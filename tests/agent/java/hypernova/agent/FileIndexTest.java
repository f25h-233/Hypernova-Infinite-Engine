package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FileIndexTest {

    @TempDir
    Path tmp;

    private static FileIndex sample(Path root) {
        return new FileIndex(
                List.of(new FileIndex.Location("DIRECTORY", root.toString(), true)),
                List.of(new FileIndex.Dir(root.toString(), root.toFile().lastModified())),
                List.of(new FileIndex.Entry("graphics/a.png",
                        root.resolve("graphics/a.png").toString(), 0)));
    }

    @Test
    void roundTrips() throws IOException {
        Path file = tmp.resolve("idx.gz");
        FileIndex in = sample(tmp);
        in.write(file);
        FileIndex out = FileIndex.read(file);
        assertNotNull(out);
        assertEquals(in.locations(), out.locations());
        assertEquals(in.dirs(), out.dirs());
        assertEquals(in.entries(), out.entries());
    }

    @Test
    void missingFileIsNull() {
        assertNull(FileIndex.read(tmp.resolve("absent.gz")));
    }

    @Test
    void corruptGzipIsNull() throws IOException {
        Path file = tmp.resolve("bad.gz");
        Files.write(file, new byte[]{1, 2, 3, 4, 5});
        assertNull(FileIndex.read(file));
    }

    @Test
    void truncatedGzipIsNull() throws IOException {
        Path file = tmp.resolve("trunc.gz");
        sample(tmp).write(file);
        byte[] all = Files.readAllBytes(file);
        Files.write(file, java.util.Arrays.copyOf(all, all.length / 2));
        assertNull(FileIndex.read(file));
    }

    @Test
    void wrongMagicIsNull() throws IOException {
        Path file = tmp.resolve("magic.gz");
        try (java.util.zip.GZIPOutputStream out =
                     new java.util.zip.GZIPOutputStream(Files.newOutputStream(file))) {
            out.write(new byte[]{9, 9, 9, 9, 9, 9, 9, 9});
        }
        assertNull(FileIndex.read(file));
    }

    @Test
    void detectsChangedDirMtime() throws IOException {
        Path root = tmp.resolve("mods");
        Files.createDirectories(root);
        FileIndex idx = sample(root);
        assertNull(idx.firstMismatchedDir(), "fresh mtime must match");
        Files.createFile(root.resolve("new.txt"));
        // Windows directory mtime granularity can be coarse; wait one tick.
        long t = System.currentTimeMillis();
        while (System.currentTimeMillis() == t) Thread.onSpinWait();
        root.toFile().setLastModified(System.currentTimeMillis());
        assertNotNull(idx.firstMismatchedDir(), "a changed directory must invalidate the index");
    }

    @Test
    void missingDirIsMismatch() {
        Path root = tmp.resolve("gone");
        FileIndex idx = sample(root);
        assertNotNull(idx.firstMismatchedDir());
    }
}
