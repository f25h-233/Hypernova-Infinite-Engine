package hypernova.agent;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;

/**
 * 判定某个点分类名在本次加载环境里是否存在对应的 {@code .java} 源。
 *
 * <p>用途：区分「真正的缓存 miss（本可以命中，但缓存里没有）」和「探测性查询
 * （游戏 jar 里的类，根本没有源码，永远不可能命中）」。前者才是命中率的分母。
 *
 * <p><b>M-1d 热修（2026-10-30）：</b>旧实现在每次 {@link #hasSource(String)} 时
 * 对每个 root 做一次 {@code Files.isRegularFile}。260mods 的 FR rulecmd 探测有
 * 11,264 次 miss、389 个 root，合计约 4.38M 次 stat；实测给首屏加了 45–53 s。
 * 现在 {@link #from(RuntimeContext)} 在后台线程一次性遍历 root，建立
 * 「相对路径 -> .java」集合；{@code hasSource} 只做 O(1) set lookup。
 *
 * <p>没有 roots 或索引为空时保守返回 true。这比旧实现更保守：旧实现在 roots
 * 非空但一个 .java 都没有时会返回 false；这里不把真实缺陷掩盖成
 * 「本来就不该命中」。
 */
public final class SourceOracle {
    /** 资源目录名：只在 root 的直接子目录按这些名字剪枝，避免扫 125k 张图。 */
    private static final Set<String> SKIP_DIRS = Set.of(
            "graphics", "sounds", "sound", "images", "music", "jars", "cache",
            "saves", "screenshots", "javadoc", ".git");

    /** 源根列表（absolute）。 */
    private final List<Path> roots;
    /** root.relativize(file) 的 POSIX 形式，例如 "src/a/ModClass.java"。 */
    private final Set<String> sourcePaths;

    private SourceOracle(List<Path> roots, Set<String> sourcePaths) {
        this.roots = roots;
        this.sourcePaths = sourcePaths;
    }

    /** 从运行时上下文收集搜索根，并在后台线程一次性建立源码索引。 */
    public static SourceOracle from(RuntimeContext ctx) {
        List<Path> roots = collectRoots(ctx);
        return new SourceOracle(roots, indexSources(roots));
    }

    /** 空判定器：没有根时一切按「有源码」处理（保守，不虚报命中率）。 */
    public static SourceOracle empty() {
        return new SourceOracle(List.of(), Set.of());
    }

    public List<Path> roots() {
        return roots;
    }

    /** 索引里的 .java 文件数；用于 agent 日志诊断。 */
    public int sourceCount() {
        return sourcePaths.size();
    }

    /**
     * 点分类名是否有对应源码。
     *
     * <p>内嵌类（{@code Outer$Inner}）由同一份源编译产出，按外部类判定。
     * 本方法只读构造期索引，**绝不访问文件系统**。
     */
    public boolean hasSource(String binaryName) {
        if (binaryName == null || binaryName.isEmpty()) return false;
        // 没有根 / 索引为空：无法判断，返回 true（比旧实现更保守，不把真实缺陷掩盖成「不该命中」）。
        if (roots.isEmpty() || sourcePaths.isEmpty()) return true;
        String base = binaryName;
        int dollar = base.indexOf('$');
        if (dollar > 0) base = base.substring(0, dollar);
        String rel = base.replace('.', '/') + ".java";
        return sourcePaths.contains(rel);
    }

    @Override
    public String toString() {
        return "SourceOracle" + roots.stream().map(Path::toString)
                .map(s -> s.toLowerCase(Locale.ROOT)).toList();
    }

    // ------------------------------------------------------------------ roots

    private static List<Path> collectRoots(RuntimeContext ctx) {
        List<Path> roots = new ArrayList<>();
        try {
            Path game = ctx.gameRoot();
            if (game != null) {
                // 根必须是 starsector-core 本身，不是 starsector-core/data/scripts。
                // 包名相对 starsector-core 组织：data.hullmods.X -> starsector-core/data/hullmods/X.java。
                // 只收 data/scripts 会漏掉基座 116 个 .java 里的 88 个（实测：116 个全部误判为无源码）。
                Path core = game.resolve("starsector-core");
                if (Files.isDirectory(core)) roots.add(core.toAbsolutePath().normalize());
            }
            Path mods = ctx.modsRoot();
            if (mods != null && Files.isDirectory(mods)) {
                try (Stream<Path> s = Files.list(mods)) {
                    s.filter(Files::isDirectory).forEach(dir -> {
                        // mod 根本身：包名是按 mod 目录的相对路径组织的，
                        // 例如 data/scripts/AvaliModPlugin.java 对应类 data.scripts.AvaliModPlugin。
                        roots.add(dir.toAbsolutePath().normalize());
                        Path src = dir.resolve("src");
                        if (Files.isDirectory(src)) roots.add(src.toAbsolutePath().normalize());
                        Path ds = dir.resolve("data/scripts");
                        if (Files.isDirectory(ds)) roots.add(ds.toAbsolutePath().normalize());
                    });
                } catch (Throwable ignored) {
                    // 扫描失败：保留已收集的根
                }
            }
        } catch (Throwable ignored) {
            // 任何失败都退化为「全部视为有源码」
        }
        return roots;
    }

    // ----------------------------------------------------------------- index

    private static Set<String> indexSources(List<Path> roots) {
        Set<String> out = new HashSet<>(16_384);
        // 每个 root 是独立的命名空间：同一个文件在 mod 根下是 src/a/X.java，
        // 在 src 根下是 a/X.java；两者都必须进集合，否则 hasSource("a.X") 会漏。
        // 嵌套 root 重复遍历 source 目录的代价很小（相对 4.38M 次 stat），必须保留。
        for (Path root : roots) walk(root, out, !isSourceRoot(root));
        return out;
    }

    /** src 与 data/scripts 是显式源根：里面即使有名为 graphics 的包目录也不能剪。 */
    private static boolean isSourceRoot(Path root) {
        Path name = root.getFileName();
        if (name == null) return false;
        String n = name.toString();
        if (n.equalsIgnoreCase("src")) return true;
        Path parent = root.getParent();
        return n.equalsIgnoreCase("scripts") && parent != null && parent.getFileName() != null
                && parent.getFileName().toString().equalsIgnoreCase("data");
    }

    private static void walk(Path root, Set<String> out, boolean pruneDirectChildren) {
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (pruneDirectChildren && !dir.equals(root) && root.equals(dir.getParent())) {
                        String name = dir.getFileName() == null
                                ? "" : dir.getFileName().toString().toLowerCase(Locale.ROOT);
                        if (SKIP_DIRS.contains(name)) return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    String name = file.getFileName() == null ? "" : file.getFileName().toString();
                    if (name.toLowerCase(Locale.ROOT).endsWith(".java")) {
                        out.add(root.relativize(file).toString().replace('\\', '/'));
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc) {
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException | RuntimeException ignored) {
            // 单个 root 失败不影响其它 root；索引为空时 hasSource 保守返回 true。
        }
    }
}
