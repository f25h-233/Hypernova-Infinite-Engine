package hypernova.agent;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * 缓存 key 的文件枚举器。
 *
 * <p>旧实现每个文件要读多次属性：{@code Files.walk} 递归时一次、{@code Files.isRegularFile}
 * 过滤一次、{@code Files.size} 与 {@code Files.getLastModifiedTime} 各一次。这里改成
 * {@link Files#walkFileTree} + {@link BasicFileAttributes}：枚举一次就拿到 path/size/mtime，
 * 后续 {@link KeyManifest#refresh} 直接复用，不再 stat。
 *
 * <p>260mods 实测（热 OS 缓存、12,308 个文件）：collect 2,155 ms + refresh 937 ms →
 * scan 412 ms（串行）/ 172 ms（4 线程）。
 *
 * <p>行为必须与旧 {@code ScriptCacheKey.collectFiles} 逐字等价；等价性由
 * {@code KeyScannerTest} 对着一份旧算法复刻来守护。
 */
public final class KeyScanner {
    /** 一个进入指纹的文件；mtime 用毫秒，与 {@link KeyManifest.Entry} 一致。 */
    public record FileInfo(Path path, long size, long mtimeMillis) {
    }

    private KeyScanner() {
    }

    static List<FileInfo> scan(RuntimeContext ctx) {
        Map<String, FileInfo> out = new TreeMap<>();
        List<Path> roots = new ArrayList<>();
        List<Path> singles = new ArrayList<>();

        // 方案 B：mods 根下所有含 mod_info.json 的直接子目录都进指纹，不解析 JSON。
        Path mods = ctx.modsRoot();
        if (Files.isDirectory(mods)) {
            try (DirectoryStream<Path> ds = Files.newDirectoryStream(mods)) {
                for (Path dir : ds) {
                    if (!Files.isDirectory(dir)) continue;
                    Path info = dir.resolve("mod_info.json");
                    if (!Files.isRegularFile(info)) continue;
                    roots.add(dir.resolve("src"));
                    roots.add(dir.resolve("jars"));
                    roots.add(dir.resolve("data/scripts"));
                    singles.add(info);
                    try (DirectoryStream<Path> jars = Files.newDirectoryStream(dir)) {
                        for (Path p : jars) {
                            if (p.getFileName().toString().toLowerCase(Locale.ROOT)
                                    .endsWith(".jar")) {
                                singles.add(p);
                            }
                        }
                    } catch (IOException e) {
                        AgentLog.fail("mod jar scan failed: " + dir, e);
                    }
                }
            } catch (IOException e) {
                AgentLog.fail("mod scan failed", e);
            }
        }
        singles.add(mods.resolve("enabled_mods.json"));
        roots.add(ctx.gameRoot().resolve("starsector-core/data/scripts"));
        singles.add(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"));
        singles.add(ctx.gameRoot().resolve("starsector-core/fr.jar"));
        for (String cp : ScriptCacheKey.classpathOrder(ctx)) singles.add(Path.of(cp));

        walkAll(roots, out, threads());
        for (Path p : singles) addFile(p, out);
        return new ArrayList<>(out.values());
    }

    /** {@code -Dhypernova.keyThreads=N}；未设置或非法值 → auto。1 = 串行。 */
    static int threads() {
        String v = System.getProperty("hypernova.keyThreads", "");
        if (!v.isBlank()) {
            try {
                int n = Integer.parseInt(v.trim());
                if (n > 0) return Math.min(32, n);
            } catch (NumberFormatException ignored) {
                // 非法值退回 auto
            }
        }
        return Math.min(4, Math.max(1, Runtime.getRuntime().availableProcessors()));
    }

    private static void walkAll(List<Path> roots, Map<String, FileInfo> out, int threads) {
        if (threads <= 1 || roots.size() <= 1) {
            for (Path r : roots) walkTree(r, out);
            return;
        }
        ExecutorService pool = Executors.newFixedThreadPool(threads, r -> {
            Thread t = new Thread(r, "Hypernova-KeyScan");
            t.setDaemon(true);
            return t;
        });
        boolean interrupted = false;
        try {
            List<Callable<Map<String, FileInfo>>> tasks = new ArrayList<>(roots.size());
            for (Path root : roots) {
                tasks.add(() -> {
                    Map<String, FileInfo> local = new TreeMap<>();
                    walkTree(root, local);
                    return local;
                });
            }
            for (Future<Map<String, FileInfo>> f : pool.invokeAll(tasks)) {
                try {
                    out.putAll(f.get());
                } catch (ExecutionException e) {
                    AgentLog.fail("key scan task failed", e.getCause());
                }
            }
        } catch (InterruptedException e) {
            interrupted = true;
            Thread.currentThread().interrupt();
        } finally {
            pool.shutdownNow();
        }
        if (interrupted) {
            // 被中断时 invokeAll 可能只跑了一部分；串行补全，绝不漏文件。
            for (Path r : roots) walkTree(r, out);
        }
    }

    private static void walkTree(Path root, Map<String, FileInfo> out) {
        if (!Files.isDirectory(root)) return;
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (isFingerprintFile(file, attrs)) add(file, attrs, out);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc) {
                    // 与旧 Files.walk 不同：单个子树不可读时继续扫兄弟节点（更安全方向：
                    // 宁可多收，不可漏收；漏收会让缓存带毒）。
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException e) {
            AgentLog.fail("walk failed: " + root, e);
        }
    }

    private static boolean isFingerprintFile(Path file, BasicFileAttributes attrs) {
        String name = file.getFileName().toString();
        if (name.equals("hypernova.agent.jar")) return false;
        String lower = name.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".java") || lower.endsWith(".jar")
                || lower.equals("mod_info.json"))) {
            return false;
        }
        // walkFileTree 默认不跟随链接；旧 Files.isRegularFile 会跟随。补上这一差异，
        // 让「指向普通文件的符号链接」仍进指纹。
        return attrs.isRegularFile()
                || (attrs.isSymbolicLink() && Files.isRegularFile(file));
    }

    private static void add(Path file, BasicFileAttributes attrs, Map<String, FileInfo> out) {
        long size = attrs.size();
        long mtime = attrs.lastModifiedTime().toMillis();
        if (attrs.isSymbolicLink()) {
            // 链接本身的大小/时间不是旧实现看到的；旧实现跟随链接，这里也跟随。
            try {
                size = Files.size(file);
                mtime = Files.getLastModifiedTime(file).toMillis();
            } catch (IOException e) {
                return;
            }
        }
        Path abs = file.toAbsolutePath().normalize();
        out.put(abs.toString(), new FileInfo(abs, size, mtime));
    }

    private static void addFile(Path p, Map<String, FileInfo> out) {
        if (p == null) return;
        try {
            // readAttributes 默认跟随链接，与旧 Files.isRegularFile 语义一致。
            BasicFileAttributes attrs = Files.readAttributes(p, BasicFileAttributes.class);
            if (!attrs.isRegularFile()) return;
            if (p.getFileName().toString().equals("hypernova.agent.jar")) return;
            add(p, attrs, out);
        } catch (IOException ignored) {
            // 不存在/不可读：旧 Files.isRegularFile 同样返回 false
        }
    }
}
