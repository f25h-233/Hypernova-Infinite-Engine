package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class LazyEvictionTest {
    private static LazyTextures.ProxyEntry entry(String path, long bytes, long lastUse) {
        LazyTextures.ProxyEntry e =
                new LazyTextures.ProxyEntry(path, "TEXTURE", 10, 10, null);
        e.ready = true;
        e.glId = 1;
        e.bytes = bytes;
        e.lastUseNanos = lastUse;
        e.owned = true;
        return e;
    }

    /** Ready entry with a real obj, so evictOne reaches the owned gate in tests. */
    private static LazyTextures.ProxyEntry readyWithObj(String path, boolean owned) {
        LazyTextures.ProxyEntry e =
                new LazyTextures.ProxyEntry(path, "TEXTURE", 10, 10, new Object());
        e.ready = true;
        e.glId = 1;
        e.bytes = 10;
        e.lastUseNanos = 100;
        e.owned = owned;
        return e;
    }

    /**
     * Selftest candidates are unmaterialized proxies. {@link #entry} builds
     * ready entries with a null obj, which the picker must reject; tests that
     * exercise the picker need a non-ready proxy with a real obj reference.
     */
    private static LazyTextures.ProxyEntry candidate(String path) {
        return new LazyTextures.ProxyEntry(path, "TEXTURE", 10, 10, new Object());
    }

    @Test
    void selectsLruUntilLowWater() {
        LazyTextures.ProxyEntry a = entry("a", 10, 100);
        LazyTextures.ProxyEntry b = entry("b", 20, 200);
        LazyTextures.ProxyEntry c = entry("c", 70, 300);
        List<LazyTextures.ProxyEntry> victims = LazyTextures.selectVictims(
                List.of(a, b, c), 150, 100, 0, 10_000, 10);
        assertEquals(List.of(a, b, c), victims);
    }

    @Test
    void stopsAtLowWaterAndMax() {
        LazyTextures.ProxyEntry a = entry("a", 10, 100);
        LazyTextures.ProxyEntry b = entry("b", 20, 200);
        LazyTextures.ProxyEntry c = entry("c", 70, 300);
        assertEquals(List.of(a), LazyTextures.selectVictims(
                List.of(a, b, c), 150, 100, 0, 10_000, 1));
    }

    @Test
    void graceStartupAndBasicPathsAreProtected() {
        LazyTextures.ProxyEntry young = entry("young", 10, 9_900);
        LazyTextures.ProxyEntry startup = entry("startup", 10, 100);
        startup.startup = true;
        LazyTextures.ProxyEntry ui = entry("graphics/ui/x.png", 10, 100);
        LazyTextures.ProxyEntry ok = entry("ok", 10, 100);
        assertEquals(List.of(ok), LazyTextures.selectVictims(
                List.of(young, startup, ui, ok), 150, 100, 1_000, 10_000, 10));
    }

    @Test
    void oldIdDeleteRule() {
        assertTrue(LazyTextures.shouldDeleteOldId(true, 7, 8, 1, true));
        assertFalse(LazyTextures.shouldDeleteOldId(false, 7, 8, 1, true));
        assertFalse(LazyTextures.shouldDeleteOldId(true, 7, 7, 1, true));
        assertFalse(LazyTextures.shouldDeleteOldId(true, 7, 8, 7, true));
        assertFalse(LazyTextures.shouldDeleteOldId(true, 7, 8, 1, false));
    }

    @Test
    void markStartupLatchesOnlyOffMain() {
        LazyTextures.ProxyEntry offMain = entry("offMain", 10, 100);
        LazyTextures.markStartup(offMain, false);
        assertTrue(offMain.startup);

        LazyTextures.ProxyEntry onMain = entry("onMain", 10, 100);
        LazyTextures.markStartup(onMain, true);
        assertFalse(onMain.startup);

        LazyTextures.ProxyEntry latch = entry("latch", 10, 100);
        LazyTextures.markStartup(latch, false);
        LazyTextures.markStartup(latch, true);
        assertTrue(latch.startup, "startup latch must never be cleared");

        assertTrue(LazyTextures.selectVictims(
                List.of(offMain), 150, 100, 0, 10_000, 10).isEmpty());
        assertEquals(List.of(onMain), LazyTextures.selectVictims(
                List.of(onMain), 150, 100, 0, 10_000, 10));
    }

    @Test
    void engineOwnedEntriesAreNotEvicted() {
        LazyTextures.ProxyEntry engine = readyWithObj("engine", false);
        LazyTextures.ProxyEntry mine = readyWithObj("mine", true);
        assertEquals(List.of(mine), LazyTextures.selectVictims(
                List.of(engine, mine), 150, 100, 0, 10_000, 10));
        assertFalse(LazyTextures.evictOneForTest(engine));
    }

    @Test
    void evictionScheduleTruthTable() {
        assertTrue(LazyTextures.shouldRunEviction(true, false, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 101, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 100, 100, true));
        assertFalse(LazyTextures.shouldRunEviction(false, false, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, true, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 0, 100, false));
    }

    @Test
    void transitionArmsOnlyWhenNameChanges() {
        assertTrue(LazyTextures.shouldArmOnTransition("TITLE", "CAMPAIGN"));
        assertFalse(LazyTextures.shouldArmOnTransition("CAMPAIGN", "CAMPAIGN"));
        assertFalse(LazyTextures.shouldArmOnTransition(null, "TITLE"));
    }

    @Test
    void partialPassRearmsOnlyWhileOverBudget() {
        assertEquals(1_123, LazyTextures.nextDueAfterPass(1_000, 123, 200, 100, 1));
        assertEquals(0, LazyTextures.nextDueAfterPass(1_000, 123, 100, 100, 1));
        // empty pass over budget: back off, do not scan 45k proxies on every materialization
        assertEquals(1_000 + LazyTextures.EVICT_EMPTY_BACKOFF_NANOS,
                LazyTextures.nextDueAfterPass(1_000, 123, 200, 100, 0));
    }

    @Test
    void budgetArmOnlyWhenIdle() {
        assertTrue(LazyTextures.shouldArmOnBudget(0, 200, 100));
        assertFalse(LazyTextures.shouldArmOnBudget(123, 200, 100));
        assertFalse(LazyTextures.shouldArmOnBudget(0, 100, 100));
    }

    @Test
    void combatProbeUsesGameState() {
        LazyTextures.resetGateStateForTest();
        com.fs.starfarer.api.Global.currentState = "COMBAT";
        assertTrue(LazyTextures.isInCombat());
        com.fs.starfarer.api.Global.currentState = "CAMPAIGN";
        assertFalse(LazyTextures.isInCombat());
        com.fs.starfarer.api.Global.currentState = null;
        assertFalse(LazyTextures.isInCombat());
        LazyTextures.resetGateStateForTest();
    }

    @Test
    void combatProbeFailsClosedWhenProbeThrows() {
        LazyTextures.resetGateStateForTest();
        try {
            com.fs.starfarer.api.Global.currentState = "CAMPAIGN";
            com.fs.starfarer.api.Global.throwNow = true;
            assertTrue(LazyTextures.isInCombat());
        } finally {
            com.fs.starfarer.api.Global.throwNow = false;
            com.fs.starfarer.api.Global.currentState = null;
            LazyTextures.resetGateStateForTest();
        }
    }

    @Test
    void ddsBytesIsOneBytePerPixel() {
        assertEquals(810L * 500L, LazyTextures.ddsBytes(810, 500));
        assertEquals(0L, LazyTextures.ddsBytes(-1, 10));
    }

    @Test
    void selfTestPickerPrefersDdsAndSkipsBasic(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "graphics/a.png\t1\t1\tD:/a.png\tD:/a.dds\t1\n"
                + "graphics/b.png\t1\t1\t\t\t0\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        LazyTextures.ProxyEntry ready = entry("graphics/ready.png", 1, 1);
        ready.ready = true;
        LazyTextures.ProxyEntry ui = candidate("graphics/ui/x.png");
        LazyTextures.ProxyEntry a = candidate("graphics/a.png");
        LazyTextures.ProxyEntry b = candidate("graphics/b.png");
        assertSame(a, LazyTextures.pickSelfTestEntry(List.of(ready, ui, a, b), idx, true));
        assertNull(LazyTextures.pickSelfTestEntry(List.of(ready, ui), idx, true));
        assertSame(b, LazyTextures.pickSelfTestEntry(List.of(b), idx, false));
    }

    @Test
    void evictableBytesExcludeStartupAndForeign() {
        assertEquals(50, LazyTextures.evictableBytes(150, 100, 0));
        assertEquals(20, LazyTextures.evictableBytes(150, 100, 30));
        assertEquals(0, LazyTextures.evictableBytes(100, 80, 40));
    }

    @Test
    void byteClassTruthTable() {
        assertEquals(LazyTextures.ByteClass.STARTUP,
                LazyTextures.byteClass(true, true));
        assertEquals(LazyTextures.ByteClass.STARTUP,
                LazyTextures.byteClass(true, false));
        assertEquals(LazyTextures.ByteClass.FOREIGN,
                LazyTextures.byteClass(false, false));
        assertEquals(LazyTextures.ByteClass.EVICTABLE,
                LazyTextures.byteClass(false, true));
    }

    @Test
    void noteMaterializedClassifiesBytes() {
        LazyTextures.resetGateStateForTest();
        LazyTextures.ProxyEntry startup = new LazyTextures.ProxyEntry(
                "startup", "TEXTURE", 10, 10, new Object());
        LazyTextures.noteMaterialized(startup, 100, false);
        assertTrue(startup.startup);
        LazyTextures.ProxyEntry foreign = new LazyTextures.ProxyEntry(
                "foreign", "TEXTURE", 10, 10, new Object());
        foreign.owned = false;
        LazyTextures.noteMaterialized(foreign, 30, true);
        LazyTextures.ProxyEntry mine = new LazyTextures.ProxyEntry(
                "mine", "TEXTURE", 10, 10, new Object());
        mine.owned = true;
        LazyTextures.noteMaterialized(mine, 20, true);
        assertEquals(150, LazyTextures.liveBytesForTest());
        assertEquals(100, LazyTextures.startupBytesForTest());
        assertEquals(30, LazyTextures.foreignBytesForTest());
        assertEquals(20, LazyTextures.evictableBytesForTest());
        LazyTextures.resetGateStateForTest();
    }

    @Test
    void evictOneRefusesStartupAndBasicEvenWhenReady() {
        LazyTextures.ProxyEntry startup = readyWithObj("startup", true);
        startup.startup = true;
        assertFalse(LazyTextures.evictOneForTest(startup));

        LazyTextures.ProxyEntry ui = readyWithObj("graphics/ui/x.png", true);
        assertFalse(LazyTextures.evictOneForTest(ui));
    }

    @Test
    void parkFailedProxyResetsOnlyUnreadyEntries() {
        List<Integer> ids = new java.util.ArrayList<>();
        LazyTextures.ProxyEntry failed = new LazyTextures.ProxyEntry(
                "failed", "TEXTURE", 10, 10, new Object());
        assertTrue(LazyTextures.parkFailedProxy(failed, true, 77, (entry, pid) -> {
            ids.add(pid);
            entry.glId = pid;
        }));
        assertEquals(List.of(77), ids);
        assertEquals(0, failed.glId);
        assertTrue(failed.failed);
        assertEquals(1, LazyTextures.failedParkedForTest());

        LazyTextures.ProxyEntry ready = readyWithObj("ready", true);
        assertFalse(LazyTextures.parkFailedProxy(ready, true, 77, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(failed, false, 77, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(failed, true, 0, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(
                failed, true, 77, (e, pid) -> { throw new IllegalStateException("boom"); }));
    }

    @Test
    void evictionGateIsMutationDetectable() {
        LazyTextures.ProxyEntry mine = readyWithObj("mine", true);
        assertTrue(LazyTextures.canEvict(mine, true));
        assertFalse(LazyTextures.canEvict(mine, false));
        LazyTextures.ProxyEntry startup = readyWithObj("startup", true);
        startup.startup = true;
        assertFalse(LazyTextures.canEvict(startup, true));
        LazyTextures.ProxyEntry ui = readyWithObj("graphics/ui/x.png", true);
        assertFalse(LazyTextures.canEvict(ui, true));
        LazyTextures.ProxyEntry engine = readyWithObj("engine", false);
        assertFalse(LazyTextures.canEvict(engine, true));
        LazyTextures.ProxyEntry notReady = readyWithObj("notReady", true);
        notReady.ready = false;
        assertFalse(LazyTextures.canEvict(notReady, true));
    }

    @Test
    void ddsFallbackReasonsCountAndReset() {
        LazyTextures.resetGateStateForTest();
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.META, "graphics/a.png", "no metadata");
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.META, "graphics/b.png", null);
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.CHECK, "graphics/c.png", "dxgi 1");
        assertEquals(2, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.META));
        assertEquals(1, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.CHECK));
        assertEquals(0, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.COPY));
        LazyTextures.resetGateStateForTest();
        assertEquals(0, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.META));
    }

    @Test
    void ddsFallbackTotalAndSummaryKeys() {
        LazyTextures.resetGateStateForTest();
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.META, "graphics/a.png", null);
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.CHECK, "graphics/b.png", "dxgi 1");
        assertEquals(2, LazyTextures.ddsFallbackTotalForTest());
        String summary = LazyTextures.ddsFallbackSummary();
        for (String key : List.of("ddsFbMeta=1", "ddsFbBridge=0", "ddsFbPath=0",
                "ddsFbGet=0", "ddsFbCheck=1", "ddsFbCommit=0", "ddsFbHandler=0",
                "ddsFbNull=0", "ddsFbShape=0", "ddsFbCopy=0")) {
            assertTrue(summary.contains(key), key);
        }
        LazyTextures.resetGateStateForTest();
        assertEquals(0, LazyTextures.ddsFallbackTotalForTest());
    }

    @Test
    void budgetBytesOverrideWins() {
        assertEquals(1024L * 1024L, LazyTextures.budgetBytes(1, -1));
        assertEquals(262_144L, LazyTextures.budgetBytes(1, 262_144));
        assertEquals(Long.MAX_VALUE, LazyTextures.budgetBytes(0, -1));
        assertEquals(262_144L, LazyTextures.budgetBytes(0, 262_144));
        assertEquals(Long.MAX_VALUE, LazyTextures.budgetBytes(-1, 0));
    }

    @Test
    void backgroundsAreBasicPath() {
        assertTrue(LazyTextures.isBasicPath("graphics/backgrounds/x.jpg"));
        assertTrue(LazyTextures.isBasicPath("graphics/ui/x.png"));
        assertTrue(LazyTextures.isBasicPath("graphics/fonts/x.png"));
        assertTrue(LazyTextures.isBasicPath("graphics/intro/x.png"));
        assertFalse(LazyTextures.isBasicPath("graphics/ships/x.png"));
    }
}
