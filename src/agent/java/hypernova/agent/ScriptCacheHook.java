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
    /**
     * 没有源码的 miss（探测性查询）——计数单独记，**不进命中率分母**。
     * FR 的 {@code findClass} 会被拿来查询游戏 jar 里没有源码的类
     * （如 {@code com.fs.starfarer.api.impl.*}），这类请求永远不可能命中缓存，
     * 混进分母会让"命中率"看起来永远到不了 100%，掩盖真实缓存效果。
     */
    private static final LongAdder SOURCELESS_MISSES = new LongAdder();
    private static final AtomicLong FIRST = new AtomicLong(0);
    private static final AtomicLong LAST = new AtomicLong(0);
    private static final Set<Object> PRELOADED = ConcurrentHashMap.newKeySet();
    private static final List<String> MISS_SAMPLE =
            Collections.synchronizedList(new ArrayList<>());
    /** 有源码的 miss 样本（真正的失败），最多 50 条，用于诊断。 */
    private static final List<String> SOURCED_MISS_SAMPLE =
            Collections.synchronizedList(new ArrayList<>());
    private static volatile RuntimeContext context;
    private static volatile Map<String, byte[]> currentMap;
    private static volatile String currentKey = "";
    private static volatile CacheWriter writer;
    /** agent 启动时刻，用于报告 preload/脚本阶段的绝对起点。 */
    private static final AtomicLong AGENT_START = new AtomicLong(0);
    /**
     * 源码是否存在的判定器（由运行时上下文注入）。null 表示未知，
     * 此时所有 miss 都按"有源码"计（保守：不虚报命中率）。
     */
    /**
     * 后台预计算的缓存 key。premain 时启动，preload 时取用。
     *
     * <p>为什么：{@code ScriptCacheKey.compute} 要遍历 389 个源根、对 12,277 个文件
     * 算 sha256，260mods 实测 3–15 s，而它跑在 FR loader 的构造函数里（主加载线程）。
     * premain 到 preload 之间有 20 s 左右的游戏自身初始化窗口，足够把它藏进去。
     *
     * <p>取用方用 {@link #awaitKey} 带超时等待：算不完就退回同步算，绝不无限阻塞。
     */
    private static final java.util.concurrent.CompletableFuture<String> keyFuture =
            new java.util.concurrent.CompletableFuture<>();
    private static volatile boolean keyComputationStarted;
    /** 主线程最多等这么久；超时就自己同步算（避免姿势不对时卡死启动）。 */
    private static final long KEY_AWAIT_MILLIS = 8_000L;
    private static volatile SourceOracle sourceOracle;
    private static final java.util.concurrent.atomic.AtomicBoolean oracleStarted =
            new java.util.concurrent.atomic.AtomicBoolean();

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
            try {
                AgentLog.fail("preload failed", t);
            } catch (Throwable ignored) {
                // 本方法在 FR 构造器内执行，日志 handler 自身失败也不能外抛
            }
        }
    }

    /** premain 时调用：后台线程算 key。失败也不抛——preload 会退回同步算。 */
    static void startKeyComputationAsync(RuntimeContext ctx) {
        if (keyComputationStarted) return;
        keyComputationStarted = true;
        Thread t = new Thread(() -> {
            long t0 = System.nanoTime();
            try {
                String k = ScriptCacheKey.compute(ctx).id();
                keyFuture.complete(k);
                AgentLog.info("cache key ready (background): " + k
                        + ", took " + (System.nanoTime() - t0) / 1_000_000 + " ms");
            } catch (Throwable e) {
                keyFuture.completeExceptionally(e);
                AgentLog.fail("background key computation failed", e);
            }
        }, "Hypernova-KeyPrecompute");
        t.setDaemon(true);
        t.start();
    }

    /**
     * 取缓存 key：优先用后台算好的，超时或失败则同步算。
     *
     * <p>返回 null 表示彻底失败（调用方应放弃 preload，让游戏正常编译）。
     */
    private static String awaitKey(RuntimeContext ctx) {
        if (keyComputationStarted) {
            try {
                return keyFuture.get(KEY_AWAIT_MILLIS, java.util.concurrent.TimeUnit.MILLISECONDS);
            } catch (java.util.concurrent.TimeoutException e) {
                AgentLog.info("background key not ready in " + KEY_AWAIT_MILLIS
                        + " ms; computing synchronously");
            } catch (Throwable e) {
                AgentLog.fail("background key failed; computing synchronously", e);
            }
        }
        try {
            return ScriptCacheKey.compute(ctx).id();
        } catch (Throwable e) {
            AgentLog.fail("synchronous key computation failed; cache disabled for this run", e);
            return null;
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
        // SourceOracle 绝不能在主线程上同步构建：实测在 260mods 上要扫 389 个源根，
        // 花 17.98 s（冷）/13.87 s（热），而 preload 跑在 FR loader 的构造函数里
        // ——那是游戏主加载线程。这 18 秒比缓存省下的编译时间还多，是纯负优化。
        // 改为后台线程懒加载：分类统计是诊断用途，晚几秒拿到没关系。
        initSourceOracleAsync(ctx);
        long t0 = System.nanoTime();
        String key = awaitKey(ctx);
        if (key == null) {
            AgentLog.info("no cache key; scripts cache disabled for this run");
            return;
        }
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

    /**
     * SourceOracle 诊断扫描是否启用。默认启用；{@code -Dhypernova.sourceOracle=false}
     * 可关闭，关闭后所有 miss 一律按「有源码」计，与索引构建失败时的保守口径一致。
     */
    static boolean sourceOracleEnabled() {
        return Boolean.parseBoolean(System.getProperty("hypernova.sourceOracle", "true"));
    }

    /**
     * 后台构建 {@link SourceOracle}。诊断用途，不阻塞加载。
     *
     * <p>构建完成后才开始分类 miss；在此之前所有 miss 都按"有源码"计
     * （保守方向：不虚报命中率，只会让 sourced_misses 偏大）。
     *
     * <p>用 {@code -Dhypernova.sourceOracle=false} 可关闭扫描：直接在调用线程上
     * 置入空判定器（不启动线程），miss 全按 sourced 计，缓存决策不受影响。
     */
    private static void initSourceOracleAsync(RuntimeContext ctx) {
        if (sourceOracle != null || oracleStarted.getAndSet(true)) return;
        if (!sourceOracleEnabled()) {
            sourceOracle = SourceOracle.empty();
            AgentLog.info("source oracle disabled by system property; all misses treated as sourced");
            return;
        }
        Thread t = new Thread(() -> {
            long t0 = System.nanoTime();
            try {
                SourceOracle o = SourceOracle.from(ctx);
                sourceOracle = o;
                AgentLog.info("source oracle ready: roots=" + o.roots().size()
                        + ", sources=" + o.sourceCount()
                        + ", took " + (System.nanoTime() - t0) / 1_000_000 + " ms");
            } catch (Throwable e) {
                sourceOracle = SourceOracle.empty();
                AgentLog.fail("source oracle init failed; treating all misses as sourced", e);
            }
        }, "Hypernova-SourceOracle");
        t.setDaemon(true);
        t.start();
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
                // 分类：没有源码的类永远不可能命中（FR 的 generateBytecodes
                // 返回 null → CNFE → 父 loader 兜底）。它们从命中率分母里剔除，
                // 否则报告的命中率会被这些不可缓存的探测请求稀释。
                SourceOracle o = sourceOracle;
                try {
                    if (o != null && !o.hasSource(name)) {
                        SOURCELESS_MISSES.increment();
                    } else if (SOURCED_MISS_SAMPLE.size() < 50) {
                        SOURCED_MISS_SAMPLE.add(name);
                    }
                } catch (Throwable ignored) {
                    // 判定失败按"有源码"处理（保守，不虚报命中率）
                    if (SOURCED_MISS_SAMPLE.size() < 50) SOURCED_MISS_SAMPLE.add(name);
                }
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
        if (w != null) {
            // 诊断：先把 shutdown 时 map 的真实大小写进日志，用于区分
            // “没写”和“写了一次但 map 本来就没涨”。m1d 冒烟排查用。
            try {
                AgentLog.info("shutdown: map.size="
                        + (currentMap == null ? -1 : currentMap.size())
                        + ", findCalls=" + FINDS.sum()
                        + ", hits=" + HITS.sum() + ", misses=" + MISSES.sum());
            } catch (Throwable ignored) {
            }
            w.flushNow();
            w.stop();
        }
        RuntimeContext ctx = context;
        if (ctx != null) {
            // 诊断：把 miss 样本写进日志（最多 50 条），用于判断
            // “miss 是因为没源码可编” 还是 “注入点漏了”。
            logBreakdown();
            ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                    spanMillis(), currentMap == null ? 0 : currentMap.size(),
                    SOURCELESS_MISSES.sum());
            ctx.telemetry().close();
        }
    }

    public static void summaryTick() {
        RuntimeContext ctx = context;
        if (ctx == null) return;
        ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                spanMillis(), currentMap == null ? 0 : currentMap.size(),
                SOURCELESS_MISSES.sum());
        // miss breakdown 必须在周期 tick 里写，不能只在 shutdown 里写：
        // 冒烟脚本用 taskkill /F 收尾（游戏不响应温和关闭），shutdown hook
        // **不会执行**，只在 shutdown 打的话永远拿不到分类数据（已实测踩到）。
        logBreakdown();
    }

    /** 把 miss 分类与样本写进 agent 日志。幂等、不抛异常。 */
    static void logBreakdown() {
        try {
            AgentLog.info("miss breakdown: total=" + MISSES.sum()
                    + ", sourceless=" + SOURCELESS_MISSES.sum()
                    + ", sourced=" + (MISSES.sum() - SOURCELESS_MISSES.sum()));
            List<String> sourced = sourcedMissSample();
            if (!sourced.isEmpty()) {
                AgentLog.info("sourced miss sample (" + sourced.size() + "): " + sourced);
            }
            List<String> all = missSample();
            if (!all.isEmpty()) {
                AgentLog.info("miss sample (" + all.size() + "): " + all);
            }
        } catch (Throwable ignored) {
            // 诊断日志绝不能影响游戏
        }
    }

    /** 由 premain 在注册 transformer 后调用，记录 agent 起点（用于遥测时间轴）。 */
    static void markAgentStart() {
        AGENT_START.set(System.currentTimeMillis());
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
    static List<String> sourcedMissSample() { return new ArrayList<>(SOURCED_MISS_SAMPLE); }
    static long sourcelessMisses() { return SOURCELESS_MISSES.sum(); }
    static void setSourceOracle(SourceOracle oracle) { sourceOracle = oracle; }
    /** 测试seam：注入一个可观察的 bytecodeCache，用于阶段检测的单测。 */
    static void setCurrentMapForTest(Map<String, byte[]> map) { currentMap = map; }

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
        SOURCED_MISS_SAMPLE.clear();
        SOURCELESS_MISSES.reset();
        AGENT_START.set(0);
        sourceOracle = null;
        oracleStarted.set(false);
        keyComputationStarted = false;
        context = null;
        currentMap = null;
        currentKey = "";
        writer = null;
    }
}
