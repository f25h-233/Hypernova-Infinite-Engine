package hypernova;

import com.fs.starfarer.api.BaseModPlugin;

import java.util.List;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.SettingsAPI;
import com.fs.starfarer.api.campaign.CampaignEventListener;
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
            telemetry = new JsonlTelemetry(new GameTelemetrySink(settings), config.telemetryBufferLines(), config.verbose());
            service = new TextureServiceImpl(manifest, new GameBackend(settings), telemetry,
                    Thread.currentThread(), () -> Global.LOADING_SAVE);
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
            saveLoadGuard = new SaveLoadGuard(() -> Global.LOADING_SAVE, service);

            TriggerPoller poller = new TriggerPoller(
                    new GameWorld(), new FleetViewFactory(),
                    fleetDiscoveryHook, contactDialogHook, systemEnterHook, deploymentHook);
            this.poller = poller;
            // 注入给无参的战斗插件实例（settings.json 的 plugins 由 ScriptStore 反射构造）。
            // 组件禁用时这里根本不会执行，共享依赖保持 null → 整条管线 no-op（INV-05）。
            HypernovaCombatPlugin.install(poller, warmupHook, saveLoadGuard, scheduler, telemetry);

            // 自检：直接在装配点验证兜底能力（REQ-R1-01 的原文判据是
            // 「预取后 getSprite(TextureId) > 0」，不是「日志里没有路径」）。
            // 这里在 onApplicationLoad 里跑一次，结果写日志，外部无需任何测试 mod。
            if (config.startupProbePaths() > 0) {
                runFallbackSelfCheck(Math.max(1, config.startupProbePaths()));
            }

            active = true;
            Global.getLogger(HypernovaPlugin.class).info("Hypernova active: " + cap.reason()
                    + ", manifest=" + manifest.size() + " paths, discarded=" + manifest.discardedCount()
                    + ", crossLayer=" + manifest.crossLayerConflictCount());
        } catch (Throwable t) {
            active = false;
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
     * 兜底自检（REQ-R1-01）：从 manifest 里挑出「此刻 getSprite 仍为空」的路径，
     * 逐条 ensureLoaded，再查 getSprite 是否非空。
     *
     * <p>这是唯一不依赖外部测试 mod 的验证方式：本方法运行在主线程 + GL 上下文中，
     * 能用引擎自己的 {@code getTextureId()} 作为判据。
     */
    private void runFallbackSelfCheck(int limit) {
        var log = Global.getLogger(HypernovaPlugin.class);
        List<String> candidates = new java.util.ArrayList<>();
        for (hypernova.manifest.Layer layer : hypernova.manifest.Layer.values()) {
            for (String path : manifest.pathsInLayer(layer)) {
                if (service.isLoaded(path)) {
                    continue; // 已注册 → 走不到兜底路径
                }
                candidates.add(path);
                if (candidates.size() >= limit) {
                    break;
                }
            }
            if (candidates.size() >= limit) {
                break;
            }
        }
        log.info("selfcheck: candidates(not-yet-registered)=" + candidates.size());
        if (candidates.isEmpty()) {
            log.info("selfcheck: INCONCLUSIVE — every manifest path is already registered in this session");
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

    @Override
    public void onGameLoad(boolean newGame) {
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
        attachCampaign();
    }

    @Override
    public void onNewGame() {
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
