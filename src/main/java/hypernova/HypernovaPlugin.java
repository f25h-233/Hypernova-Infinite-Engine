package hypernova;

import com.fs.starfarer.api.BaseModPlugin;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.SettingsAPI;
import com.fs.starfarer.api.campaign.SectorAPI;
import com.fs.starfarer.api.combat.ShipHullSpecAPI;
import com.fs.starfarer.api.combat.ShipVariantAPI;
import hypernova.adapter.FleetViewFactory;
import hypernova.adapter.GameBackend;
import hypernova.adapter.GameSpriteSource;
import hypernova.adapter.GameTelemetrySink;
import hypernova.adapter.GameWorld;
import hypernova.adapter.HypernovaCampaignListener;
import hypernova.adapter.HypernovaCombatPlugin;
import hypernova.adapter.TriggerPoller;
import hypernova.adapter.VariantLookup;
import hypernova.config.Capability;
import hypernova.config.HypernovaConfig;
import hypernova.config.VersionProbe;
import hypernova.hooks.ContactDialogHook;
import hypernova.hooks.DeploymentHook;
import hypernova.hooks.FleetDiscoveryHook;
import hypernova.hooks.FleetSpriteResolver;
import hypernova.hooks.PostLoadWarmupHook;
import hypernova.hooks.SaveLoadGuard;
import hypernova.hooks.SystemEnterHook;
import hypernova.manifest.ManifestLoader;
import hypernova.manifest.TextureManifest;
import hypernova.scheduler.FrameBudgetScheduler;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.telemetry.JsonlTelemetry;
import hypernova.telemetry.Telemetry;
import hypernova.texture.TextureServiceImpl;

public class HypernovaPlugin extends BaseModPlugin {
    private static final String CONFIG_PATH = "data/config/hypernova/hypernova.json";
    private static final int PER_TICK_CAP = 32;

    private transient boolean active;
    private transient TextureServiceImpl service;
    private transient TextureManifest manifest;
    private transient PrefetchScheduler scheduler;
    private transient Telemetry telemetry;
    private transient SaveLoadGuard saveLoadGuard;
    private transient PostLoadWarmupHook warmupHook;
    private transient FleetDiscoveryHook fleetDiscoveryHook;
    private transient ContactDialogHook contactDialogHook;
    private transient DeploymentHook deploymentHook;
    private transient SystemEnterHook systemEnterHook;
    private transient TriggerPoller poller;
    private transient HypernovaCampaignListener campaignListener;

