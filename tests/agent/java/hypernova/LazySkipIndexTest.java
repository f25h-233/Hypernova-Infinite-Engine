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
        assertEquals(new LazySkipIndex.Dim(10, 20), idx.get("graphics/a.png"));
        assertEquals(new LazySkipIndex.Dim(3, 4), idx.get("graphics/b c.png"));
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
}
