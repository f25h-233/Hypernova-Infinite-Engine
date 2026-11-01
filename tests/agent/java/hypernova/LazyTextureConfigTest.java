package hypernova;

import hypernova.agent.textures.LazyTextureConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyTextureConfigTest {
    @Test
    void defaultsOff() {
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, null);
        assertFalse(c.enabled());
        assertFalse(c.probe());
        assertNull(c.skipFile());
        assertNull(c.manifestFile());
        assertTrue(c.dds());
        assertFalse(c.eviction());
        assertEquals(256, c.evictionBudgetMb());
        assertEquals(10_000, c.evictionGraceMs());
        assertEquals(2_000, c.evictionSceneDelayMs());
        assertEquals(64, c.evictionMaxPerPass());
        assertFalse(c.selftest());
    }

    @Test
    void enabledFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load("true", null, "C:/x/skip.txt", null);
        assertTrue(c.enabled());
        assertFalse(c.probe());
        assertEquals(Path.of("C:/x/skip.txt"), c.skipFile());
        assertEquals(Path.of("C:/x/manifest-v1.json"), c.manifestFile());
    }

    @Test
    void probeFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load(null, "true", "C:/x/skip.txt", null);
        assertFalse(c.enabled());
        assertTrue(c.probe());
    }

    @Test
    void configFileEnablesLazy(@TempDir Path dir) throws Exception {
        Path cfg = dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{\"textures\":{\"lazy\":{\"enabled\":true}}}");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, cfg);
        assertTrue(c.enabled());
        assertEquals(dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt"),
                c.skipFile());
    }

    @Test
    void badConfigDefaultsOff(@TempDir Path dir) throws Exception {
        Path cfg = dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{not json");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, cfg);
        assertFalse(c.enabled());
    }

    @Test
    void configFileParsesDdsAndEviction(@TempDir Path dir) throws Exception {
        Path cfg = dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{\"textures\":{\"lazy\":{"
                + "\"enabled\":true,\"dds\":false,\"selftest\":true,"
                + "\"eviction\":{\"enabled\":true,\"budget_mb\":32,\"grace_ms\":500,"
                + "\"scene_delay_ms\":100,\"max_per_pass\":4}}}}");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, cfg);
        assertTrue(c.enabled());
        assertFalse(c.dds());
        assertTrue(c.selftest());
        assertTrue(c.eviction());
        assertEquals(32, c.evictionBudgetMb());
        assertEquals(500, c.evictionGraceMs());
        assertEquals(100, c.evictionSceneDelayMs());
        assertEquals(4, c.evictionMaxPerPass());
    }
}
