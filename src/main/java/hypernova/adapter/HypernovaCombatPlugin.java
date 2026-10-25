package hypernova.adapter;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.combat.BaseEveryFrameCombatPlugin;
import com.fs.starfarer.api.input.InputEventAPI;
import hypernova.hooks.PostLoadWarmupHook;
import hypernova.hooks.SaveLoadGuard;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.telemetry.Telemetry;

import java.util.List;

/**
 * 每帧管线：poller → warmup → saveLoadGuard → scheduler，每 600 帧 flush 遥测。
 *
 * <p>同一份管线需要两个游戏状态的驱动，缺一个就有触发点静默失效：
 * <ul>
 *   <li><b>战斗态</b>（触发点③）：本类注册进 {@code data/config/settings.json} 的 {@code plugins}，
 *       引擎在每场战斗开始时反射构造无参实例并加入 combat engine。</li>
 *   <li><b>战役态</b>（触发点①②④⑤ + 调度器/telemetry）：本类同时实现 {@link EveryFrameScript}，
 *       装配层把它作为 transient script 挂到 sector 上。战役脚本在战斗态不会被 advance，
 *       战斗插件在战役态不存在，因此两条路径不会同帧双跑。</li>
 * </ul>
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

    private TriggerPoller poller;
    private PostLoadWarmupHook warmupHook;
    private SaveLoadGuard saveLoadGuard;
    private PrefetchScheduler scheduler;
    private Telemetry telemetry;

    private int framesSinceFlush;

    /**
     * 装配层在 onApplicationLoad 里调用（不触碰 Global），让无参实例能取到依赖。
     * 参数为 null 表示组件禁用，本就应 no-op。
     */
    public static void install(TriggerPoller poller, PostLoadWarmupHook warmupHook,
                               SaveLoadGuard saveLoadGuard, PrefetchScheduler scheduler,
                               Telemetry telemetry) {
        sharedPoller = poller;
        sharedWarmupHook = warmupHook;
        sharedSaveLoadGuard = saveLoadGuard;
        sharedScheduler = scheduler;
        sharedTelemetry = telemetry;
    }

    /** 供 {@code data/config/settings.json} 的 plugins 注册（ScriptStore 反射构造，每场战斗一次）。 */
    public HypernovaCombatPlugin() {
    }

    public HypernovaCombatPlugin(TriggerPoller poller, PostLoadWarmupHook warmupHook,
                                 SaveLoadGuard saveLoadGuard, PrefetchScheduler scheduler,
                                 Telemetry telemetry) {
        this.poller = poller;
        this.warmupHook = warmupHook;
        this.saveLoadGuard = saveLoadGuard;
        this.scheduler = scheduler;
        this.telemetry = telemetry;
    }

    /** 战斗态入口。 */
    @Override
    public void advance(float amount, List<InputEventAPI> events) {
        if (!resolve()) {
            return;
        }
        poller.tick();
        warmupHook.tick();
        saveLoadGuard.tick();
        scheduler.tick();
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
        if (p == null || w == null || g == null || s == null || t == null) {
            return false;
        }
        poller = p;
        warmupHook = w;
        saveLoadGuard = g;
        scheduler = s;
        telemetry = t;
        return true;
    }
}