    @Override
    public void onApplicationLoad() throws Exception {
        try {
            Global.getLogger(HypernovaPlugin.class).info(
                    "Hypernova init thread: " + Thread.currentThread().getName());
            SettingsAPI settings = Global.getSettings();
            HypernovaConfig config = HypernovaConfig.fromJson(settings.loadJSON(CONFIG_PATH));
            Capability cap = VersionProbe.probe(settings.getVersionString(), frPresent());
            if (!config.enabled() || !cap.gameOk()) {
                Global.getLogger(HypernovaPlugin.class).info(
                        "Hypernova disabled: " + (config.enabled() ? cap.reason() : "config.enabled=false"));
                return;
            }
            manifest = ManifestLoader.load(settings);
            if (manifest == null) {
                Global.getLogger(HypernovaPlugin.class).warn("Hypernova disabled: manifest unavailable");
                return;
            }
            telemetry = new JsonlTelemetry(new GameTelemetrySink(settings), config.telemetryBufferLines());
            service = new TextureServiceImpl(manifest, new GameBackend(settings), telemetry,
                    () -> Global.LOADING_SAVE);
            scheduler = new FrameBudgetScheduler(service, config.frameBudgetMicros(), PER_TICK_CAP,
                    System::nanoTime, manifest::contains);
            GameSpriteSource spriteSource = new GameSpriteSource(variantId -> {
                ShipVariantAPI v = settings.getVariant(variantId);
                if (v == null) {
                    return null;
                }
                ShipHullSpecAPI spec = v.getHullSpec();
                return spec == null ? null : new VariantLookup.Result(spec.getSpriteName());
            });
            FleetSpriteResolver resolver = new FleetSpriteResolver(spriteSource);
            fleetDiscoveryHook = new FleetDiscoveryHook(scheduler, resolver);
            contactDialogHook = new ContactDialogHook(scheduler, resolver);
            deploymentHook = new DeploymentHook(scheduler, resolver);
            systemEnterHook = new SystemEnterHook(scheduler, resolver);
            warmupHook = new PostLoadWarmupHook(scheduler, service);
            saveLoadGuard = new SaveLoadGuard(() -> Global.LOADING_SAVE, service,
                    System::nanoTime, config.frameBudgetMicros() * 1_000L);

            TriggerPoller poller = new TriggerPoller(
                    new GameWorld(), new FleetViewFactory(),
                    fleetDiscoveryHook, contactDialogHook, systemEnterHook, deploymentHook);
            this.poller = poller;

            // 自检：验证兜底能力（REQ-R1-01 的原文判据是
            // 「预取后 getSprite(TextureId) > 0」，不是「日志里没有路径」）。
            // 构造 one-shot，由首次主线程 advance 执行：FR 0.9.7 的
            // onApplicationLoad 在 Thread-N-FR-Main-Loader 上，不能在这里调用 ensureLoaded。
            final int probePaths = config.startupProbePaths();
            Runnable startupSelfCheck = probePaths > 0
                    ? () -> runFallbackSelfCheck(Math.max(1, probePaths))
                    : null;

            active = true;
            // 注入给无参的战斗插件实例（settings.json 的 plugins 由 ScriptStore 反射构造）。
            // install() 放在 active=true 之后：它之前的初始化失败不会留下「已禁用但仍运行」
            // 的静态槽位；install() 之后的失败由 catch 里的 install(null,...) 统一回滚（I2 / INV-05）。
            HypernovaCombatPlugin.install(poller, warmupHook, saveLoadGuard, scheduler, telemetry,
                    service, startupSelfCheck, config.heartbeatFrames());
            Global.getLogger(HypernovaPlugin.class).info("Hypernova active: " + cap.reason()
                    + ", manifest=" + manifest.size() + " paths, discarded=" + manifest.discardedCount()
                    + ", crossLayer=" + manifest.crossLayerConflictCount());
        } catch (Throwable t) {
            active = false;
            // 回滚静态槽位：否则 transient script / combat plugin 仍能从 static 拿到依赖，
            // 出现「日志说已禁用、管线照常运行」的自相矛盾状态（I2 / INV-05）。
            HypernovaCombatPlugin.install(null, null, null, null, null, null, null, 0);
            Global.getLogger(HypernovaPlugin.class).error("Hypernova disabled: init failure", t);
        }
    }

    /**
     * 诊断入口：供外部（测试 mod / 冒烟脚本）验证兜底能力。
     * 返回本组件是否启用；未启用时所有调用都应视为 no-op。
     */
    public boolean isActive() {
        return active;
    }

    /**
     * 诊断入口：把一条 manifest 内路径交给本组件加载，返回是否确保成功。
     * 必须在主线程调用（内部有断言）。
     */
    public boolean ensureLoadedForDiagnostics(String path) {
        return active && service != null && service.ensureLoaded(path).ok();
    }

    /** 诊断入口：路径是否已在引擎注册表里（不触发加载）。 */
    public boolean isRegisteredForDiagnostics(String path) {
        return active && service != null && service.isLoaded(path);
    }

    /** 诊断入口：manifest 内是否存在该路径。 */
    public boolean manifestContainsForDiagnostics(String path) {
        return manifest != null && manifest.contains(path);
    }

    /** 诊断入口：本组件当前状态摘要，供日志核对。 */
    public String diagnosticsSummary() {
        if (!active) {
            return "inactive";
        }
        return "active, manifest=" + manifest.size()
                + ", pending=" + service.pendingCount();
    }

    /**
     * 启动期只允许 L1 进入本组件队列（REQ-R1-05）。自检是唯一会在
     * 主线程早期取路径的入口，因此这里把候选集硬限制在 L1；L2/L3
     * 只能由运行期触发点按各自层入队。
     */
    static List<String> selfCheckCandidates(TextureManifest manifest,
                                            Predicate<String> loaded,
                                            int limit) {
        List<String> out = new ArrayList<>();
        if (limit <= 0) {
            return out;
        }
        for (String path : manifest.pathsInLayer(hypernova.manifest.Layer.L1)) {
            if (loaded.test(path)) {
                continue;
            }
            out.add(path);
            if (out.size() >= limit) {
                break;
            }
        }
        return out;
    }

