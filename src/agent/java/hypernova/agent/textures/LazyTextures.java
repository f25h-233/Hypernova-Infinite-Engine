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
    private static final AtomicLong LAZY_REREGISTERED = new AtomicLong();
    private static final Map<String, ProxyEntry> PROXIES = new ConcurrentHashMap<>();
    private static final Map<Object, ProxyEntry> PROXY_BY_OBJ = new ConcurrentHashMap<>();
    /** Skip paths whose proxy has not been inserted into oOoO.new yet. */
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final AtomicBoolean LOADING_WARNED = new AtomicBoolean();
    /** Fail-open is one-shot: concurrent drain/register failures must not reload twice. */
    private static final AtomicBoolean FAILING_OPEN = new AtomicBoolean();

    // Wiring armed flags: set by the transformers when their hook is actually
    // applied. ensureShape() force-loads every target and refuses to skip if any
    // hook is missing, so version drift fails open instead of leaving 45k paths
    // out of oOoO.new.
    private static volatile boolean queueArmed;
    private static volatile boolean registerArmed;
    private static volatile boolean drainArmed;
    private static volatile boolean threadArmed;
    private static volatile long loadingResolveNanos;

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
            if (registerProxy(path, type)) {
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

    // ---- wiring armed flags (set by the transformers when a hook is applied) ----

    static void noteQueueArmed() {
        queueArmed = true;
    }

    static void noteRegisterArmed() {
        registerArmed = true;
    }

    static void noteDrainArmed() {
        drainArmed = true;
    }

    static void noteThreadArmed() {
        threadArmed = true;
    }

    static boolean wiringArmed() {
        return queueArmed && registerArmed && drainArmed && threadArmed;
    }

    static boolean queueArmed() {
        return queueArmed;
    }

    static boolean registerArmed() {
        return registerArmed;
    }

    static boolean drainArmed() {
        return drainArmed;
    }

    static boolean threadArmed() {
        return threadArmed;
    }

    static void resetWiringForTest() {
        queueArmed = false;
        registerArmed = false;
        drainArmed = false;
        threadArmed = false;
    }

    /**
     * Shape gate for the wiring the skip path depends on. Pure so the hook
     * matrix can be tested without loading game classes. objectType is
     * com.fs.graphics.Object; proxyType is LazyProxyObject, which must itself
     * declare both overrides (otherwise bind/id never materializes).
     */
    static boolean wiringOk(boolean queue, boolean register, boolean drain, boolean thread,
                            Method engineRegister, Class<?> objectType, Class<?> proxyType) {
        if (!queue || !register || !drain || !thread || engineRegister == null) return false;
        try {
            objectType.getMethod("Ø00000");
            objectType.getMethod("ö00000");
            return proxyType.getMethod("Ø00000").getDeclaringClass() == proxyType
                    && proxyType.getMethod("ö00000").getDeclaringClass() == proxyType;
        } catch (Throwable t) {
            return false;
        }
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

    private static boolean registerProxy(String path, String type) {
        try {
            if (PROXIES.containsKey(path)) return true;
            LazySkipIndex idx = index;
            LazySkipIndex.Dim dim = idx == null ? null : idx.get(path);
            ProxyShape shape = proxyShape;
            if (dim == null || shape == null) return false;
            Object obj = shape.newProxy(path, dim.w(), dim.h());
            ProxyEntry entry = new ProxyEntry(path, type, dim.w(), dim.h(), obj);
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
     * (FR-Main-Loader, first step of initMods) or the runtime main thread. Any
     * failure — wrong thread, register error, or leftovers after the drain —
     * disables lazy skipping and reloads the remaining textures through the
     * normal async path, instead of leaving skip paths out of the repository.
     */
    public static void drainPending() {
        try {
            if (!enabled || probe || disabled) return;
            Thread current = Thread.currentThread();
            Thread loading = loadingThread();
            if (current != runtimeMain && current != loading) {
                AgentLog.fail("lazy: drain on " + current.getName()
                        + " (loading=" + (loading == null ? "none" : loading.getName())
                        + "); failing open and reloading pending textures", null);
                failOpenPending();
                return;
            }
            int drained = 0;
            boolean failed = false;
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
                    failed = true;
                    break;
                }
            }
            if (drained > 0) {
                LAZY_DRAINED.addAndGet(drained);
                AgentLog.info("lazy: drained " + drained + " proxies into oOoO.new");
            }
            if (failed || !PENDING.isEmpty()) {
                AgentLog.fail("lazy: drain incomplete (pending=" + PENDING.size()
                        + "); failing open and reloading pending textures", null);
                failOpenPending();
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: drain failed; failing open", t);
            failOpenPending();
        }
    }

    /** Stops skipping and restores every still-pending path through loadAsync. */
    private static void failOpenPending() {
        // Set disabled before the CAS: every other thread must stop skipping
        // immediately, even if this thread loses the one-shot race.
        disabled = true;
        if (!FAILING_OPEN.compareAndSet(false, true)) {
            AgentLog.info("lazy: fail-open already handled; skipping duplicate");
            return;
        }
        Object loader = loaderSingleton;
        if (loader == null) {
            AgentLog.fail("lazy: no TextureLoader singleton; cannot reload pending textures", null);
            return;
        }
        int reloaded = 0;
        int notReloaded = 0;
        for (String path : PENDING) {
            ProxyEntry e = PROXIES.get(path);
            if (e == null) {
                PENDING.remove(path);
                continue;
            }
            try {
                // N4: loadAsync returns false when loadTextureAsync cannot be
                // resolved; such paths stay pending and are counted as failed
                // instead of being reported as reloaded.
                if (loadAsync(loader, e.type, path)) {
                    PENDING.remove(path);
                    reloaded++;
                } else {
                    LAZY_FAILED.incrementAndGet();
                    notReloaded++;
                }
            } catch (Throwable t) {
                LAZY_FAILED.incrementAndGet();
                notReloaded++;
                AgentLog.fail("lazy: pending reload failed for " + path, t);
            }
        }
        AgentLog.info("lazy: fail-open reloaded " + reloaded + " pending textures"
                + (notReloaded == 0 ? ""
                : "; " + notReloaded + " not reloaded (kept pending)"));
    }

    private static Method engineRegister() {
        Method m = engineRegisterMethod;
        if (m != null || engineRegisterResolved) return m;
        synchronized (LazyTextures.class) {
            m = engineRegisterMethod;
            if (m != null || engineRegisterResolved) return m;
            try {
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
                return found;
            } catch (Throwable t) {
                AgentLog.fail("lazy: engine texture map register resolution failed", t);
                engineRegisterResolved = true;
                return null;
            }
        }
    }

    private static void registerEngineMap(String path, Object obj) throws Throwable {
        Method m = engineRegister();
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
        if (t != null) return t;
        synchronized (LazyTextures.class) {
            t = loadingThreadField;
            if (t != null) return t;
            // Never cache a null resolution: the summary thread can run before
            // initResourceLoading() sets mainThread. Retry, but throttle the
            // reflection and the log so a version drift cannot hot-loop.
            long now = System.nanoTime();
            if (now - loadingResolveNanos < 1_000_000_000L) return null;
            loadingResolveNanos = now;
            try {
                Class<?> fileLoader = Class.forName("com.fs.util.C",
                        false, LazyTextures.class.getClassLoader());
                Method getInstance = fileLoader.getDeclaredMethod("Ó00000");
                getInstance.setAccessible(true);
                Object instance = getInstance.invoke(null);
                Field field = fileLoader.getDeclaredField("mainThread");
                field.setAccessible(true);
                t = (Thread) field.get(instance);
                if (t != null) {
                    loadingThreadField = t;
                    loadingThreadResolved = true;
                } else if (LOADING_WARNED.compareAndSet(false, true)) {
                    AgentLog.info("lazy: FileLoader.mainThread not set yet; will retry");
                }
            } catch (Throwable t2) {
                if (LOADING_WARNED.compareAndSet(false, true)) {
                    AgentLog.info("lazy: FileLoader.mainThread unavailable; will retry");
                }
            }
            return t;
        }
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
                ClassLoader loader = LazyTextures.class.getClassLoader();
                Class<?> obj = Class.forName("com.fs.graphics.Object");
                Class<?> proxy = Class.forName("hypernova.agent.textures.LazyProxyObject");
                proxyShape = ProxyShape.resolve(obj, proxy);
                ensureLoader();
                if (syncMethod == null || loaderSingleton == null) {
                    throw new IllegalStateException("TextureLoader sync path unavailable");
                }
                // Force-load every transformer target so its hook is applied and
                // armed before the first skip; version drift must fail open here.
                Class.forName("com.fs.graphics.TextureLoader", false, loader);
                Class.forName("com.fs.graphics.oOoO", false, loader);
                Class.forName("com.fs.starfarer.api.impl.campaign.procgen.MarkovNames", false, loader);
                Class.forName("com.fs.starfarer.BaseGameState", false, loader);
                Method engine = engineRegister();
                if (!wiringOk(queueArmed, registerArmed, drainArmed, threadArmed, engine, obj, proxy)) {
                    throw new IllegalStateException("lazy wiring incomplete: queue=" + queueArmed
                            + " register=" + registerArmed + " drain=" + drainArmed
                            + " thread=" + threadArmed + " engineRegister=" + (engine != null));
                }
                AgentLog.info("lazy: shape ok; proxy + sync loader resolved");
                AgentLog.info("lazy: wiring armed queue=" + queueArmed + " register=" + registerArmed
                        + " drain=" + drainArmed + " thread=" + threadArmed);
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

    private static boolean loadAsync(Object loader, String type, String path) throws Throwable {
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
        if (m == null) return false;
        try {
            m.invoke(loader, type, path);
            return true;
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
            if (e == null || e.obj == value) return;
            synchronized (e) {
                if (e.obj == value) return;
                if (e.ready) {
                    refreshReady(proxyShape, e, value, "register");
                    return;
                }
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
            if (e == null || e.obj == value) return;
            synchronized (e) {
                if (e.obj == value) return;
                if (e.ready) {
                    refreshReady(proxyShape, e, value, "engine hit");
                    return;
                }
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

    /**
     * F3 fix: a real object arrived for an already-materialized proxy (cache
     * clear/reload, resolution change). Copy the new fields — including the new
     * GL id — into the proxy and point TextureLoader.ÔO0000 at the proxy, so
     * Sprite instances that already hold the proxy see the new texture. The
     * same source object is absorbed once: if the engine map keeps returning
     * that real object on every lookup, the per-lookup path stays a reference
     * comparison instead of 14 reflective field copies.
     *
     * <p>Called under {@code synchronized (e)}. Returns true when a refresh
     * happened (test seam; production callers ignore the result).
     */
    static boolean refreshReady(ProxyShape shape, ProxyEntry e, Object value, String source)
            throws Exception {
        if (shape == null || e == null || value == null) return false;
        if (value == e.obj || value == e.lastSource) return false;
        shape.copy(value, e.obj);
        e.lastSource = value;
        putPathCache(e.path, e.obj);
        int perPath = ++e.reregistered;
        long total = LAZY_REREGISTERED.incrementAndGet();
        if (perPath <= 3) {
            AgentLog.info("lazy: refreshed ready proxy " + e.path + " from " + source
                    + " (F3; reregistered=" + total + ", pathReregistered=" + perPath + ")");
        }
        return true;
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
                    + " reregistered=" + LAZY_REREGISTERED.get()
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

    static final class ProxyEntry {
        final String path;
        final String type;
        final int w;
        final int h;
        final Object obj;
        volatile boolean ready;
        volatile boolean failed;
        /** Last real object absorbed by {@link #refreshReady}; dedups hot lookups. */
        volatile Object lastSource;
        /** How many different real objects this proxy has absorbed (F3). */
        int reregistered;
        final AtomicLong attempts = new AtomicLong();

        ProxyEntry(String path, String type, int w, int h, Object obj) {
            this.path = path;
            this.type = type;
            this.w = w;
            this.h = h;
            this.obj = obj;
        }
    }
}
