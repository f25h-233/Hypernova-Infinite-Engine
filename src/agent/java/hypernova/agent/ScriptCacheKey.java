package hypernova.agent;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class ScriptCacheKey {
    public record Result(String id, String canonical, int fileCount, long bytes,
                         long elapsedMillis) {
    }

    private ScriptCacheKey() {
    }

    public static Result compute(RuntimeContext ctx) {
        long t0 = System.nanoTime();
        List<Path> files = collectFiles(ctx);
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        KeyManifest manifest = KeyManifest.load(manifestFile);
        List<KeyManifest.Entry> entries = manifest.refresh(files);

        List<String> classpathOrder = classpathOrder(ctx);
        StringBuilder sb = new StringBuilder(1 << 20);
        sb.append("java=").append(System.getProperty("java.version", "")).append('\n');
        sb.append("classpath=").append(String.join(File.pathSeparator, classpathOrder)).append('\n');
        List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
        for (KeyManifest.Entry e : sorted) {
            sb.append(e.path()).append('|').append(e.size()).append('|')
                    .append(e.mtime()).append('|').append(e.sha256()).append('\n');
        }
        String canonical = sb.toString();
        String id = sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0, 32);
        try {
            manifest.save(manifestFile);
        } catch (IOException e) {
            AgentLog.fail("key manifest save failed", e);
        }
        long bytes = entries.stream().mapToLong(KeyManifest.Entry::size).sum();
        return new Result(id, canonical, entries.size(), bytes,
                (System.nanoTime() - t0) / 1_000_000);
    }

    static List<Path> collectFiles(RuntimeContext ctx) {
        TreeSet<Path> files = new TreeSet<>();
        Path mods = ctx.modsRoot();
        // 方案 B：enabledMods 存的是文件夹名，不是 mod_info.json 的 id（260mods 上 256 条只能
        // 匹配 201 个目录，漏 ~27% 源码），所以不做 enabled 过滤：modsRoot 下所有含
        // mod_info.json 的直接子目录一律进指纹。只扫直接子目录，不递归孙目录，
        // 否则同级副本目录（如 "mods - 副本"）之类会被误收。
        scanModFolders(mods, files);
        // enabled_mods.json 自身仍进指纹：它决定 enabledMods 的顺序 -> classpath 优先级。
        addFile(mods.resolve("enabled_mods.json"), files);
        addTree(ctx.gameRoot().resolve("starsector-core/data/scripts"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.jar"), files);
        for (String cp : classpathOrder(ctx)) addFile(Path.of(cp), files);
        return new ArrayList<>(files);
    }

    private static List<String> classpathOrder(RuntimeContext ctx) {
        Path root = ctx.gameRoot().toAbsolutePath().normalize();
        List<String> out = new ArrayList<>();
        for (String cp : System.getProperty("java.class.path", "").split(File.pathSeparator)) {
            if (cp.isBlank()) continue;
            Path p = Path.of(cp).toAbsolutePath().normalize();
            if (Files.isRegularFile(p) && p.startsWith(root)
                    && !p.getFileName().toString().equals("hypernova.agent.jar")) {
                out.add(p.toString());
            }
        }
        return out;
    }

    private static void addTree(Path root, Set<Path> out) {
        if (!Files.isDirectory(root)) return;
        try (Stream<Path> s = Files.walk(root)) {
            s.filter(Files::isRegularFile)
                    .filter(p -> {
                        String n = p.getFileName().toString().toLowerCase(Locale.ROOT);
                        return n.endsWith(".java") || n.endsWith(".jar")
                                || n.equals("mod_info.json");
                    })
                    .forEach(p -> addFile(p, out));
        } catch (IOException e) {
            AgentLog.fail("walk failed: " + root, e);
        }
    }

    private static void addFile(Path p, Set<Path> out) {
        if (p != null && Files.isRegularFile(p)) out.add(p.toAbsolutePath().normalize());
    }

    /**
     * 把 {@code modsRoot} 下所有直接子目录里「有 mod_info.json」的 mod 收进 {@code out}。
     * 不解析 mod_info.json：文件本身会被 {@link #addFile} 收进指纹，解析失败也不影响覆盖，
     * 因此这里不依赖任何 JSON 解析，也不会因为 id 缺失/格式怪而漏掉目录。
     */
    private static void scanModFolders(Path mods, Set<Path> out) {
        if (!Files.isDirectory(mods)) return;
        try (Stream<Path> s = Files.list(mods)) {
            s.filter(Files::isDirectory).forEach(dir -> {
                if (!Files.isRegularFile(dir.resolve("mod_info.json"))) return;
                addTree(dir.resolve("src"), out);
                addTree(dir.resolve("jars"), out);
                addTree(dir.resolve("data/scripts"), out);
                addFile(dir.resolve("mod_info.json"), out);
                try (Stream<Path> rootJars = Files.list(dir)) {
                    rootJars.filter(p -> p.getFileName().toString().toLowerCase(Locale.ROOT)
                                    .endsWith(".jar"))
                            .forEach(p -> addFile(p, out));
                } catch (IOException ignored) {
                }
            });
        } catch (IOException e) {
            AgentLog.fail("mod scan failed", e);
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
