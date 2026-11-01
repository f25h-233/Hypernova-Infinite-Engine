package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

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
        return e;
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
    void ddsBytesIsOneBytePerPixel() {
        assertEquals(810L * 500L, LazyTextures.ddsBytes(810, 500));
        assertEquals(0L, LazyTextures.ddsBytes(-1, 10));
    }
}
