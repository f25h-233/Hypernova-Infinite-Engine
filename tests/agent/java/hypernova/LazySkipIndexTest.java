package hypernova;

import hypernova.agent.textures.LazySkipIndex;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazySkipIndexTest {
    @Test
    void parsesPathsAndDims(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "# comment\n"
                + "graphics/a.png\t10\t20\n"
                + "\n"
                + "graphics/b c.png\t3\t4\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        assertEquals(2, idx.size());
        assertEquals(0, idx.invalid());
        assertTrue(idx.contains("graphics/a.png"));
        assertEquals(new LazySkipIndex.Entry(10, 20, null, null, false),
                idx.get("graphics/a.png"));
        assertEquals(new LazySkipIndex.Entry(3, 4, null, null, false),
                idx.get("graphics/b c.png"));
    }

    @Test
    void rejectsBadDimsAndMalformedLines(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "bad line\n"
                + "graphics/a.png\t0\t20\n"
                + "graphics/b.png\tx\t20\n"
                + "graphics/c.png\t5\t\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        assertEquals(0, idx.size());
        assertEquals(4, idx.invalid());
    }

    @Test
    void missingFileThrows(@TempDir Path dir) {
        assertThrows(Exception.class, () -> LazySkipIndex.load(dir.resolve("nope.txt")));
    }

    @Test
    void parsesGenerationHeader(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "# generation=abc123\n"
                + "graphics/a.png\t10\t20\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        assertEquals("abc123", idx.generation());
        assertEquals(1, idx.size());
        assertEquals(0, idx.invalid());
    }

    @Test
    void parsesV2Columns(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "# generation=abc123\n"
                + "graphics/a.png\t10\t20\tD:/m/a.png\tD:/d/a.dds\t1\n"
                + "graphics/b.png\t3\t4\t\t\t0\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        LazySkipIndex.Entry a = idx.get("graphics/a.png");
        assertEquals(10, a.w());
        assertEquals(20, a.h());
        assertEquals("D:/m/a.png", a.absPath());
        assertEquals("D:/d/a.dds", a.ddsPath());
        assertTrue(a.baked());
        assertTrue(a.hasDds());
        LazySkipIndex.Entry b = idx.get("graphics/b.png");
        assertNull(b.absPath());
        assertNull(b.ddsPath());
        assertFalse(b.baked());
        assertFalse(b.hasDds());
    }
}
