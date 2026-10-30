package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * {@link SourceOracle} 是命中率口径的分界线：它把「没源码的探测性 miss」
 * 从分母里剔出去。判错的后果是把不可缓存的类算成缓存失败（命中率虚低），
 * 或者把真正该缓存的类算成不可缓存（命中率虚高、掩盖缺陷）。
 */
class SourceOracleTest {
    @TempDir Path tmp;

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }

    @Test
    void findsSourceUnderCoreDataScriptsAndModSrc() throws Exception {
        Path game = tmp.resolve("g1");
        // 真实布局：包名相对 starsector-core 组织。
        //   data.hullmods.X   -> starsector-core/data/hullmods/X.java
        //   data.scripts.plugins.Y -> starsector-core/data/scripts/plugins/Y.java
        Path core = game.resolve("starsector-core");
        Files.createDirectories(core.resolve("data/hullmods"));
        Files.writeString(core.resolve("data/hullmods/HeavyArmor.java"),
                "package data.hullmods; class HeavyArmor {}");
        Files.createDirectories(core.resolve("data/scripts/plugins"));
        Files.writeString(core.resolve("data/scripts/plugins/CorePlugin.java"),
                "package data.scripts.plugins; class CorePlugin {}");

        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m1");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("src/a/ModClass.java"), "package a; class ModClass {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        assertTrue(oracle.hasSource("data.hullmods.HeavyArmor"),
                "starsector-core/data/hullmods 下的类必须是「有源码」");
        assertTrue(oracle.hasSource("data.scripts.plugins.CorePlugin"),
                "starsector-core/data/scripts 下的类必须是「有源码」");
        assertTrue(oracle.hasSource("a.ModClass"), "mod src 下的类必须是「有源码」");
        // 候选探测名：真实 GateCMD 在 rulecmd/missions/ 下，
        // rulecmd.GateCMD 这个名字在任何地方都不存在。
        assertFalse(oracle.hasSource("com.fs.starfarer.api.impl.campaign.rulecmd.GateCMD"),
                "不存在的候选探测名必须判为「无源码」");
    }

    @Test
    void innerClassesFollowTheirOuterClass() throws Exception {
        Path game = tmp.resolve("g2");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src/x"));
        Files.writeString(mod.resolve("src/x/Outer.java"), "package x; class Outer { class In {} }");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        assertTrue(oracle.hasSource("x.Outer$In"), "内嵌类应由外部类的源码判定");
        assertFalse(oracle.hasSource("x.Missing$1"));
    }

    @Test
    void emptyNameIsNotSourced() {
        // S5 冷跑实测出现过 3 条空的 findClass 调用名；它们不能算进
        // sourced_misses，否则会虚报"有源码却没命中"。
        SourceOracle empty = SourceOracle.empty();
        assertFalse(empty.hasSource(""));
        assertFalse(empty.hasSource(null));
    }

    @Test
    void noRootsMeansEverythingCountsAsSourced() {
        // 保守方向：没有根（初始化失败）时不能把 miss 判成「无源码」，
        // 否则会把真实缺陷掩盖成「本来就不该命中」。
        SourceOracle empty = SourceOracle.empty();
        assertTrue(empty.hasSource("any.Class"));
        assertTrue(empty.hasSource("com.fs.starfarer.api.impl.Foo"));
    }

    @Test
    void dataScriptsUnderModIsAlsoASourceRoot() throws Exception {
        Path game = tmp.resolve("g3");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("data/scripts/world"));
        Files.writeString(mod.resolve("data/scripts/world/Gen.java"), "package world; class Gen {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        assertTrue(oracle.hasSource("world.Gen"));
    }

    @Test
    void hasSourceUsesSnapshotNotFilesystem() throws Exception {
        Path game = tmp.resolve("g4");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src/a"));
        Path source = mod.resolve("src/a/ModClass.java");
        Files.writeString(source, "package a; class ModClass {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));
        assertTrue(oracle.sourceCount() > 0,
                "前置条件：索引必须非空，否则 hasSource 会走空索引短路而测不到快照语义");

        // 删除源文件后仍然必须判 true：hasSource 只能读 from() 时建立的索引。
        // 旧实现每次调用都 Files.isRegularFile，删除后会变 false，导致
        // 11,264 次 rulecmd 探测 × 389 roots ≈ 4.38M stat 的启动回归。
        Files.delete(source);
        assertTrue(oracle.hasSource("a.ModClass"),
                "hasSource 必须使用构造期快照，不能在每次调用时访问文件系统");
    }

    @Test
    void hasSourceIsCheapWithManyRoots() throws Exception {
        Path game = tmp.resolve("g5");
        Path mods = game.resolve("mods");
        Files.createDirectories(mods);
        for (int i = 0; i < 300; i++) {
            Files.createDirectories(mods.resolve("m" + i + "/src"));
        }
        Path present = mods.resolve("m0/src/a/Present.java");
        Files.createDirectories(present.getParent());
        Files.writeString(present, "package a; class Present {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));
        assertTrue(oracle.hasSource("a.Present"),
                "前置条件：索引必须非空，确保 11,264 次循环走真实 set 查表而不是空索引短路");
        assertTimeoutPreemptively(java.time.Duration.ofSeconds(5), () -> {
            for (int i = 0; i < 11_264; i++) {
                oracle.hasSource("com.fs.starfarer.api.impl.campaign.rulecmd.T" + i + "CMD");
            }
        }, "11,264 次 hasSource 在 300 个 roots 下必须远低于 5 s（旧实现约 30–50 s）");
    }

    @Test
    void findsSourceInTopLevelPackageDir() throws Exception {
        Path game = tmp.resolve("g6");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("org/example"));
        Files.writeString(mod.resolve("org/example/TopLevel.java"),
                "package org.example; class TopLevel {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        assertTrue(oracle.hasSource("org.example.TopLevel"),
                "mod 根下的顶层包目录（不在 src/ 下）也必须被索引");
    }

    @Test
    void findsSourceInPackageDirNamedLikeAsset() throws Exception {
        Path game = tmp.resolve("g7");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("org/dark/graphics/plugins"));
        Files.writeString(mod.resolve("org/dark/graphics/plugins/LightInjector.java"),
                "package org.dark.graphics.plugins; class LightInjector {}");
        // 必须有另一个未被剪枝的源文件：索引为空时 hasSource 保守返回 true，
        // 会掩盖「graphics 包目录被剪掉」的缺陷，让本测试假绿。
        Files.createDirectories(mod.resolve("org/example"));
        Files.writeString(mod.resolve("org/example/Real.java"),
                "package org.example; class Real {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));
        assertTrue(oracle.sourceCount() > 0,
                "前置条件：索引必须非空，否则空索引短路会掩盖剪枝缺陷");

        assertTrue(oracle.hasSource("org.dark.graphics.plugins.LightInjector"),
                "org/dark/graphics 是包目录，不能因为名叫 graphics 就剪枝");
    }
}
