package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * M2.5 probe + production lazy-texture state.
 *
 * <p>Probe mode only counts; every queued texture still calls loadTextureAsync.
 * Production mode skips non-L1 queue entries, registers a proxy Object with the
 * manifest dimensions, and materializes it on the first lookup from the loading
 * thread or the runtime main thread. Any shape/reflection failure disables the
 * module (fail-open); materialize failures keep the proxy and are logged.
 */
public final class LazyTextures {
    // ---- probe counters (Task 1) ----
    private static final AtomicLong QUEUE_TOTAL = new AtomicLong();
    private static final AtomicLong QUEUE_WOULD_SKIP = new AtomicLong();
    private static final AtomicLong LOOKUP_TOTAL = new AtomicLong();
    private static final AtomicLong DEMAND_DISTINCT = new AtomicLong();
    private static final Map<String, AtomicLong> TYPES = new ConcurrentHashMap<>();
    private static final Map<String, Long> DEMAND_FIRST = new ConcurrentHashMap<>();
    private static final AtomicBoolean WIRED = new AtomicBoolean();
    private static final AtomicBoolean SUMMARY_STARTED = new AtomicBoolean();
    private static final AtomicBoolean DEGRADED = new AtomicBoolean();
    private static final Set<String> QUEUED_SKIP = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_QUEUED = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_HIT = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_MISS = ConcurrentHashMap.newKeySet();

    // ---- production state ----
    private static final AtomicLong LAZY_SKIPPED = new AtomicLong();
    private static final AtomicLong LAZY_MATERIALIZED = new AtomicLong();
    private static final AtomicLong LAZY_DEFERRED = new AtomicLong();
    private static final AtomicLong LAZY_FAILED = new AtomicLong();
    private static final AtomicLong LAZY_DRAINED = new AtomicLong();
    private static final Map<String, ProxyEntry> PROXIES = new ConcurrentHashMap<>();
    private static final Map<Object, ProxyEntry> PROXY_BY_OBJ = new ConcurrentHashMap<>();
    /** Skip paths whose proxy has not been inserted into oOoO.new yet. */
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final AtomicBoolean DRAIN_WARNED = new AtomicBoolean();

    private static volatile boolean enabled;
    private static volatile boolean probe;
    private static volatile boolean disabled;
    private static volatile ProxyShape proxyShape;
    private static volatile boolean shapeResolved;

    private static volatile Method syncMethod;
    private static volatile Object loaderSingleton;
    private static volatile Field pathCacheField;
    private static volatile boolean loaderResolved;

    private static volatile Method engineRegisterMethod;
    private static volatile boolean engineRegisterResolved;

    private static volatile Thread runtimeMain;
    private static volatile Thread loadingThreadField;
    private static volatile boolean loadingThreadResolved;

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
        enabled = config.enabled();
        probe = config.probe();
        if (!enabled && !probe) return;
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
        AgentLog.info("lazy: started enabled=" + enabled + " probe=" + probe + "; skipFile=" + skipFile);
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

    public static void queue(Object loader, String type, String path) throws Throwable {
        try {
            QUEUE_TOTAL.incrementAndGet();
            TYPES.computeIfAbsent(type == null ? "" : type, k -> new AtomicLong()).incrementAndGet();
            if (WIRED.compareAndSet(false, true)) {
                AgentLog.info("lazy probe: lambda wired (first queue: type=" + type + ", path=" + path + ")");
            }
            LazySkipIndex idx = index;
            if (idx != null && idx.contains(path)) {
                QUEUED_SKIP.add(path);
                long n = QUEUE_WOULD_SKIP.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: would-skip " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: counter failed; continuing", t);
        }
        if (shouldSkip(type, path)) {
            if (registerProxy(path)) {
                LAZY_SKIPPED.incrementAndGet();
                return;
            }
            AgentLog.fail("lazy: proxy unavailable for " + path + "; loading normally",
                    new IllegalStateException("proxy registration failed"));
        }
        loadAsync(loader, type, path);
    }

