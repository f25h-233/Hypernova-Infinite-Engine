package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
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
    private static final AtomicLong DIM_MISMATCH = new AtomicLong();
    private static final AtomicLong LATE_REGISTERED = new AtomicLong();
    private static final AtomicLong LATE_LOADED = new AtomicLong();
    private static volatile boolean dds;
    private static final AtomicLong DDS_HIT = new AtomicLong();
    private static final AtomicLong DDS_FALLBACK = new AtomicLong();
    private static final AtomicLong DDS_DISABLED = new AtomicLong();
    private static final AtomicLong DDS_DIM_MISMATCH = new AtomicLong();
    /**
     * R-M26-10: GL deletes are only legal on the runtime main thread. Ids freed
     * off-main (loading thread DDS cleanup, F3 refresh) wait here for the next
     * main-thread noteGameState() drain.
     */
    private static final java.util.Set<Integer> PENDING_DELETE =
            java.util.concurrent.ConcurrentHashMap.newKeySet();
    private static final AtomicLong DEFERRED_DELETES = new AtomicLong();
    // ---- M2.6 eviction state ----
    private static volatile boolean eviction;
    private static volatile int evictionBudgetMb;
    private static volatile long evictionGraceNanos;
    private static volatile long evictionSceneDelayNanos;
    private static volatile int evictionMaxPerPass;
    private static final AtomicLong LIVE_BYTES = new AtomicLong();
    private static final AtomicLong EVICTED = new AtomicLong();
    private static final AtomicLong EVICTED_BYTES = new AtomicLong();
    private static final AtomicLong REMATERIALIZED = new AtomicLong();
    private static final AtomicLong EVICT_PASSES = new AtomicLong();
    private static final AtomicLong OLD_ID_DELETED = new AtomicLong();
    private static final AtomicLong OLD_ID_SKIPPED = new AtomicLong();
    private static volatile int placeholderId;
    private static final AtomicBoolean PLACEHOLDER_FAILED = new AtomicBoolean();
    private static volatile long evictDueNanos;
    private static volatile String lastStateName;
    private static volatile long stateTransitions;
    private static volatile long mainCapturedNanos;
    // ---- M2.6 default-on fix: deterministic eviction + real combat signal ----
    private static volatile Method gameStateMethod;
    private static volatile boolean gameStateResolved;
    private static final AtomicBoolean GAME_STATE_FAIL_LOGGED = new AtomicBoolean();
    static final long EVICT_EMPTY_BACKOFF_NANOS = 30_000_000_000L;
    // ---- M2.6 selftest state ----
    private static volatile boolean selftest;
    private static volatile int selftestResult;
    private static final AtomicBoolean SELFTEST_DONE = new AtomicBoolean();
    private static final String PLACEHOLDER_PATH = "graphics/hypernova/blank.png";
    private static final AtomicBoolean LOAD_ASYNC_FAILED = new AtomicBoolean();
    private static final Map<String, ProxyEntry> PROXIES = new ConcurrentHashMap<>();
    private static final Map<Object, ProxyEntry> PROXY_BY_OBJ = new ConcurrentHashMap<>();
    /** Skip paths whose proxy has not been inserted into oOoO.new yet. */
    private static final Set<String> PENDING = ConcurrentHashMap.newKeySet();
    private static final Object DRAIN_LOCK = new Object();
    private static volatile boolean drained;
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

    private static volatile LazySkipIndex index;
    private static volatile Path skipFile;
    private static volatile Path manifestFile;

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
        dds = config.dds();
        eviction = config.eviction();
        selftest = config.selftest();
        evictionBudgetMb = config.evictionBudgetMb();
        evictionGraceNanos = Math.max(0, config.evictionGraceMs()) * 1_000_000L;
        evictionSceneDelayNanos = Math.max(0, config.evictionSceneDelayMs()) * 1_000_000L;
        evictionMaxPerPass = Math.max(1, config.evictionMaxPerPass());
        skipFile = config.skipFile();
        manifestFile = config.manifestFile();
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
            String problem = verifyGeneration(idx, manifestFile);
            if (problem != null) {
                disabled = true;
                AgentLog.fail("lazy: skip/manifest generation check failed: " + problem
                        + "; lazy disabled", null);
                return;
            }
            index = idx;
            AgentLog.info("lazy probe: index loaded paths=" + idx.size()
                    + " invalid=" + idx.invalid() + " generation="
                    + shortGeneration(idx.generation())
                    + " in " + idx.loadMillis() + " ms; file=" + f);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: index load failed; probe counts stay 0", t);
        }
    }

    private static String shortGeneration(String generation) {
        if (generation == null || generation.isBlank()) return "none";
        return generation.length() <= 12 ? generation : generation.substring(0, 12);
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
        if (!loadAsync(loader, type, path)) {
            disabled = true;
            if (LOAD_ASYNC_FAILED.compareAndSet(false, true)) {
                AgentLog.fail("lazy: loadTextureAsync unavailable for " + path
                        + "; lazy disabled", null);
            }
            failOpenPending();
        }
    }

    static boolean eligible(boolean enabled, boolean probe, boolean disabled,
                            LazySkipIndex index, String type, String path) {
        if (!enabled || probe || disabled) return false;
        if ("TEXTURE_ALPHA_ADDER".equals(type)) return false;
        return index != null && index.contains(path);
    }

    static boolean skipAllowed(boolean enabled, boolean probe, boolean disabled,
                               boolean drainedNow, LazySkipIndex index,
                               String type, String path) {
        return !drainedNow && eligible(enabled, probe, disabled, index, type, path);
    }

    static boolean shouldFailOpenDisabledDrain(boolean enabled, boolean probe,
                                               boolean disabled, int pending) {
        return (!enabled || probe || disabled) && pending > 0;
    }

    static boolean dimensionsMatch(int realW, int realH, int expectedW, int expectedH) {
        return realW > 0 && realH > 0 && realW == expectedW && realH == expectedH;
    }

    static boolean isLoadAsync(Method method) {
        if (method == null) return false;
        Class<?>[] p = method.getParameterTypes();
        return "loadTextureAsync".equals(method.getName()) && p.length == 2
                && p[0] == String.class && p[1] == String.class;
    }

    static String verifyGeneration(LazySkipIndex idx, Path manifest) {
        if (idx == null) return "no index";
        if (manifest == null) return "manifest path missing";
        if (!Files.isRegularFile(manifest)) return "manifest missing: " + manifest;
        String expected = idx.generation();
        if (expected == null || expected.isBlank()) return "skip generation header missing";
        try {
            String actual = sha256(manifest);
            if (!expected.equalsIgnoreCase(actual)) {
                return "generation mismatch expected=" + expected + " actual=" + actual;
            }
            return null;
        } catch (Throwable t) {
            return "manifest hash failed: " + t;
        }
    }

    static String sha256(Path file) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(file)) {
            byte[] buf = new byte[65_536];
            int n;
            while ((n = in.read(buf)) >= 0) {
                if (n > 0) md.update(buf, 0, n);
            }
        }
        return HexFormat.of().formatHex(md.digest());
    }

    static void resetGateStateForTest() {
        disabled = false;
        drained = false;
        DIM_MISMATCH.set(0);
        LAZY_FAILED.set(0);
        LOAD_ASYNC_FAILED.set(false);
        FAILING_OPEN.set(false);
        loadAsyncMethod = null;
        DEGRADED.set(false);
        DDS_HIT.set(0);
        DDS_FALLBACK.set(0);
        DDS_DISABLED.set(0);
        DDS_DIM_MISMATCH.set(0);
        EVICTED.set(0);
        EVICTED_BYTES.set(0);
        REMATERIALIZED.set(0);
        EVICT_PASSES.set(0);
        LIVE_BYTES.set(0);
        OLD_ID_DELETED.set(0);
        OLD_ID_SKIPPED.set(0);
        evictDueNanos = 0;
        lastStateName = null;
        PENDING_DELETE.clear();
        DEFERRED_DELETES.set(0);
        selftestResult = 0;
        SELFTEST_DONE.set(false);
        gameStateMethod = null;
        gameStateResolved = false;
        GAME_STATE_FAIL_LOGGED.set(false);
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
            if (!skipAllowed(enabled, probe, disabled, drained, index, type, path)) return false;
            return ensureShape();
        } catch (Throwable t) {
            AgentLog.fail("lazy: skip decision failed for " + path + "; loading normally", t);
            return false;
        }
    }

    private static boolean registerProxy(String path, String type) {
        try {
            synchronized (DRAIN_LOCK) {
                if (PROXIES.containsKey(path)) return true;
                LazySkipIndex idx = index;
                LazySkipIndex.Entry dim = idx == null ? null : idx.get(path);
                ProxyShape shape = proxyShape;
                if (dim == null || shape == null) return false;
                Object obj = shape.newProxy(path, dim.w(), dim.h());
                ProxyEntry entry = new ProxyEntry(path, type, dim.w(), dim.h(), obj);
                ProxyEntry prev = PROXIES.putIfAbsent(path, entry);
                if (prev != null) return true;
                PROXY_BY_OBJ.put(obj, entry);
                if (drained) {
                    if (canMaterialize()) {
                        try {
                            registerEngineMap(path, obj);
                            LATE_REGISTERED.incrementAndGet();
                            return true;
                        } catch (Throwable t) {
                            PROXIES.remove(path, entry);
                            PROXY_BY_OBJ.remove(obj, entry);
                            AgentLog.fail("lazy: late engine map register failed for " + path, t);
                            return false;
                        }
                    }
                    PROXIES.remove(path, entry);
                    PROXY_BY_OBJ.remove(obj, entry);
                    LATE_LOADED.incrementAndGet();
                    return false;
                }
                PENDING.add(path);
                if (PROXIES.size() <= 20) {
                    AgentLog.info("lazy: proxy " + path + " " + dim.w() + "x" + dim.h());
                }
                return true;
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: proxy registration failed for " + path + "; loading normally", t);
            return false;
        }
    }

    public static Object lookup(String path) {
        if (path == null) return null;
        try {
            long now = System.nanoTime();
            maybeRunEviction(now);
            if (selftest) maybeRunSelfTest(now);
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
            long now = System.nanoTime();
            maybeRunEviction(now);
            if (selftest) maybeRunSelfTest(now);
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
        synchronized (DRAIN_LOCK) {
            if (drained) return;
            try {
                if (!enabled || probe || disabled) {
                    drained = true;
                    if (shouldFailOpenDisabledDrain(enabled, probe, disabled, PENDING.size())) {
                        AgentLog.fail("lazy: drain skipped because lazy is disabled with "
                                + PENDING.size() + " pending proxies; failing open", null);
                        failOpenPending();
                    }
                    return;
                }
                Thread current = Thread.currentThread();
                Thread loading = loadingThread();
                if (current != runtimeMain && current != loading) {
                    AgentLog.fail("lazy: drain on " + current.getName()
                            + " (loading=" + (loading == null ? "none" : loading.getName())
                            + "); failing open and reloading pending textures", null);
                    drained = true;
                    failOpenPending();
                    return;
                }
                int drainedCount = 0;
                boolean failed = false;
                for (String path : PENDING) {
                    ProxyEntry e = PROXIES.get(path);
                    if (e == null) {
                        PENDING.remove(path);
                        continue;
                    }
                    try {
                        registerEngineMap(path, e.obj);
                        if (PENDING.remove(path)) drainedCount++;
                    } catch (Throwable t) {
                        AgentLog.fail("lazy: engine map register failed for " + path, t);
                        failed = true;
                        break;
                    }
                }
                if (drainedCount > 0) {
                    LAZY_DRAINED.addAndGet(drainedCount);
                    AgentLog.info("lazy: drained " + drainedCount + " proxies into oOoO.new");
                }
                drained = true;
                if (failed || !PENDING.isEmpty()) {
                    AgentLog.fail("lazy: drain incomplete (pending=" + PENDING.size()
                            + "); failing open and reloading pending textures", null);
                    failOpenPending();
                }
            } catch (Throwable t) {
                drained = true;
                AgentLog.fail("lazy: drain failed; failing open", t);
                failOpenPending();
            }
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
            if (state == null) return;
            String name = state.getClass().getName();
            if (name.contains("launcher") || name.contains("Launcher")) return;
            if (runtimeMain == null) {
                runtimeMain = Thread.currentThread();
                mainCapturedNanos = System.nanoTime();
                AgentLog.info("lazy: runtime main thread captured " + runtimeMain.getName()
                        + " from " + name);
            }
            noteGameState(name);
        } catch (Throwable t) {
            AgentLog.fail("lazy: main-thread capture failed", t);
        }
    }

    static void noteGameState(String name) {
        long now = System.nanoTime();
        if (eviction) {
            String prev = lastStateName;
            if (shouldArmOnTransition(prev, name)) {
                evictDueNanos = now + evictionSceneDelayNanos;
                long n = ++stateTransitions;
                if (n <= 20) {
                    AgentLog.info("lazy: state " + prev + " -> " + name
                            + "; eviction due in " + (evictionSceneDelayNanos / 1_000_000L) + " ms");
                }
            }
            lastStateName = name;
        }
        maybeRunEviction(now);
        maybeRunSelfTest(now);
    }

    static boolean shouldArmOnTransition(String prev, String name) {
        return prev != null && name != null && !prev.equals(name);
    }

    static boolean shouldRunEviction(boolean eviction, boolean disabled, long dueNanos,
                                     long now, boolean inCombat) {
        return eviction && !disabled && dueNanos != 0 && now >= dueNanos && !inCombat;
    }

    static long nextDueAfterPass(long now, long delay, long liveBytes, long budget, int evicted) {
        if (liveBytes <= budget) return 0;
        if (evicted > 0) return now + delay;
        return now + Math.max(delay, EVICT_EMPTY_BACKOFF_NANOS);
    }

    static boolean shouldArmOnBudget(long dueNanos, long liveBytes, long budget) {
        return dueNanos == 0 && liveBytes > budget;
    }

    static void maybeRunEviction(long now) {
        if (Thread.currentThread() != runtimeMain) return;
        if (!PENDING_DELETE.isEmpty()) drainPendingDeletes();
        if (!eviction || disabled) return;
        long due = evictDueNanos;
        if (due == 0 || now < due) return;
        boolean combat = isInCombat();
        if (!shouldRunEviction(eviction, disabled, due, now, combat)) {
            if (combat) {
                evictDueNanos = now + evictionSceneDelayNanos;
            }
            return;
        }
        evictDueNanos = 0;
        evictPass(now);
    }

    static boolean isInCombat() {
        Method m = resolveGameStateMethod();
        if (m == null) return true; // conservative: unknown -> do not evict
        try {
            Object state = m.invoke(null);
            return state != null && "COMBAT".equals(String.valueOf(state));
        } catch (Throwable t) {
            return true;
        }
    }

    private static Method resolveGameStateMethod() {
        Method m = gameStateMethod;
        if (m != null || gameStateResolved) return m;
        synchronized (LazyTextures.class) {
            if (gameStateResolved) return gameStateMethod;
            try {
                Class<?> global = Class.forName("com.fs.starfarer.api.Global", false,
                        LazyTextures.class.getClassLoader());
                gameStateMethod = global.getMethod("getCurrentState");
            } catch (Throwable t) {
                if (GAME_STATE_FAIL_LOGGED.compareAndSet(false, true)) {
                    AgentLog.fail("lazy: game state probe unavailable; eviction disabled", t);
                }
            } finally {
                gameStateResolved = true;
            }
            return gameStateMethod;
        }
    }

    /**
     * Runs the real-process selftest at most once, on the runtime main thread,
     * at least 5 s after the main thread was captured. This build calls
     * BaseGameState.traverse (and therefore noteGameState) only on state
     * transitions, so the same gate is also evaluated from the per-frame
     * main-thread paths (lookup miss / onProxyUse bind-id).
     */
    private static void maybeRunSelfTest(long now) {
        if (!selftest || SELFTEST_DONE.get()) return;
        if (Thread.currentThread() != runtimeMain) return;
        long captured = mainCapturedNanos;
        if (captured == 0 || now - captured < 5_000_000_000L) return;
        if (SELFTEST_DONE.compareAndSet(false, true)) {
            runSelfTest();
        }
    }

    private static void materialize(ProxyEntry e) {
        synchronized (e) {
            if (e.ready || e.failed) return;
            long t0 = System.nanoTime();
            try {
                if (dds && materializeDds(e)) {
                    return;
                }
                materializePng(e, t0);
            } catch (Throwable t) {
                long attempts = e.attempts.incrementAndGet();
                if (attempts >= 2) e.failed = true;
                LAZY_FAILED.incrementAndGet();
                AgentLog.fail("lazy: materialize failed for " + e.path
                        + " (attempt " + attempts + ")", t);
            }
        }
    }

    private static void materializePng(ProxyEntry e, long t0) throws Throwable {
        Object real = syncLoad(e.path);
        ProxyShape shape = proxyShape;
        if (shape == null) throw new IllegalStateException("proxy shape unavailable");
        int realW = shape.imageWidth(real);
        int realH = shape.imageHeight(real);
        if (!dimensionsMatch(realW, realH, e.w, e.h)) {
            onDimMismatch(e, realW, realH, "materialize");
        }
        shape.copy(real, e.obj);
        e.ready = true;
        e.glId = shape.glId(real);
        e.owned = true;
        noteMaterialized(e, 4L * e.w * e.h);
        e.dds = false;
        touch(e);
        putPathCache(e.path, e.obj);
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        long n = LAZY_MATERIALIZED.incrementAndGet();
        if (n <= 20 || ms >= 50) {
            AgentLog.info("lazy: materialized " + e.path + " " + e.w + "x" + e.h
                    + " in " + ms + " ms");
        }
    }

    private static boolean materializeDds(ProxyEntry e) {
        LazySkipIndex.Entry meta = index == null ? null : index.get(e.path);
        if (meta == null || meta.absPath() == null || meta.ddsPath() == null) {
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        if (!DdsBridge.available()) {
            DDS_DISABLED.incrementAndGet();
            return false;
        }
        Path absPath;
        try {
            absPath = Path.of(meta.absPath());
        } catch (Throwable t) {
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        DdsBridge.Data data = DdsBridge.get(absPath);
        if (data == null) {
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        if (!dimensionsMatch(data.imageWidth(), data.imageHeight(), e.w, e.h)) {
            DDS_DIM_MISMATCH.incrementAndGet();
            onDimMismatch(e, data.imageWidth(), data.imageHeight(), "dds metadata");
            return false;
        }
        DdsCheck.Result check = DdsCheck.check(data.ddsPath(), e.w, e.h);
        if (!check.ok()) {
            long n = DDS_FALLBACK.incrementAndGet();
            if (n <= 20) {
                AgentLog.info("lazy: dds fallback " + e.path + " (" + check.reason() + ")");
            }
            return false;
        }
        int id = DdsBridge.commit(data.texData());
        if (id <= 0) {
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        Object real;
        try {
            real = DdsBridge.newHandler(loaderSingleton, e.path, data.texData(), id);
        } catch (Throwable t) {
            deleteTextureSafe(id);
            long n = DDS_FALLBACK.incrementAndGet();
            if (n <= 20) AgentLog.fail("lazy: dds handler failed for " + e.path, t);
            return false;
        }
        if (real == null) {
            deleteTextureSafe(id);
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        ProxyShape shape = proxyShape;
        if (shape == null) {
            deleteTextureSafe(id);
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        int realW;
        int realH;
        try {
            realW = shape.imageWidth(real);
            realH = shape.imageHeight(real);
        } catch (Throwable t) {
            deleteTextureSafe(id);
            DDS_FALLBACK.incrementAndGet();
            AgentLog.fail("lazy: dds handler shape failed for " + e.path, t);
            return false;
        }
        if (!dimensionsMatch(realW, realH, e.w, e.h)) {
            DDS_DIM_MISMATCH.incrementAndGet();
            onDimMismatch(e, realW, realH, "dds handler");
        }
        try {
            shape.copy(real, e.obj);
        } catch (Throwable t) {
            deleteTextureSafe(id);
            DDS_FALLBACK.incrementAndGet();
            AgentLog.fail("lazy: dds handler copy failed for " + e.path, t);
            return false;
        }
        e.ready = true;
        e.dds = true;
        e.glId = id;
        e.owned = true;
        noteMaterialized(e, ddsBytes(data.width(), data.height()));
        touch(e);
        putPathCache(e.path, e.obj);
        long n = DDS_HIT.incrementAndGet();
        LAZY_MATERIALIZED.incrementAndGet();
        if (n <= 20) {
            AgentLog.info("lazy: dds materialized " + e.path + " " + e.w + "x" + e.h
                    + " id=" + id + " bytes=" + e.bytes);
        }
        return true;
    }

    static long ddsBytes(int w, int h) {
        // BC7 is 1 byte/pixel for level 0; the DDS may carry mips, but this is a
        // conservative LRU accounting estimate, not a VRAM measurement.
        return Math.max(0L, (long) w * h);
    }

    /** R-M26-10: GL deletes only on the runtime main thread; off-main ids wait. */
    private static boolean deleteTextureSafe(int id) {
        if (id <= 0) return false;
        if (Thread.currentThread() != runtimeMain) {
            PENDING_DELETE.add(id);
            DEFERRED_DELETES.incrementAndGet();
            return false;
        }
        return GlBridge.deleteTexture(id);
    }

    private static void drainPendingDeletes() {
        if (Thread.currentThread() != runtimeMain || PENDING_DELETE.isEmpty()) return;
        for (Integer id : PENDING_DELETE) {
            if (GlBridge.deleteTexture(id)) PENDING_DELETE.remove(id);
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
            if (syncMethod == null || loaderSingleton == null) {
                throw new IllegalStateException("loader shape");
            }
            if (loadAsyncMethod == null) {
                throw new IllegalStateException("loadTextureAsync shape");
            }
            return;
        }
        synchronized (LazyTextures.class) {
            if (loaderResolved) {
                if (syncMethod == null || loaderSingleton == null) {
                    throw new IllegalStateException("loader shape");
                }
                if (loadAsyncMethod == null) {
                    throw new IllegalStateException("loadTextureAsync shape");
                }
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
                Method async = null;
                for (Method method : loader.getClass().getDeclaredMethods()) {
                    if (isLoadAsync(method)) {
                        async = method;
                        continue;
                    }
                    if (!"o00000".equals(method.getName()) || method.getParameterCount() != 7) continue;
                    Class<?>[] p = method.getParameterTypes();
                    if (p[0] == objClass && p[1] == String.class
                            && p[2] == int.class && p[3] == int.class
                            && p[4] == int.class && p[5] == int.class
                            && p[6] == boolean.class) {
                        sync = method;
                    }
                }
                if (async == null) throw new NoSuchMethodException("TextureLoader.loadTextureAsync");
                async.setAccessible(true);
                loadAsyncMethod = async;
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
                AgentLog.info("lazy: sync+async loader resolved on " + loader.getClass().getName());
            } finally {
                loaderResolved = true;
            }
        }
    }

    private static boolean loadAsync(Object loader, String type, String path) throws Throwable {
        Method m = loadAsyncMethod;
        if (m == null) {
            m = resolveLoadAsync(loader);
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

    static Method resolveLoadAsync(Object loader) {
        if (loader == null) return null;
        try {
            Method m = loader.getClass().getDeclaredMethod(
                    "loadTextureAsync", String.class, String.class);
            m.setAccessible(true);
            loadAsyncMethod = m;
            return m;
        } catch (Throwable t) {
            if (DEGRADED.compareAndSet(false, true)) {
                AgentLog.fail("lazy: loadTextureAsync missing on "
                        + loader.getClass().getName(), t);
            }
            return null;
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
        if (path == null) return;
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
                int realW = shape.imageWidth(value);
                int realH = shape.imageHeight(value);
                if (!dimensionsMatch(realW, realH, e.w, e.h)) {
                    onDimMismatch(e, realW, realH, "register");
                }
                shape.copy(value, e.obj);
                e.ready = true;
                e.glId = shape.glId(value);
                e.owned = false;
                noteMaterialized(e, 4L * e.w * e.h);
                e.dds = false;
                touch(e);
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
                int realW = shape.imageWidth(value);
                int realH = shape.imageHeight(value);
                if (!dimensionsMatch(realW, realH, e.w, e.h)) {
                    onDimMismatch(e, realW, realH, "engine hit");
                }
                shape.copy(value, e.obj);
                e.ready = true;
                e.glId = shape.glId(value);
                e.owned = false;
                noteMaterialized(e, 4L * e.w * e.h);
                e.dds = false;
                touch(e);
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
        int realW = shape.imageWidth(value);
        int realH = shape.imageHeight(value);
        if (!dimensionsMatch(realW, realH, e.w, e.h)) {
            onDimMismatch(e, realW, realH, source);
            return false;
        }
        int oldId = shape.glId(e.obj);
        boolean oldOwned = e.owned;
        shape.copy(value, e.obj);
        int newId = shape.glId(value);
        e.glId = newId;
        boolean onMain = Thread.currentThread() == runtimeMain;
        if (shouldDeleteOldId(oldOwned, oldId, newId, placeholderId, onMain)) {
            if (GlBridge.deleteTexture(oldId)) {
                OLD_ID_DELETED.incrementAndGet();
            } else {
                OLD_ID_SKIPPED.incrementAndGet();
            }
        } else if (oldOwned && oldId > 0 && oldId != newId && oldId != placeholderId) {
            PENDING_DELETE.add(oldId);
            DEFERRED_DELETES.incrementAndGet();
        }
        e.owned = false;
        e.dds = false;
        e.lastSource = value;
        touch(e);
        putPathCache(e.path, e.obj);
        int perPath = ++e.reregistered;
        long total = LAZY_REREGISTERED.incrementAndGet();
        if (perPath <= 3) {
            AgentLog.info("lazy: refreshed ready proxy " + e.path + " from " + source
                    + " (F3; reregistered=" + total + ", pathReregistered=" + perPath + ")");
        }
        return true;
    }

    private static void onDimMismatch(ProxyEntry e, int realW, int realH, String source) {
        long n = DIM_MISMATCH.incrementAndGet();
        LAZY_FAILED.incrementAndGet();
        disabled = true;
        if (n <= 20) {
            AgentLog.fail("lazy: dimension mismatch for " + e.path + " expected "
                    + e.w + "x" + e.h + " real " + realW + "x" + realH
                    + " (" + source + "); lazy disabled", null);
        }
    }

    private static void touch(ProxyEntry e) {
        e.lastUseNanos = System.nanoTime();
    }

    static List<ProxyEntry> selectVictims(List<ProxyEntry> ready, long liveBytes,
                                          long budgetBytes, long graceNanos,
                                          long now, int max) {
        if (liveBytes <= budgetBytes) return List.of();
        long low = budgetBytes - (budgetBytes / 5); // 80%
        List<ProxyEntry> candidates = new ArrayList<>();
        for (ProxyEntry e : ready) {
            if (e == null || !e.ready || e.bytes <= 0 || e.glId <= 0) continue;
            if (!e.owned) continue;
            if (e.startup || isBasicPath(e.path)) continue;
            if (e.lastUseNanos == 0 || now - e.lastUseNanos < graceNanos) continue;
            candidates.add(e);
        }
        candidates.sort(Comparator.comparingLong(e -> e.lastUseNanos));
        List<ProxyEntry> out = new ArrayList<>();
        long live = liveBytes;
        for (ProxyEntry e : candidates) {
            if (live <= low || out.size() >= max) break;
            out.add(e);
            live -= e.bytes;
        }
        return out;
    }

    static boolean isBasicPath(String path) {
        if (path == null) return true;
        return path.startsWith("graphics/ui/")
                || path.startsWith("graphics/fonts/")
                || path.startsWith("graphics/intro/");
    }

    static boolean shouldDeleteOldId(boolean owned, int oldId, int newId,
                                     int placeholder, boolean allowedThread) {
        return owned && allowedThread && oldId > 0 && oldId != newId
                && oldId != placeholder;
    }

    private static long budgetBytes() {
        return evictionBudgetMb <= 0 ? Long.MAX_VALUE : evictionBudgetMb * 1024L * 1024L;
    }

    private static void evictPass(long now) {
        if (!eviction || disabled || Thread.currentThread() != runtimeMain) return;
        long live = LIVE_BYTES.get();
        long budget = budgetBytes();
        if (live <= budget) return;
        List<ProxyEntry> ready = new ArrayList<>();
        for (ProxyEntry e : PROXIES.values()) {
            if (e.ready) ready.add(e);
        }
        List<ProxyEntry> victims = selectVictims(ready, live, budget,
                evictionGraceNanos, now, evictionMaxPerPass);
        int n = 0;
        long bytes = 0;
        for (ProxyEntry e : victims) {
            long b = e.bytes;
            if (evictOne(e, false)) {
                n++;
                bytes += b;
            }
        }
        EVICT_PASSES.incrementAndGet();
        if (n > 0) {
            AgentLog.info("lazy: eviction pass evicted=" + n + " bytes=" + bytes
                    + " live=" + LIVE_BYTES.get() + " budget=" + budget);
        }
        evictDueNanos = nextDueAfterPass(now, evictionSceneDelayNanos,
                LIVE_BYTES.get(), budget, n);
    }

    private static boolean evictOne(ProxyEntry e, boolean force) {
        if (e == null || !e.ready || e.glId <= 0 || e.obj == null) return false;
        if (!e.owned) return false;
        if (!force && (e.startup || isBasicPath(e.path))) return false;
        if (Thread.currentThread() != runtimeMain) return false;
        if (!ensurePlaceholder()) return false;
        int id;
        synchronized (e) {
            if (!e.ready || e.glId <= 0) return false;
            ProxyShape shape = proxyShape;
            if (shape == null) return false;
            id = e.glId;
            try {
                shape.reset(e.obj, 3553, placeholderId, 1, 1, 1.0f, 1.0f, e.w, e.h);
            } catch (Throwable t) {
                AgentLog.fail("lazy: eviction reset failed for " + e.path, t);
                return false;
            }
            long bytes = e.bytes;
            e.ready = false;
            e.failed = false;
            e.dds = false;
            e.owned = false;
            e.glId = 0;
            e.bytes = 0;
            e.lastSource = null;
            e.attempts.set(0);
            e.evicted++;
            LIVE_BYTES.addAndGet(-bytes);
            EVICTED.incrementAndGet();
            EVICTED_BYTES.addAndGet(bytes);
            touch(e);
        }
        // The proxy already points at the valid placeholder; a failed delete is
        // a VRAM leak, not a dangling id. Count it and let re-materialize fix it.
        if (!GlBridge.deleteTexture(id)) {
            OLD_ID_SKIPPED.incrementAndGet();
            return false;
        }
        return true;
    }

    static boolean evictOneForTest(ProxyEntry e, boolean force) {
        return evictOne(e, force);
    }

    private static boolean ensurePlaceholder() {
        if (placeholderId > 0) return true;
        if (PLACEHOLDER_FAILED.get()) return false;
        synchronized (LazyTextures.class) {
            if (placeholderId > 0) return true;
            try {
                Object real = syncLoad(PLACEHOLDER_PATH);
                ProxyShape shape = proxyShape;
                if (shape == null) throw new IllegalStateException("proxy shape unavailable");
                int target = shape.target(real);
                int id = shape.glId(real);
                if (target != 3553 || id <= 0) {
                    throw new IllegalStateException("bad placeholder target=" + target + " id=" + id);
                }
                placeholderId = id;
                AgentLog.info("lazy: eviction placeholder resolved id=" + id);
                return true;
            } catch (Throwable t) {
                PLACEHOLDER_FAILED.set(true);
                AgentLog.fail("lazy: eviction placeholder unavailable; eviction disabled", t);
                return false;
            }
        }
    }

    /**
     * Picks an invisible, not-yet-materialized proxy for the real-process
     * selftest. Basic UI/font/intro paths, startup textures, and failed
     * proxies are never candidates; a DDS-backed entry is preferred so the
     * selftest exercises the DDS materialize path.
     */
    static ProxyEntry pickSelfTestEntry(java.util.Collection<ProxyEntry> proxies,
                                        LazySkipIndex idx, boolean preferDds) {
        ProxyEntry fallback = null;
        for (ProxyEntry e : proxies) {
            if (e == null || e.ready || e.failed || e.startup || e.obj == null) continue;
            if (isBasicPath(e.path)) continue;
            LazySkipIndex.Entry meta = idx == null ? null : idx.get(e.path);
            if (preferDds && meta != null && meta.hasDds()) return e;
            if (fallback == null) fallback = e;
        }
        return fallback;
    }

    private static void runSelfTest() {
        try {
            ProxyEntry pick = pickSelfTestEntry(PROXIES.values(), index, dds);
            if (pick == null) {
                selftestResult = 3;
                AgentLog.fail("lazy selftest: no candidate proxy", null);
                return;
            }
            Object before = lookup(pick.path);
            if (before == null || !pick.ready || pick.glId <= 0) {
                selftestResult = 2;
                AgentLog.fail("lazy selftest: materialize failed for " + pick.path, null);
                return;
            }
            int firstId = pick.glId;
            if (!evictOne(pick, true) || pick.ready) {
                selftestResult = 2;
                AgentLog.fail("lazy selftest: evict failed for " + pick.path, null);
                return;
            }
            Object after = lookup(pick.path);
            if (after == null || !pick.ready || pick.glId <= 0
                    || pick.rematerialized <= 0) {
                selftestResult = 2;
                AgentLog.fail("lazy selftest: re-materialize failed for " + pick.path, null);
                return;
            }
            if (dds && !pick.dds) {
                selftestResult = 2;
                AgentLog.fail("lazy selftest: DDS path not used for " + pick.path
                        + " (ddsFallback=" + DDS_FALLBACK.get() + ")", null);
                return;
            }
            selftestResult = 1;
            AgentLog.info("lazy selftest: ok path=" + pick.path + " ids=" + firstId
                    + "->" + pick.glId + " dds=" + (pick.dds ? 1 : 0)
                    + " rematerialized=" + pick.rematerialized);
        } catch (Throwable t) {
            selftestResult = 2;
            AgentLog.fail("lazy selftest failed", t);
        }
    }

    /**
     * I2: textures first materialized off the runtime main thread (including
     * anything while {@code runtimeMain} is still null during loading) are
     * startup textures and are excluded from eviction. One-way latch.
     */
    static void markStartup(ProxyEntry e, boolean onMain) {
        if (!e.startup && !onMain) e.startup = true;
    }

    private static void noteMaterialized(ProxyEntry e, long bytes) {
        markStartup(e, Thread.currentThread() == runtimeMain);
        if (e.bytes == 0 && bytes > 0) {
            e.bytes = bytes;
            LIVE_BYTES.addAndGet(bytes);
        }
        if (e.evicted > 0) {
            e.rematerialized++;
            REMATERIALIZED.incrementAndGet();
        }
        if (eviction && budgetBytes() != Long.MAX_VALUE
                && shouldArmOnBudget(evictDueNanos, LIVE_BYTES.get(), budgetBytes())) {
            evictDueNanos = System.nanoTime() + evictionSceneDelayNanos;
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
                    + " reregistered=" + LAZY_REREGISTERED.get()
                    + " failed=" + LAZY_FAILED.get()
                    + " disabled=" + (disabled ? 1 : 0)
                    + " main=" + (runtimeMain == null ? "none" : runtimeMain.getName())
                    + " loading=" + (lt == null ? "none" : lt.getName())
                    + " lateRegistered=" + LATE_REGISTERED.get()
                    + " lateLoaded=" + LATE_LOADED.get()
                    + " dimMismatch=" + DIM_MISMATCH.get()
                    + " dds=" + (dds ? 1 : 0)
                    + " ddsHit=" + DDS_HIT.get()
                    + " ddsFallback=" + DDS_FALLBACK.get()
                    + " ddsDisabled=" + (dds && !DdsBridge.available() ? 1 : 0)
                    + " ddsDimMismatch=" + DDS_DIM_MISMATCH.get()
                    + " eviction=" + (eviction ? 1 : 0)
                    + " evicted=" + EVICTED.get()
                    + " evictedBytes=" + EVICTED_BYTES.get()
                    + " rematerialized=" + REMATERIALIZED.get()
                    + " evictPasses=" + EVICT_PASSES.get()
                    + " liveBytes=" + LIVE_BYTES.get()
                    + " placeholder=" + placeholderId
                    + " oldIdDeleted=" + OLD_ID_DELETED.get()
                    + " evictSkipped=" + OLD_ID_SKIPPED.get()
                    + " deferredDeletes=" + DEFERRED_DELETES.get()
                    + " selftest=" + selftestResult);
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
        int evicted;
        int rematerialized;
        volatile int glId;
        volatile long bytes;
        volatile long lastUseNanos;
        volatile boolean owned;
        volatile boolean dds;
        volatile boolean startup;
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
