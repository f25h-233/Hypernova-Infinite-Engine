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
    }

    @Test
    void enabledFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load("true", null, "C:/x/skip.txt", null);
        assertTrue(c.enabled());
        assertFalse(c.probe());
        assertEquals(Path.of("C:/x/skip.txt"), c.skipFile());
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
}
