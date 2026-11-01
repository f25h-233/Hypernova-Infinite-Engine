package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyTexturesEligibleTest {
    @Test
    void skipMatrix(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "graphics/a.png\t10\t20\n");
        LazySkipIndex idx = LazySkipIndex.load(f);

        assertTrue(LazyTextures.eligible(true, false, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(false, false, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, true, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, true, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, false, idx, "TEXTURE_ALPHA_ADDER", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, false, idx, "TEXTURE", "graphics/b.png"));
        assertFalse(LazyTextures.eligible(true, false, false, null, "TEXTURE", "graphics/a.png"));
    }
}
