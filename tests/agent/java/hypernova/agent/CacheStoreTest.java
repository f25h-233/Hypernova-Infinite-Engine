package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CacheStoreTest {
    @TempDir Path tmp;

    @Test
    void saveLoadAndCleanupOlderGenerations() throws Exception {
        CacheStore store = new CacheStore(tmp, 2, 1L << 30);
        Map<String, byte[]> m1 = Map.of("a.B", new byte[]{1});
        Map<String, byte[]> m2 = Map.of("a.C", new byte[]{2});
        store.save("k1", m1);
        Thread.sleep(20);
        store.save("k2", m2);
        Thread.sleep(20);
        store.save("k3", m2);
        assertNotNull(store.load("k3"));
        assertFalse(Files.exists(tmp.resolve("k1")), "oldest generation must be deleted");
        assertTrue(Files.exists(tmp.resolve("k2")));
        assertTrue(Files.exists(tmp.resolve("k3")));
    }

    @Test
    void corruptPackLoadsNull() throws Exception {
        CacheStore store = new CacheStore(tmp, 2, 1L << 30);
        store.save("k", Map.of("a.B", new byte[]{1, 2, 3}));
        Path pack = tmp.resolve("k/classes.pack");
        byte[] bytes = Files.readAllBytes(pack);
        bytes[bytes.length - 1] ^= 1;
        Files.write(pack, bytes);
        assertNull(store.load("k"));
    }
}
