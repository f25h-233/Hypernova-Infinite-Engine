package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DdsCheckTest {
    private static byte[] dds(int w, int h, int dxgi, String magic, String fourCC, int dataBytes) {
        byte[] b = new byte[148 + dataBytes];
        System.arraycopy(magic.getBytes(StandardCharsets.US_ASCII), 0, b, 0, 4);
        ByteBuffer bb = ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN);
        bb.putInt(4, 124);
        bb.putInt(12, h);
        bb.putInt(16, w);
        System.arraycopy(fourCC.getBytes(StandardCharsets.US_ASCII), 0, b, 84, 4);
        bb.putInt(128, dxgi);
        return b;
    }

    @Test
    void acceptsValidBc7(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("a.dds");
        Files.write(f, dds(810, 500, 98, "DDS ", "DX10", 406_148));
        DdsCheck.Result r = DdsCheck.check(f, 810, 500);
        assertTrue(r.ok(), r.reason());
        assertEquals(810, r.width());
        assertEquals(500, r.height());
        assertEquals(98, r.dxgi());
    }

    @Test
    void rejectsBadMagicHeaderFormatAndDims(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("a.dds");
        Files.write(f, dds(8, 8, 98, "BAD!", "DX10", 1000));
        assertFalse(DdsCheck.check(f, 8, 8).ok());
        Files.write(f, dds(8, 8, 98, "DDS ", "DX9 ", 1000));
        assertFalse(DdsCheck.check(f, 8, 8).ok());
        Files.write(f, dds(8, 8, 99, "DDS ", "DX10", 1000));
        assertFalse(DdsCheck.check(f, 8, 8).ok());
        Files.write(f, dds(8, 8, 98, "DDS ", "DX10", 1000));
        assertFalse(DdsCheck.check(f, 9, 8).ok());
    }

    @Test
    void rejectsShortHeaderAndShortData(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("short.dds");
        Files.write(f, new byte[100]);
        assertFalse(DdsCheck.check(f, 8, 8).ok());
        Files.write(f, dds(64, 64, 98, "DDS ", "DX10", 4));
        assertFalse(DdsCheck.check(f, 64, 64).ok());
        assertFalse(DdsCheck.check(dir.resolve("missing.dds"), 64, 64).ok());
    }
}
