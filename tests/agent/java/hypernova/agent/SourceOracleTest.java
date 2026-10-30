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
}
