package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FileIndexTest {

    private static final String FR_VERSION = "0.9.7rc2";
    private static final String SHAPE_STAMP = "C$Oo|enum|String|boolean|File,Location";

    @TempDir
    Path tmp;

    private static FileIndex sample(Path root) {
        return new FileIndex(FR_VERSION, SHAPE_STAMP,
                List.of(new FileIndex.Location("DIRECTORY", root.toString(), true)),
                List.of(new FileIndex.Dir(root.toString(), root.toFile().lastModified())),
                List.of(new FileIndex.Entry("graphics/a.png",
                        root.resolve("graphics/a.png").toString(), 0)));
    }

    @Test
    void roundTripsStampsAndPayload() throws IOException {
        Path file = tmp.resolve("idx.gz");
        FileIndex in = sample(tmp);
        in.write(file);
        FileIndex out = FileIndex.read(file, FR_VERSION, SHAPE_STAMP);
        assertNotNull(out);
        assertEquals(FR_VERSION, out.frVersion());
        assertEquals(SHAPE_STAMP, out.shapeStamp());
        assertEquals(in.locations(), out.locations());
        assertEquals(in.dirs(), out.dirs());
        assertEquals(in.entries(), out.entries());
    }

    @Test
    void wrongFrVersionIsNull() throws IOException {
        Path file = tmp.resolve("version.gz");
        sample(tmp).write(file);
        assertNull(FileIndex.read(file, "0.9.5", SHAPE_STAMP));
    }

    @Test
    void wrongShapeStampIsNull() throws IOException {
        Path file = tmp.resolve("shape.gz");
        sample(tmp).write(file);
        assertNull(FileIndex.read(file, FR_VERSION, "Different|shape"));
    }

    @Test
    void missingFileIsNull() {
        assertNull(FileIndex.read(tmp.resolve("absent.gz"), FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void corruptGzipIsNull() throws IOException {
        Path file = tmp.resolve("bad.gz");
        Files.write(file, new byte[]{1, 2, 3, 4, 5});
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void truncatedGzipIsNull() throws IOException {
        Path file = tmp.resolve("trunc.gz");
        sample(tmp).write(file);
        byte[] all = Files.readAllBytes(file);
        Files.write(file, java.util.Arrays.copyOf(all, all.length / 2));
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void wrongMagicIsNull() throws IOException {
        Path file = tmp.resolve("magic.gz");
        try (java.util.zip.GZIPOutputStream out =
                     new java.util.zip.GZIPOutputStream(Files.newOutputStream(file))) {
            out.write(new byte[]{9, 9, 9, 9, 9, 9, 9, 9});
        }
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
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

    @FunctionalInterface
    private interface GzipBody {
        void write(DataOutputStream out) throws IOException;
    }

    private Path gzipFile(String name, GzipBody body) throws IOException {
        Path file = tmp.resolve(name);
        try (DataOutputStream out = new DataOutputStream(
                new java.io.BufferedOutputStream(
                        new java.util.zip.GZIPOutputStream(Files.newOutputStream(file))))) {
            body.write(out);
        }
        return file;
    }

    /** Writes the full VERSION 2 header so body-guard tests reach the body. */
    private static void header(DataOutputStream out) throws IOException {
        out.writeInt(FileIndex.MAGIC);
        out.writeInt(FileIndex.VERSION);
        writeString(out, FR_VERSION);
        writeString(out, SHAPE_STAMP);
    }

    private static void writeString(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    @Test
    void wrongVersionIsNull() throws IOException {
        Path file = gzipFile("version.gz", out -> {
            out.writeInt(FileIndex.MAGIC);
            out.writeInt(FileIndex.VERSION + 1);
            // A reader without the version guard would consume the next word as
            // the FR-version string length; a zero length decodes successfully.
            out.writeInt(0);
            out.writeInt(0);
            out.writeInt(0); // location count
            out.writeInt(0); // dirs
            out.writeInt(0); // entries
        });
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void negativeCountIsNull() throws IOException {
        Path file = gzipFile("count-negative.gz", out -> {
            header(out);
            out.writeInt(-1); // location count
        });
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void oversizedCountIsNull() throws IOException {
        Path file = gzipFile("count-huge.gz", out -> {
            header(out);
            int count = 2_000_001; // MAX_RECORDS + 1
            out.writeInt(count);
            // The body is complete, so removing the upper-bound guard would
            // decode successfully (non-null) instead of returning null.
            for (int i = 0; i < count; i++) {
                out.writeInt(0); // type length
                out.writeInt(0); // path length
                out.writeBoolean(false); // isMod
            }
            out.writeInt(0); // dirs
            out.writeInt(0); // entries
        });
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void negativeStringLengthIsNull() throws IOException {
        Path file = gzipFile("string-negative.gz", out -> {
            header(out);
            out.writeInt(1); // location count
            out.writeInt(-1); // type length
        });
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }

    @Test
    void oversizedStringLengthIsNull() throws IOException {
        Path file = gzipFile("string-huge.gz", out -> {
            header(out);
            out.writeInt(1); // location count
            out.writeInt((1 << 20) + 1); // MAX_STRING + 1
            out.write(new byte[(1 << 20) + 1]); // full bytes for a successful decode
            out.writeInt(0); // path length
            out.writeBoolean(false); // isMod
            out.writeInt(0); // dirs
            out.writeInt(0); // entries
        });
        assertNull(FileIndex.read(file, FR_VERSION, SHAPE_STAMP));
    }
}
