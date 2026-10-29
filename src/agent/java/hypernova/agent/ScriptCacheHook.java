package hypernova.agent;

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
    private static volatile RuntimeContext context;
    private static volatile String currentKey = "";

    private ScriptCacheHook() {
    }

    public static void preload(Object loader) {
        PRELOAD_CALLS.incrementAndGet();
        AgentLog.info("preload hook fired: "
                + (loader == null ? "null" : loader.getClass().getName()));
    }

    public static void onFindClass(Object loader, String name) {
        long now = System.nanoTime();
        FIRST.compareAndSet(0, now);
        LAST.set(now);
        FINDS.increment();
        MISSES.increment();
    }

    public static void shutdown() {
        summaryTick();
    }

    public static void summaryTick() {
        RuntimeContext ctx = context;
        if (ctx != null) {
            ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                    spanMillis(), 0);
        }
    }

    static void setContext(RuntimeContext ctx) { context = ctx; }
    static long preloadCalls() { return PRELOAD_CALLS.get(); }
    static long findCalls() { return FINDS.sum(); }
    static long hits() { return HITS.sum(); }
    static long misses() { return MISSES.sum(); }

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
        context = null;
        currentKey = "";
    }
}
