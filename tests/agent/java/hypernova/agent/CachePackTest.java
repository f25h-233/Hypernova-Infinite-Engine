package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CachePackTest {
    @TempDir Path tmp;

    @Test
    void roundTrip() throws Exception {
        Map<String, byte[]> in = new LinkedHashMap<>();
        in.put("a.B", new byte[]{1, 2, 3});
        in.put("a.C$1", new byte[]{4});
        Path p = tmp.resolve("x/classes.pack");
        CachePack.write(p, in);
        CachePack.Pack out = CachePack.read(p);
        assertNotNull(out);
        assertEquals(2, out.entries().size());
        assertArrayEquals(new byte[]{1, 2, 3}, out.entries().get("a.B"));
        assertEquals(4, out.bytes());
    }

    @Test
    void corruptTrailingCrcReturnsNull() throws Exception {
        Path p = tmp.resolve("y/classes.pack");
        CachePack.write(p, Map.of("a.B", new byte[]{1, 2, 3}));
        byte[] bytes = Files.readAllBytes(p);
        bytes[bytes.length - 1] ^= 0x7F;
        Files.write(p, bytes);
        assertNull(CachePack.read(p));
    }

    @Test
    void truncatedReturnsNull() throws Exception {
        Path p = tmp.resolve("z/classes.pack");
        CachePack.write(p, Map.of("a.B", new byte[]{1, 2, 3}));
        byte[] bytes = Files.readAllBytes(p);
        Files.write(p, Arrays.copyOf(bytes, bytes.length - 4));
        assertNull(CachePack.read(p));
    }
}
