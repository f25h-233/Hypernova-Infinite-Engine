package hypernova.adapter;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.combat.BaseEveryFrameCombatPlugin;
import com.fs.starfarer.api.input.InputEventAPI;
import hypernova.hooks.PostLoadWarmupHook;
import hypernova.hooks.SaveLoadGuard;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.telemetry.Telemetry;
import hypernova.texture.TextureService;

import java.util.List;

/**
 * 每帧管线：poller → warmup → saveLoadGuard → scheduler，每 600 帧 flush 遥测。
 *
 * <p>同一份管线需要两个游戏状态的驱动，缺一个就有触发点静默失效：
 * <ul>
 *   <li><b>战斗态</b>（触发点③）：本类注册进 {@code data/config/settings.json} 的 {@code plugins}，
 *       引擎在每场战斗开始时反射构造无参实例并加入 combat engine。</li>
 *   <li><b>战役态</b>（触发点①②④⑤ + 调度器/telemetry）：本类同时实现 {@link EveryFrameScript}，
 *       装配层把它作为 transient script 挂到 sector 上。</li>
 * </ul>
 * 两条挂载路径的实例身份、类加载器都无法保证唯一（settings.json 由 ScriptStore 反射构造），
 * 实机日志已证明出现过同帧双跑，故 advance 开头用 {@link FrameAdvanceGate} 做幂等门闩。
 * 无参实例（引擎反射构造）从 {@link #install} 置入的共享依赖取参数；配置禁用时共享依赖为 null，
 * 整条管线 no-op（INV-05）。
 */
public final class HypernovaCombatPlugin extends BaseEveryFrameCombatPlugin implements EveryFrameScript {
    private static final int FLUSH_EVERY_FRAMES = 600;

    private static volatile TriggerPoller sharedPoller;
    private static volatile PostLoadWarmupHook sharedWarmupHook;
    private static volatile SaveLoadGuard sharedSaveLoadGuard;
    private static volatile PrefetchScheduler sharedScheduler;
    private static volatile Telemetry sharedTelemetry;
    private static volatile TextureService sharedService;
    /** One-shot diagnostic, run on the first main-thread advance (may be null). */
    private static volatile Runnable sharedStartupSelfCheck;
    /** 心跳频率（帧）：0 关闭，1 每帧，N>1 每 N 帧。原 verbose 死开关的替代（Minor）。 */
    private static volatile int sharedHeartbeatFrames = 3000;
    /** M4 frame-time probe；null = 关闭（零采样成本）。 */
    private static volatile FrameTimeProbe sharedFrameProbe;
    /** 双入口共享的门闩：同帧第二次 advance（另一个实例/另一个入口）直接 return（I1）。 */
    private static final FrameAdvanceGate GATE = new FrameAdvanceGate(5_000_000L);

    private TriggerPoller poller;
    private PostLoadWarmupHook warmupHook;
    private SaveLoadGuard saveLoadGuard;
    private PrefetchScheduler scheduler;
    private Telemetry telemetry;
    private TextureService service;
    private FrameTimeProbe frameProbe;

    private int framesSinceFlush;
    private long tickCount;
    private int heartbeatFrames = 3000;

    /**
     * 装配层在 onApplicationLoad 里调用（不触碰 Global），让无参实例能取到依赖。
     * 参数为 null 表示组件禁用，本就应 no-op。
     */
    public static void install(TriggerPoller poller, PostLoadWarmupHook warmupHook,
                               SaveLoadGuard saveLoadGuard, PrefetchScheduler scheduler,
                               Telemetry telemetry, TextureService service,
                               Runnable startupSelfCheck, int heartbeatFrames,
                               FrameTimeProbe frameProbe) {
        sharedPoller = poller;
        sharedWarmupHook = warmupHook;
        sharedSaveLoadGuard = saveLoadGuard;
        sharedScheduler = scheduler;
        sharedTelemetry = telemetry;
        sharedService = service;
        sharedStartupSelfCheck = startupSelfCheck;
        sharedHeartbeatFrames = heartbeatFrames;
        sharedFrameProbe = frameProbe;
    }

    /** 供 {@code data/config/settings.json} 的 plugins 注册（ScriptStore 反射构造，每场战斗一次）。 */
    public HypernovaCombatPlugin() {
    }

    /** 战斗态入口。 */
    @Override
    public void advance(float amount, List<InputEventAPI> events) {
        if (!resolve()) {
            return;
        }
        TextureService svc = service;
        if (svc != null && svc.bindMainThread(Thread.currentThread())) {
            com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).info(
                    "Hypernova main thread bound at advance: " + Thread.currentThread().getName());
        }
        Runnable selfCheck = sharedStartupSelfCheck;
        if (selfCheck != null && !com.fs.starfarer.api.Global.LOADING_SAVE) {
            sharedStartupSelfCheck = null;
            try {
                selfCheck.run();
            } catch (Throwable t) {
                com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).error(
                        "startup self-check failed", t);
            }
        }
        // I1：战役态 transient script 与战斗态插件是两个实例、共享同一调度器。
        // 同帧第二个入口不推进管线，否则预算、perTickCap 与 flush 节流全部按 2 倍速消耗。
        if (!GATE.shouldRun(scheduler, scheduler.stats().ticks(), System.nanoTime())) {
            return;
        }
        poller.tick();
        warmupHook.tick();
        saveLoadGuard.tick();
        scheduler.tick();
        long now = System.nanoTime();
        long ticks = scheduler.stats().ticks();
        GATE.completed(scheduler, ticks, now);
        tickCount++;
        // M4：探针在门闩之后，并按引擎帧 amount 去重；关闭时只做一次 null 检查。
        FrameTimeProbe probe = frameProbe;
        if (probe != null) {
            probe.frame(now, amount);
            String frameLine = probe.lineIfDue();
            if (frameLine != null) {
                com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class)
                        .info(frameLine);
            }
        }
        int hb = heartbeatFrames;
        if (hb > 0 && tickCount % hb == 1) {
            com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).info(
                    "HYPERNOVA_TICK " + tickCount + " " + scheduler.stats());
        }
        if (++framesSinceFlush >= FLUSH_EVERY_FRAMES) {
            framesSinceFlush = 0;
            telemetry.flush();
        }
    }

    /** 战役态入口（transient script）。 */
    @Override
    public void advance(float amount) {
        advance(amount, List.of());
    }

    @Override
    public boolean isDone() {
        return false;
    }

    @Override
    public boolean runWhilePaused() {
        return false;
    }

    private boolean resolve() {
        if (poller != null) {
            return true;
        }
        TriggerPoller p = sharedPoller;
        PostLoadWarmupHook w = sharedWarmupHook;
        SaveLoadGuard g = sharedSaveLoadGuard;
        PrefetchScheduler s = sharedScheduler;
        Telemetry t = sharedTelemetry;
        TextureService svc = sharedService;
        if (p == null || w == null || g == null || s == null || t == null || svc == null) {
            return false;
        }
        poller = p;
        warmupHook = w;
        saveLoadGuard = g;
        scheduler = s;
        telemetry = t;
        service = svc;
        heartbeatFrames = sharedHeartbeatFrames;
        frameProbe = sharedFrameProbe;
        return true;
    }
}