    static boolean eligible(boolean enabled, boolean probe, boolean disabled,
                            LazySkipIndex index, String type, String path) {
        if (!enabled || probe || disabled) return false;
        if ("TEXTURE_ALPHA_ADDER".equals(type)) return false;
        return index != null && index.contains(path);
    }

    public static boolean shouldSkip(String type, String path) {
        try {
            if (!eligible(enabled, probe, disabled, index, type, path)) return false;
            return ensureShape();
        } catch (Throwable t) {
            AgentLog.fail("lazy: skip decision failed for " + path + "; loading normally", t);
            return false;
        }
    }

    private static boolean registerProxy(String path) {
        try {
            if (PROXIES.containsKey(path)) return true;
            LazySkipIndex idx = index;
            LazySkipIndex.Dim dim = idx == null ? null : idx.get(path);
            ProxyShape shape = proxyShape;
            if (dim == null || shape == null) return false;
            Object obj = shape.newProxy(path, dim.w(), dim.h());
            ProxyEntry entry = new ProxyEntry(path, dim.w(), dim.h(), obj);
            ProxyEntry prev = PROXIES.putIfAbsent(path, entry);
            if (prev != null) return true;
            PROXY_BY_OBJ.put(obj, entry);
            PENDING.add(path);
            if (PROXIES.size() <= 20) {
                AgentLog.info("lazy: proxy " + path + " " + dim.w() + "x" + dim.h());
            }
            return true;
        } catch (Throwable t) {
            AgentLog.fail("lazy: proxy registration failed for " + path + "; loading normally", t);
            return false;
        }
    }

    public static Object lookup(String path) {
        try {
            ProxyEntry e = PROXIES.get(path);
            if (e == null) return null;
            if (!e.ready) {
                if (canMaterialize()) {
                    materialize(e);
                } else {
                    LAZY_DEFERRED.incrementAndGet();
                }
            }
            return e.obj;
        } catch (Throwable t) {
            AgentLog.fail("lazy: lookup failed for " + path, t);
            return null;
        }
    }

