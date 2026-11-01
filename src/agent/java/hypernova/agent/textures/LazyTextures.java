package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Task 1 probe state. Every queued texture still goes through the donor's
 * loadTextureAsync; counters only observe. The production skip/proxy path is
 * the M2.5 addendum.
 */
public final class LazyTextures {
    private static final AtomicLong QUEUE_TOTAL = new AtomicLong();
    private static final AtomicLong QUEUE_WOULD_SKIP = new AtomicLong();
    private static final AtomicLong LOOKUP_TOTAL = new AtomicLong();
    private static final AtomicLong DEMAND_DISTINCT = new AtomicLong();
    private static final Map<String, AtomicLong> TYPES = new ConcurrentHashMap<>();
    private static final Map<String, Long> DEMAND_FIRST = new ConcurrentHashMap<>();
    private static final AtomicBoolean WIRED = new AtomicBoolean();
    private static final AtomicBoolean SUMMARY_STARTED = new AtomicBoolean();

    private static volatile LazySkipIndex index;
    private static volatile Path skipFile;

    private static volatile boolean loadResolved;
    private static volatile Method loadAsyncMethod;
    private static volatile boolean renderResolved;
    private static volatile Field renderProgressField;
    private static volatile boolean knownResolved;
    private static volatile Field knownImagesField;

    private LazyTextures() {
    }

    public static void start(LazyTextureConfig config) {
        if (!config.probe()) return;
        skipFile = config.skipFile();
        Thread loader = new Thread(LazyTextures::loadIndex, "Hypernova-Lazy-Index");
        loader.setDaemon(true);
        loader.start();
        if (SUMMARY_STARTED.compareAndSet(false, true)) {
            Thread summary = new Thread(LazyTextures::summaryLoop, "Hypernova-Lazy-Summary");
            summary.setDaemon(true);
            summary.start();
            Runtime.getRuntime().addShutdownHook(
                    new Thread(LazyTextures::summary, "Hypernova-Lazy-Summary-Shutdown"));
        }
        AgentLog.info("lazy probe: started; skipFile=" + skipFile);
    }

    private static void loadIndex() {
        try {
            Path f = skipFile;
            if (f == null) {
                AgentLog.info("lazy probe: no skip file resolved; probe counts stay 0");
                return;
            }
            if (!Files.isRegularFile(f)) {
                AgentLog.info("lazy probe: skip file missing: " + f);
                return;
            }
            LazySkipIndex idx = LazySkipIndex.load(f);
            index = idx;
            AgentLog.info("lazy probe: index loaded paths=" + idx.size()
                    + " invalid=" + idx.invalid() + " in " + idx.loadMillis()
                    + " ms; file=" + f);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: index load failed; probe counts stay 0", t);
        }
    }

    /**
     * Called from the injected queue lambda on a texture worker, before the
     * original load. Must preserve the donor's exception semantics: any
     * Throwable from loadTextureAsync propagates to the generated catch.
     */
    public static void queue(Object loader, String type, String path) throws Throwable {
        try {
            QUEUE_TOTAL.incrementAndGet();
            TYPES.computeIfAbsent(type == null ? "" : type, k -> new AtomicLong()).incrementAndGet();
            if (WIRED.compareAndSet(false, true)) {
                AgentLog.info("lazy probe: lambda wired (first queue: type=" + type
                        + ", path=" + path + ")");
            }
            LazySkipIndex idx = index;
            if (idx != null && idx.contains(path)) {
                long n = QUEUE_WOULD_SKIP.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: would-skip " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: counter failed; continuing", t);
        }
        loadAsync(loader, type, path);
    }

    private static void loadAsync(Object loader, String type, String path) throws Throwable {
        Method m = loadAsyncMethod;
        if (m == null && !loadResolved) {
            synchronized (LazyTextures.class) {
                m = loadAsyncMethod;
                if (m == null && !loadResolved) {
                    try {
                        m = loader.getClass().getDeclaredMethod(
                                "loadTextureAsync", String.class, String.class);
                        m.setAccessible(true);
                        loadAsyncMethod = m;
                        AgentLog.info("lazy probe: loadTextureAsync resolved on "
                                + loader.getClass().getName());
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: loadTextureAsync missing; queued texture skipped", t);
                    } finally {
                        loadResolved = true;
                    }
                }
            }
        }
        if (m == null) return; // fail-open: never crash the game for a probe
        try {
            m.invoke(loader, type, path);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause == null ? e : cause;
        }
    }

    public static void markRenderProgress() {
        Field f = renderProgressField;
        if (f == null && !renderResolved) {
            synchronized (LazyTextures.class) {
                f = renderProgressField;
                if (f == null && !renderResolved) {
                    try {
                        Class<?> c = Class.forName("com.fs.starfarer.loading.ResourceLoaderState",
                                false, LazyTextures.class.getClassLoader());
                        f = c.getDeclaredField("renderProgress");
                        f.setAccessible(true);
                        renderProgressField = f;
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: renderProgress missing; progress hint disabled", t);
                    } finally {
                        renderResolved = true;
                    }
                }
            }
        }
        if (f == null) return;
        try {
            f.setBoolean(null, true);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: renderProgress set failed", t);
        }
    }

    public static void removeKnown(Object loader, String path) {
        Field f = knownImagesField;
        if (f == null && !knownResolved) {
            synchronized (LazyTextures.class) {
                f = knownImagesField;
                if (f == null && !knownResolved) {
                    try {
                        f = loader.getClass().getDeclaredField("knownImages");
                        f.setAccessible(true);
                        knownImagesField = f;
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: knownImages missing; optional cleanup disabled", t);
                    } finally {
                        knownResolved = true;
                    }
                }
            }
        }
        if (f == null) return;
        try {
            Object value = f.get(loader);
            if (value instanceof Set<?> set) set.remove(path);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: knownImages remove failed", t);
        }
    }

    /** Demand accounting for paths that a real skip implementation would proxy. */
    public static void probeLookup(String path) {
        try {
            LOOKUP_TOTAL.incrementAndGet();
            LazySkipIndex idx = index;
            if (idx == null || !idx.contains(path)) return;
            if (DEMAND_FIRST.putIfAbsent(path, System.nanoTime()) == null) {
                long n = DEMAND_DISTINCT.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: demand " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: lookup counter failed; continuing", t);
        }
    }

    /** Task 1: no proxy. The addendum replaces this with the proxy/materialize path. */
    public static Object lookup(String path) {
        return null;
    }

    private static void summaryLoop() {
        while (true) {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                return;
            }
            summary();
        }
    }

    public static void summary() {
        try {
            LazySkipIndex idx = index;
            AgentLog.info("lazy probe: summary queue=" + QUEUE_TOTAL.get()
                    + " wouldSkip=" + QUEUE_WOULD_SKIP.get()
                    + " lookups=" + LOOKUP_TOTAL.get()
                    + " demand=" + DEMAND_DISTINCT.get()
                    + " index=" + (idx == null ? "none" : idx.size())
                    + " types=" + types());
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: summary failed", t);
        }
    }

    private static String types() {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, AtomicLong> e : TYPES.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(e.getKey()).append('=').append(e.getValue().get());
        }
        return sb.append('}').toString();
    }
}
