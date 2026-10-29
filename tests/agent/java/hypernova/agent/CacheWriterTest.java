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

    /** M-3：稳定窗口到达后要持续落盘,而不是只写第一轮就退出。 */
    @Test
    void laterStableWindowWritesNewEntries() throws Exception {
        Path saves = tmp.resolve("saves2");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(tmp.resolve("game2"), tmp.resolve("mods2"),
                saves, saves.resolve("cache"), saves.resolve("agent.log"),
                saves.resolve("telemetry.jsonl"), cfg);
        Map<String, byte[]> map = new ConcurrentHashMap<>();
        map.put("a.B", new byte[]{1});
        CacheWriter writer = new CacheWriter(ctx, "testkey2", map, 0, 0);
        try {
            writer.start();
            // 第一轮稳定窗口(0 ms)后写入 a.B;随后加入 c.D,等下一轮窗口把它也落盘。
            writeUntilPresent(ctx, "testkey2", "a.B", 5_000);
            map.put("c.D", new byte[]{4, 5, 6});
            writeUntilPresent(ctx, "testkey2", "c.D", 5_000);
        } finally {
            writer.stop();
        }
    }

    private static void writeUntilPresent(RuntimeContext ctx, String key, String entry,
                                          long timeoutMillis) throws Exception {
        long deadline = System.currentTimeMillis() + timeoutMillis;
        CachePack.Pack p = null;
        while (System.currentTimeMillis() < deadline) {
            p = new CacheStore(ctx.cacheRoot(), 2, 1L << 30).load(key);
            if (p != null && p.entries().containsKey(entry)) return;
            Thread.sleep(50);
        }
        fail("entry " + entry + " was not persisted within " + timeoutMillis + " ms; pack=" + p);
    }
}