    /**
     * Called from LazyProxyObject's bind/id overrides. Materializes only on the
     * loading thread or the runtime main thread; other threads see the proxy.
     */
    public static void onProxyUse(Object proxy) {
        try {
            if (proxy == null) return;
            ProxyEntry e = PROXY_BY_OBJ.get(proxy);
            if (e == null || e.ready) return;
            if (canMaterialize()) {
                materialize(e);
            } else {
                LAZY_DEFERRED.incrementAndGet();
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: proxy use failed", t);
        }
    }

    /**
     * Inserts every pending proxy into oOoO.new. Must run on the loading thread
     * (FR-Main-Loader, first step of initMods) or the runtime main thread; other
     * threads leave PENDING untouched for a later drain.
     */
    public static void drainPending() {
        try {
            if (!enabled || probe || disabled) return;
            Thread current = Thread.currentThread();
            if (current != runtimeMain && current != loadingThread()) {
                if (DRAIN_WARNED.compareAndSet(false, true)) {
                    AgentLog.info("lazy: drain skipped on " + current.getName()
                            + "; will retry on the loading/main thread");
                }
                return;
            }
            int drained = 0;
            for (String path : PENDING) {
                ProxyEntry e = PROXIES.get(path);
                if (e == null) {
                    PENDING.remove(path);
                    continue;
                }
                try {
                    registerEngineMap(path, e.obj);
                    if (PENDING.remove(path)) drained++;
                } catch (Throwable t) {
                    AgentLog.fail("lazy: engine map register failed for " + path, t);
                    break; // keep the rest pending for a later drain
                }
            }
            if (drained > 0) {
                LAZY_DRAINED.addAndGet(drained);
                AgentLog.info("lazy: drained " + drained + " proxies into oOoO.new");
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: drain failed", t);
        }
    }

    private static void registerEngineMap(String path, Object obj) throws Throwable {
        Method m = engineRegisterMethod;
        if (m == null && !engineRegisterResolved) {
            synchronized (LazyTextures.class) {
                m = engineRegisterMethod;
                if (m == null && !engineRegisterResolved) {
                    Class<?> objClass = Class.forName("com.fs.graphics.Object");
                    Class<?> repo = Class.forName("com.fs.graphics.oOoO");
                    Method found = null;
                    for (Method candidate : repo.getDeclaredMethods()) {
                        if (!"super".equals(candidate.getName())) continue;
                        if ((candidate.getModifiers() & Modifier.STATIC) == 0) continue;
                        Class<?>[] p = candidate.getParameterTypes();
                        if (p.length == 2 && p[0] == String.class && p[1] == objClass) {
                            found = candidate;
                            break;
                        }
                    }
                    if (found != null) {
                        found.setAccessible(true);
                        engineRegisterMethod = found;
                        AgentLog.info("lazy: engine texture map register resolved");
                    }
                    engineRegisterResolved = true;
                    m = found;
                }
            }
        }
        if (m == null) throw new IllegalStateException("oOoO.super(String,Object) unavailable");
        try {
            m.invoke(null, path, obj);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause == null ? e : cause;
        }
    }

    private static boolean canMaterialize() {
        Thread t = Thread.currentThread();
        if (t == runtimeMain) return true;
        Thread loading = loadingThread();
        return loading != null && t == loading;
    }

    private static Thread loadingThread() {
        Thread t = loadingThreadField;
        if (t == null && !loadingThreadResolved) {
            synchronized (LazyTextures.class) {
                t = loadingThreadField;
                if (t == null && !loadingThreadResolved) {
                    try {
                        Class<?> fileLoader = Class.forName("com.fs.util.C",
                                false, LazyTextures.class.getClassLoader());
                        Method getInstance = fileLoader.getDeclaredMethod("Ó00000");
                        getInstance.setAccessible(true);
                        Object instance = getInstance.invoke(null);
                        Field field = fileLoader.getDeclaredField("mainThread");
                        field.setAccessible(true);
                        t = (Thread) field.get(instance);
                        loadingThreadField = t;
                    } catch (Throwable t2) {
                        AgentLog.info("lazy: FileLoader.mainThread unavailable; loading-thread materialize disabled");
                    } finally {
                        loadingThreadResolved = true;
                    }
                }
            }
        }
        return t;
    }

    public static void captureMainThread(Object state) {
        try {
            if (runtimeMain != null || state == null) return;
            String name = state.getClass().getName();
            if (name.contains("launcher") || name.contains("Launcher")) return;
            runtimeMain = Thread.currentThread();
            AgentLog.info("lazy: runtime main thread captured " + runtimeMain.getName() + " from " + name);
        } catch (Throwable t) {
            AgentLog.fail("lazy: main-thread capture failed", t);
        }
    }

    private static void materialize(ProxyEntry e) {
        synchronized (e) {
            if (e.ready || e.failed) return;
            long t0 = System.nanoTime();
            try {
                Object real = syncLoad(e.path);
                ProxyShape shape = proxyShape;
                if (shape == null) throw new IllegalStateException("proxy shape unavailable");
                shape.copy(real, e.obj);
                e.ready = true;
                putPathCache(e.path, e.obj);
                long ms = (System.nanoTime() - t0) / 1_000_000L;
                long n = LAZY_MATERIALIZED.incrementAndGet();
                if (n <= 20 || ms >= 50) {
                    AgentLog.info("lazy: materialized " + e.path + " " + e.w + "x" + e.h + " in " + ms + " ms");
                }
            } catch (Throwable t) {
                long attempts = e.attempts.incrementAndGet();
                if (attempts >= 2) e.failed = true;
                LAZY_FAILED.incrementAndGet();
                AgentLog.fail("lazy: materialize failed for " + e.path + " (attempt " + attempts + ")", t);
            }
        }
    }

    private static Object syncLoad(String path) throws Throwable {
        ensureLoader();
        Method sync = syncMethod;
        Object loader = loaderSingleton;
        if (sync == null || loader == null) throw new IllegalStateException("sync loader unavailable");
        try {
            return sync.invoke(loader, null, path, 3553, 6408, 9729, 9729, false);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause == null ? e : cause;
        }
    }

    @SuppressWarnings("unchecked")
    private static void putPathCache(String path, Object obj) {
        Field field = pathCacheField;
        Object loader = loaderSingleton;
        if (field == null || loader == null) return;
        try {
            Object value = field.get(loader);
            if (value instanceof Map<?, ?>) {
                ((Map<Object, Object>) value).put(path, obj);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: path cache put failed for " + path, t);
        }
    }

    private static boolean ensureShape() {
        if (shapeResolved) return !disabled;
        synchronized (LazyTextures.class) {
            if (shapeResolved) return !disabled;
            try {
                Class<?> obj = Class.forName("com.fs.graphics.Object");
                Class<?> proxy = Class.forName("hypernova.agent.textures.LazyProxyObject");
                proxyShape = ProxyShape.resolve(obj, proxy);
                ensureLoader();
                if (syncMethod == null || loaderSingleton == null) {
                    throw new IllegalStateException("TextureLoader sync path unavailable");
                }
                AgentLog.info("lazy: shape ok; proxy + sync loader resolved");
            } catch (Throwable t) {
                disabled = true;
                AgentLog.fail("lazy: shape gate failed; lazy skip disabled", t);
            } finally {
                shapeResolved = true;
            }
            return !disabled;
        }
    }

    private static void ensureLoader() throws Exception {
        if (loaderResolved) {
            if (syncMethod == null || loaderSingleton == null) throw new IllegalStateException("loader shape");
            return;
        }
        synchronized (LazyTextures.class) {
            if (loaderResolved) {
                if (syncMethod == null || loaderSingleton == null) throw new IllegalStateException("loader shape");
                return;
            }
            try {
                Class<?> objClass = Class.forName("com.fs.graphics.Object");
                Class<?> repo = Class.forName("com.fs.graphics.oOoO");
                Method getLoader = repo.getDeclaredMethod("String");
                getLoader.setAccessible(true);
                Object loader = getLoader.invoke(null);
                if (loader == null) throw new IllegalStateException("TextureLoader singleton null");
                Method sync = null;
                for (Method method : loader.getClass().getDeclaredMethods()) {
                    if (!"o00000".equals(method.getName()) || method.getParameterCount() != 7) continue;
                    Class<?>[] p = method.getParameterTypes();
                    if (p[0] == objClass && p[1] == String.class
                            && p[2] == int.class && p[3] == int.class
                            && p[4] == int.class && p[5] == int.class
                            && p[6] == boolean.class) {
                        sync = method;
                        break;
                    }
                }
                if (sync == null) throw new NoSuchMethodException("TextureLoader.o00000 7-arg");
                sync.setAccessible(true);
                try {
                    Field cache = loader.getClass().getDeclaredField("ÔO0000");
                    if (!Map.class.isAssignableFrom(cache.getType())) {
                        throw new NoSuchFieldException("ÔO0000 not a Map");
                    }
                    cache.setAccessible(true);
                    pathCacheField = cache;
                } catch (Throwable t) {
                    AgentLog.info("lazy: TextureLoader path cache unavailable; proxy reuse disabled");
                }
                syncMethod = sync;
                loaderSingleton = loader;
                AgentLog.info("lazy: sync loader resolved on " + loader.getClass().getName());
            } finally {
                loaderResolved = true;
            }
        }
    }

    private static void loadAsync(Object loader, String type, String path) throws Throwable {
        Method m = loadAsyncMethod;
        if (m == null && !loadResolved) {
            synchronized (LazyTextures.class) {
                m = loadAsyncMethod;
                if (m == null && !loadResolved) {
                    try {
                        m = loader.getClass().getDeclaredMethod("loadTextureAsync", String.class, String.class);
                        m.setAccessible(true);
                        loadAsyncMethod = m;
                        AgentLog.info("lazy probe: loadTextureAsync resolved on " + loader.getClass().getName());
                    } catch (Throwable t) {
                        DEGRADED.set(true);
                        AgentLog.fail("lazy probe: loadTextureAsync missing; queued texture skipped", t);
                    } finally {
                        loadResolved = true;
                    }
                }
            }
        }
        if (m == null) return;
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

    public static void probeLookup(String path) {
        try {
            LOOKUP_TOTAL.incrementAndGet();
            LazySkipIndex idx = index;
            if (idx == null || !idx.contains(path)) return;
            if (DEMAND_FIRST.putIfAbsent(path, System.nanoTime()) == null) {
                long n = DEMAND_DISTINCT.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: demand " + path);
            }
            if (QUEUED_SKIP.contains(path)) DEMAND_QUEUED.add(path);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: lookup counter failed; continuing", t);
        }
    }

    public static void probeResult(String path, Object value) {
        try {
            if (path == null || !QUEUED_SKIP.contains(path)) return;
            if (value != null) {
                DEMAND_HIT.add(path);
                noteEngineHit(path, value);
            } else {
                DEMAND_MISS.add(path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: result counter failed; continuing", t);
        }
    }

    /** Absorbs a real object that someone registers for a skipped path. */
    public static void onRegister(String path, Object value) {
        try {
            if (path == null || value == null) return;
            ProxyEntry e = PROXIES.get(path);
            if (e == null || e.ready || e.obj == value) return;
            synchronized (e) {
                if (e.ready || e.obj == value) return;
                ProxyShape shape = proxyShape;
                if (shape == null) return;
                shape.copy(value, e.obj);
                e.ready = true;
                long n = LAZY_MATERIALIZED.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy: materialized via register " + path);
            }
        } catch (Throwable t) {
            LAZY_FAILED.incrementAndGet();
            AgentLog.fail("lazy: register copy failed for " + path, t);
        }
    }

    private static void noteEngineHit(String path, Object value) {
        try {
            if (value == null) return;
            ProxyEntry e = PROXIES.get(path);
            if (e == null || e.ready || e.obj == value) return;
            synchronized (e) {
                if (e.ready || e.obj == value) return;
                ProxyShape shape = proxyShape;
                if (shape == null) return;
                shape.copy(value, e.obj);
                e.ready = true;
                long n = LAZY_MATERIALIZED.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy: materialized via engine hit " + path);
            }
        } catch (Throwable t) {
            LAZY_FAILED.incrementAndGet();
            AgentLog.fail("lazy: engine-hit copy failed for " + path, t);
        }
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
            Thread lt = loadingThread();
            AgentLog.info("lazy probe: summary queue=" + QUEUE_TOTAL.get()
                    + " wouldSkip=" + QUEUE_WOULD_SKIP.get()
                    + " lookups=" + LOOKUP_TOTAL.get()
                    + " demand=" + DEMAND_DISTINCT.get()
                    + " index=" + (idx == null ? "none" : idx.size())
                    + " types=" + types()
                    + " queuedSkip=" + QUEUED_SKIP.size()
                    + " demandQueued=" + DEMAND_QUEUED.size()
                    + " hits=" + DEMAND_HIT.size()
                    + " misses=" + DEMAND_MISS.size()
                    + " degraded=" + (DEGRADED.get() ? 1 : 0)
                    + " skipped=" + LAZY_SKIPPED.get()
                    + " proxies=" + PROXIES.size()
                    + " materialized=" + LAZY_MATERIALIZED.get()
                    + " deferred=" + LAZY_DEFERRED.get()
                    + " pending=" + PENDING.size()
                    + " drained=" + LAZY_DRAINED.get()
                    + " failed=" + LAZY_FAILED.get()
                    + " disabled=" + (disabled ? 1 : 0)
                    + " main=" + (runtimeMain == null ? "none" : runtimeMain.getName())
                    + " loading=" + (lt == null ? "none" : lt.getName()));
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

    private static final class ProxyEntry {
        final String path;
        final int w;
        final int h;
        final Object obj;
        volatile boolean ready;
        volatile boolean failed;
        final AtomicLong attempts = new AtomicLong();

        ProxyEntry(String path, int w, int h, Object obj) {
            this.path = path;
            this.w = w;
            this.h = h;
            this.obj = obj;
        }
    }
}
