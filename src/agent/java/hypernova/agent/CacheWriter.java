package hypernova.agent;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CacheWriter {
    private final RuntimeContext ctx;
    private final String key;
    private final Map<String, byte[]> map;
    private final long stableMillis;
    private final AtomicBoolean started = new AtomicBoolean();
    private volatile int lastWrittenSize;
    private volatile boolean stopped;

    public CacheWriter(RuntimeContext ctx, String key, Map<String, byte[]> map,
                       int preloadedCount, long stableMillis) {
        this.ctx = ctx;
        this.key = key;
        this.map = map;
        this.lastWrittenSize = preloadedCount;
        this.stableMillis = stableMillis;
    }

    public void start() {
        if (!started.compareAndSet(false, true)) return;
        Thread t = new Thread(this::run, "Hypernova-ScriptCache-Writer");
        t.setDaemon(true);
        t.start();
    }

    private void run() {
        int lastSize = map.size();
        long changedAt = System.currentTimeMillis();
        while (!stopped) {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                return;
            }
            int size = map.size();
            if (size != lastSize) {
                lastSize = size;
                changedAt = System.currentTimeMillis();
                continue;
            }
            if (System.currentTimeMillis() - changedAt >= stableMillis) {
                if (size > lastWrittenSize) flushNow();
                return;
            }
        }
    }

    public synchronized void flushNow() {
        if (map.size() == lastWrittenSize) return;
        Map<String, byte[]> snapshot = new HashMap<>(map);
        long t0 = System.nanoTime();
        try {
            new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                    ctx.config().cacheMaxBytes()).save(key, snapshot);
            lastWrittenSize = snapshot.size();
            long ms = (System.nanoTime() - t0) / 1_000_000;
            long bytes = snapshot.values().stream().mapToLong(a -> a.length).sum();
            AgentLog.info("scripts cache written: key=" + key + ", entries="
                    + snapshot.size() + ", bytes=" + bytes + ", in " + ms + " ms");
            ctx.telemetry().event("write", key, snapshot.size(), bytes, ms);
        } catch (Throwable t) {
            AgentLog.fail("scripts cache write failed", t);
            ctx.telemetry().event("write-error", key, 0, 0, 0);
        }
    }

    public void stop() {
        stopped = true;
    }
}
