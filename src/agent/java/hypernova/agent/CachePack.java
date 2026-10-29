package hypernova.agent;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.CRC32;

public final class CachePack {
    public record Pack(Map<String, byte[]> entries, long bytes) {
    }

    static final int MAGIC = 0x484E5031; // "HNP1"
    static final int VERSION = 1;
    static final int MAX_NAME = 4096;
    static final int MAX_DATA = 50 * 1024 * 1024;
    static final int MAX_COUNT = 200_000;

    private CachePack() {
    }

    public static Pack read(Path file) {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(file), 1 << 16))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION) return null;
            int count = in.readInt();
            if (count < 0 || count > MAX_COUNT) return null;
            Map<String, byte[]> map = new HashMap<>(Math.max(16, count * 2));
            CRC32 crc = new CRC32();
            long bytes = 0;
            for (int i = 0; i < count; i++) {
                int nameLen = in.readInt();
                if (nameLen < 1 || nameLen > MAX_NAME) return null;
                byte[] name = in.readNBytes(nameLen);
                if (name.length != nameLen) return null;
                int dataLen = in.readInt();
                if (dataLen < 0 || dataLen > MAX_DATA) return null;
                byte[] data = in.readNBytes(dataLen);
                if (data.length != dataLen) return null;
                crc.update(name);
                crc.update(data);
                map.put(new String(name, StandardCharsets.UTF_8), data);
                bytes += dataLen;
            }
            long expected = in.readLong();
            return expected == crc.getValue() ? new Pack(map, bytes) : null;
        } catch (Throwable t) {
            AgentLog.fail("cache pack read failed: " + file, t);
            return null;
        }
    }

    public static void write(Path file, Map<String, byte[]> entries) throws IOException {
        Files.createDirectories(file.getParent());
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        CRC32 crc = new CRC32();
        try (OutputStream fos = Files.newOutputStream(tmp);
             BufferedOutputStream bos = new BufferedOutputStream(fos, 1 << 16);
             DataOutputStream out = new DataOutputStream(bos)) {
            out.writeInt(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(entries.size());
            for (Map.Entry<String, byte[]> e : entries.entrySet()) {
                byte[] name = e.getKey().getBytes(StandardCharsets.UTF_8);
                byte[] data = e.getValue();
                out.writeInt(name.length);
                out.write(name);
                out.writeInt(data.length);
                out.write(data);
                crc.update(name);
                crc.update(data);
            }
            out.flush();
            bos.flush();
            fos.write(ByteBuffer.allocate(8).putLong(crc.getValue()).array());
            fos.flush();
        }
        Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
    }
}
