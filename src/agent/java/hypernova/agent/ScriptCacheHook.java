package hypernova.agent;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class ScriptCacheHook {
    private static final AtomicInteger PRELOAD_CALLS = new AtomicInteger();
    private static final LongAdder FINDS = new LongAdder();
    private static final LongAdder HITS = new LongAdder();
    private static final LongAdder MISSES = new LongAdder();
    private static final AtomicLong FIRST = new AtomicLong(0);
    private static final AtomicLong LAST = new AtomicLong(0);
    private static final Set<Object> PRELOADED = ConcurrentHashMap.newKeySet();
    private static final List<String> MISS_SAMPLE =
            Collections.synchronizedList(new ArrayList<>());
    private static volatile RuntimeContext context;
    private static volatile Map<String, byte[]> currentMap;
    private static volatile String currentKey = "";
    private static volatile CacheWriter writer;

    private ScriptCacheHook() {
    }

    public static void preload(Object loader) {
        PRELOAD_CALLS.incrementAndGet();
        try {
            RuntimeContext ctx = context;
            if (ctx == null) {
                AgentLog.info("no runtime context; preload skipped");
                return;
            }
            preload(loader, ctx);
        } catch (Throwable t) {
            AgentLog.fail("preload failed", t);
        }
    }

    static void preload(Object loader, RuntimeContext ctx) {
        if (loader == null || ctx == null || !ctx.config().scriptsEnabled()) return;
        if (!PRELOADED.add(loader)) return;
        Map<String, byte[]> map = bytecodeCache(loader);
        if (map == null) {
            AgentLog.info("bytecodeCache field not found; scripts cache disabled");
            return;
        }
        currentMap = map;
        context = ctx;
        long t0 = System.nanoTime();
        String key = ScriptCacheKey.compute(ctx).id();
        currentKey = key;
        CacheStore store = new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                ctx.config().cacheMaxBytes());
        CachePack.Pack pack = store.load(key);
        long ms = (System.nanoTime() - t0) / 1_000_000;
        if (pack != null) {
            map.putAll(pack.entries());
            AgentLog.info("scripts cache preloaded: key=" + key + ", entries="
                    + pack.entries().size() + ", bytes=" + pack.bytes() + ", in " + ms + " ms");
            ctx.telemetry().event("preload", key, pack.entries().size(), pack.bytes(), ms);
        } else {
            AgentLog.info("scripts cache cold: key=" + key + ", preloaded=0, in " + ms + " ms");
            ctx.telemetry().event("preload-miss", key, 0, 0, ms);
        }
        writer = new CacheWriter(ctx, key, map, map.size(), 5_000);
        writer.start();
    }

    public static void onFindClass(Object loader, String name) {
        // 本方法由 transformer 注入真实 findClass 入口，任何异常都不能漏回游戏。
        // 计数语义：每次调用恰好计一次 find（先计再做事），异常时仍保住分母，
        // 且用 counted 防止 catch 里重复计数（否则 find_calls 会被放大）。
        boolean counted = false;
        try {
            long now = System.nanoTime();
            FIRST.compareAndSet(0, now);
            LAST.set(now);
            FINDS.increment();
            counted = true;
            Map<String, byte[]> map = currentMap;
            if (map != null && map.containsKey(name)) {
                HITS.increment();
            } else {
                MISSES.increment();
                if (MISS_SAMPLE.size() < 50) MISS_SAMPLE.add(name);
            }
        } catch (Throwable t) {
            if (!counted) {
                try {
                    FINDS.increment();
                } catch (Throwable ignored) {
                    // 连计数都失败时无能为力，绝不外抛
                }
            }
            try {
                AgentLog.fail("onFindClass hook failed", t);
            } catch (Throwable ignored) {
                // 日志本身也可能失败（SecurityException/OOM）；钩子绝不能把异常抛回游戏
            }
        }
    }

    public static void shutdown() {
        CacheWriter w = writer;
        if (w != null) w.flushNow();
        RuntimeContext ctx = context;
        if (ctx != null) {
            ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                    spanMillis(), currentMap == null ? 0 : currentMap.size());
            ctx.telemetry().close();
        }
    }

    public static void summaryTick() {
        RuntimeContext ctx = context;
        if (ctx == null) return;
        ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                spanMillis(), currentMap == null ? 0 : currentMap.size());
    }

    private static Map<String, byte[]> bytecodeCache(Object loader) {
        try {
            Field f = loader.getClass().getDeclaredField("bytecodeCache");
            f.setAccessible(true);
            Object value = f.get(loader);
            if (value instanceof Map<?, ?> m) {
                @SuppressWarnings("unchecked")
                Map<String, byte[]> typed = (Map<String, byte[]>) m;
                return typed;
            }
        } catch (Throwable t) {
            AgentLog.fail("cannot access bytecodeCache", t);
        }
        return null;
    }

    static void setContext(RuntimeContext ctx) { context = ctx; }
    static long preloadCalls() { return PRELOAD_CALLS.get(); }
    static long findCalls() { return FINDS.sum(); }
    static long hits() { return HITS.sum(); }
    static long misses() { return MISSES.sum(); }
    static String currentKey() { return currentKey; }
    static List<String> missSample() { return new ArrayList<>(MISS_SAMPLE); }

    static long spanMillis() {
        long first = FIRST.get();
        long last = LAST.get();
        return first == 0 || last < first ? 0 : (last - first) / 1_000_000;
    }

    static void resetForTest() {
        PRELOAD_CALLS.set(0);
        FINDS.reset();
        HITS.reset();
        MISSES.reset();
        FIRST.set(0);
        LAST.set(0);
        PRELOADED.clear();
        MISS_SAMPLE.clear();
        context = null;
        currentMap = null;
        currentKey = "";
        writer = null;
    }
}
