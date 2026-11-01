package hypernova;

import hypernova.agent.textures.LazyTextureConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyTextureConfigTest {
    @Test
    void probeOffByDefault() {
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null);
        assertFalse(c.probe());
        assertNull(c.skipFile());
    }

    @Test
    void probeAndSkipFileFromProperties() {
        LazyTextureConfig c = LazyTextureConfig.load("true", "C:/x/skip.txt", null);
        assertTrue(c.probe());
        assertEquals(Path.of("C:/x/skip.txt"), c.skipFile());
    }

    @Test
    void skipFileDerivedFromModRoot(@TempDir Path dir) throws Exception {
        Path mod = dir.resolve("mods/hypernova_infinite_engine");
        Path cfg = mod.resolve("data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{}");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, cfg);
        assertFalse(c.probe());
        assertEquals(mod.resolve("data/config/hypernova/lazy-skip-v1.txt"), c.skipFile());
    }
}