    /**
     * 兜底自检（REQ-R1-01）：从 manifest 的 L1 候选里挑出「此刻 getSprite 仍为空」
     * 的路径，逐条 ensureLoaded，再查 getSprite 是否非空。
     *
     * <p>候选集只取 L1（REQ-R1-05）；L2/L3 只能由运行期触发点按各自层入队。
     *
     * <p>这是唯一不依赖外部测试 mod 的验证方式：本方法运行在主线程 + GL 上下文中，
     * 能用引擎自己的 {@code getTextureId()} 作为判据。
     *
     * <p>调用点已从 {@code onApplicationLoad} 移到首次主线程 {@code advance}：
     * FR 0.9.7 的 {@code onApplicationLoad} 在 {@code Thread-N-FR-Main-Loader} 上执行，
     * 在那里调用 {@code ensureLoaded} 必然触发主线程断言。
     */
    private void runFallbackSelfCheck(int limit) {
        var log = Global.getLogger(HypernovaPlugin.class);
        List<String> candidates = selfCheckCandidates(manifest, service::isLoaded, limit);
        log.info("selfcheck: layer=L1 candidates(not-yet-registered)=" + candidates.size());
        if (candidates.isEmpty()) {
            log.info("selfcheck: INCONCLUSIVE — every L1 manifest path is already registered in this session");
            return;
        }
        int ok = 0;
        for (String path : candidates) {
            boolean loaded = service.ensureLoaded(path).ok();
            boolean registered = service.isLoaded(path);
            if (loaded && registered) {
                ok++;
                log.info("selfcheck: LOADED " + path);
            } else {
                log.warn("selfcheck: FAILED " + path + " ok=" + loaded + " registered=" + registered);
            }
        }
        log.info("selfcheck: RESULT " + ok + "/" + candidates.size()
                + (ok == candidates.size() ? " PASS" : " FAIL"));
    }

    private static boolean frPresent() {
        try {
            Class.forName("com.genir.renderer.Version");
            return true;
        } catch (Throwable ignored) {
            return false;
        }
    }

    private void bindMainThread(String where) {
        if (!active || service == null) {
            return;
        }
        Thread thread = Thread.currentThread();
        if (service.bindMainThread(thread)) {
            Global.getLogger(HypernovaPlugin.class).info(
                    "Hypernova main thread bound at " + where + ": " + thread.getName());
        }
    }

    @Override
    public void onGameLoad(boolean newGame) {
        bindMainThread("onGameLoad");
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
        attachCampaign();
    }

    @Override
    public void onNewGame() {
        bindMainThread("onNewGame");
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
        attachCampaign();
    }

    /**
     * 战役态接线。三条通道各自独立，漏一条就是静默失效：
     * <ul>
     *   <li>{@code HypernovaCombatPlugin} 作为 transient script：战役期每帧管线（①④ + 调度器 + telemetry）；</li>
     *   <li>{@code addTransientListener}：{@code CampaignEngine.reportBattleFinished} 从
     *       {@code getAllListeners()} 派发 → 战斗结束复位 DeploymentHook；</li>
     *   <li>{@code getListenerManager().addListener}：{@code ListenerUtil.reportAboutToOpenCoreTab}
     *       从 listener manager 的 {@code CoreUITabListener} 桶派发 → 触发点②。</li>
     * </ul>
     * 两条 listener 通道必须分开注册：它们读的是两套不同的容器。
     */
    private void attachCampaign() {
        try {
            SectorAPI sector = Global.getSector();
            Global.getLogger(HypernovaPlugin.class).info(
                    "attachCampaign: sector=" + (sector != null) + ", poller=" + (poller != null)
                            + ", active=" + active);
            if (sector == null || poller == null) {
                return;
            }
            if (!sector.hasTransientScript(HypernovaCombatPlugin.class)) {
                sector.addTransientScript(new HypernovaCombatPlugin());
            }
            HypernovaCampaignListener previous = campaignListener;
            if (previous != null) {
                sector.removeListener(previous);
                sector.getListenerManager().removeListener(previous);
            }
            HypernovaCampaignListener listener = new HypernovaCampaignListener(
                    new FleetViewFactory(), contactDialogHook, deploymentHook);
            sector.addTransientListener(listener);
            sector.getListenerManager().addListener(listener, true);
            this.campaignListener = listener;
            Global.getLogger(HypernovaPlugin.class).info(
                    "attachCampaign: done, transientScript="
                            + sector.hasTransientScript(HypernovaCombatPlugin.class));
        } catch (Throwable t) {
            Global.getLogger(HypernovaPlugin.class).error("attachCampaign failed", t);
        }
    }
}
