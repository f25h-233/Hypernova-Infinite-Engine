package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.junit.jupiter.api.Assertions.*;

class CacheWriterTest {
    @TempDir Path tmp;

    @Test
    void flushWritesNewEntries() throws Exception {
        Path saves = tmp.resolve("saves");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(tmp.resolve("game"), tmp.resolve("mods"),
                saves, saves.resolve("cache"), saves.resolve("agent.log"),
                saves.resolve("telemetry.jsonl"), cfg);
        Map<String, byte[]> map = new ConcurrentHashMap<>();
        map.put("a.B", new byte[]{1, 2, 3});
        CacheWriter writer = new CacheWriter(ctx, "testkey", map, 0, 0);
        writer.flushNow();
        CachePack.Pack p = new CacheStore(ctx.cacheRoot(), 2, 1L << 30).load("testkey");
        assertNotNull(p);
        assertArrayEquals(new byte[]{1, 2, 3}, p.entries().get("a.B"));
    }
}
