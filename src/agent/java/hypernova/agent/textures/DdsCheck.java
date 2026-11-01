package hypernova.agent.textures;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Pure pre-validation for VOpt BC7 DDS files. FR's DDS path reads the whole
 * file and uploads it on the render thread; a bad file becomes an unrecoverable
 * AsyncException/isStateCorrupted. Every check here must pass before
 * DDSIntegration.commitTexture is called.
 */
public final class DdsCheck {
    static final int HEADER_BYTES = 148;
    static final int DXGI_FORMAT_BC7 = 98;

    public record Result(boolean ok, String reason, int width, int height, int dxgi) {
    }

    private DdsCheck() {
    }

    public static Result check(Path file, int expectedWidth, int expectedHeight) {
        if (file == null) return new Result(false, "no dds path", 0, 0, 0);
        if (!Files.isRegularFile(file)) return new Result(false, "missing", 0, 0, 0);
        final long size;
        final byte[] b = new byte[HEADER_BYTES];
        try {
            size = Files.size(file);
            try (InputStream in = Files.newInputStream(file)) {
                int n = in.readNBytes(b, 0, HEADER_BYTES);
                if (n < HEADER_BYTES) {
                    return new Result(false, "short header " + n, 0, 0, 0);
                }
            }
        } catch (IOException e) {
            return new Result(false, "read failed: " + e, 0, 0, 0);
        }
        if (b[0] != 'D' || b[1] != 'D' || b[2] != 'S' || b[3] != ' ') {
            return new Result(false, "bad magic", 0, 0, 0);
        }
        int headerSize = le32(b, 4);
        if (headerSize != 124) {
            return new Result(false, "bad header size " + headerSize, 0, 0, 0);
        }
        int height = le32(b, 12);
        int width = le32(b, 16);
        if (!"DX10".equals(new String(b, 84, 4, StandardCharsets.US_ASCII))) {
            return new Result(false, "not DX10", width, height, 0);
        }
        int dxgi = le32(b, 128);
        if (dxgi != DXGI_FORMAT_BC7) {
            return new Result(false, "dxgi " + dxgi, width, height, dxgi);
        }
        if (width <= 0 || height <= 0) {
            return new Result(false, "bad dims " + width + "x" + height, width, height, dxgi);
        }
        if (width != expectedWidth || height != expectedHeight) {
            return new Result(false, "dims " + width + "x" + height
                    + " != " + expectedWidth + "x" + expectedHeight, width, height, dxgi);
        }
        long blocks = ((width + 3L) / 4L) * ((height + 3L) / 4L);
        long minBytes = HEADER_BYTES + blocks * 16L;
        if (size < minBytes) {
            return new Result(false, "short dds data " + size + " < " + minBytes,
                    width, height, dxgi);
        }
        return new Result(true, "ok", width, height, dxgi);
    }

    private static int le32(byte[] b, int o) {
        return (b[o] & 0xff) | ((b[o + 1] & 0xff) << 8)
                | ((b[o + 2] & 0xff) << 16) | ((b[o + 3] & 0xff) << 24);
    }
}
