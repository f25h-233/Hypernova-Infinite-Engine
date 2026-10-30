package hypernova.agent;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

/**
 * 判定某个点分类名在本次加载环境里是否存在对应的 {@code .java} 源。
 *
 * <p>用途：区分「真正的缓存 miss（本可以命中，但缓存里没有）」和「探测性查询
 * （游戏 jar 里的类，根本没有源码，永远不可能命中）」。前者才是命中率的分母。
 *
 * <p>实现取自 FR 实际使用的 {@code com.fs.starfarer.loading.JavaSourceFinder}
 * 的搜索根：基座的 {@code data/scripts}、每个 mod 的 {@code src} 与
 * {@code data/scripts}。这里不复刻它的 obfuscation 逻辑，只做「目录里有没有这个
 * 相对路径的 .java」的存在性判断——用于统计，不参与加载。
 */
public final class SourceOracle {
    /** 源根列表（absolute）。 */
    private final List<Path> roots;

    private SourceOracle(List<Path> roots) {
        this.roots = roots;
    }

    /** 从运行时上下文收集搜索根。任何异常都返回空根集（= 全部视为有源码，保守）。 */
    public static SourceOracle from(RuntimeContext ctx) {
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
                        // 这一条覆盖 data/scripts、data/missions、data/hullmods 等全部 data.* 包。
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
        return new SourceOracle(roots);
    }

    /** 空判定器：没有根时一切按「有源码」处理（保守，不虚报命中率）。 */
    public static SourceOracle empty() {
        return new SourceOracle(List.of());
    }

    public List<Path> roots() {
        return roots;
    }

    /**
     * 点分类名是否有对应源码。
     *
     * <p>内嵌类（{@code Outer$Inner}）由同一份源编译产出，按外部类判定。
     */
    public boolean hasSource(String binaryName) {
        // 空名不是"有源码"——它是无效探测，不该进 sourced miss 样本
        // （m1d S5 冷跑实测出现过 3 条空名，污染了 sourced_misses 计数）。
        if (binaryName == null || binaryName.isEmpty()) return false;
        // 没有根时无法判断：返回 true 保守，不把真实缺陷掩盖成"不该命中"。
        if (roots.isEmpty()) return true;
        String base = binaryName;
        int dollar = base.indexOf('$');
        if (dollar > 0) base = base.substring(0, dollar);
        String rel = base.replace('.', '/') + ".java";
        for (Path root : roots) {
            try {
                if (Files.isRegularFile(root.resolve(rel))) return true;
            } catch (Throwable ignored) {
                // 单个根出错继续看下一个
            }
        }
        // 有些 mod 把源码放在 src/data/scripts/... 下，也已由上面的 src 根覆盖；
        // 这里不再做大小写不敏感回退，保持确定性。
        return false;
    }

    @Override
    public String toString() {
        return "SourceOracle" + roots.stream().map(Path::toString)
                .map(s -> s.toLowerCase(Locale.ROOT)).toList();
    }
}
