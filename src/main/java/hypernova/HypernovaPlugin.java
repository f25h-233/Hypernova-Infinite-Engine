package hypernova;

import com.fs.starfarer.api.BaseModPlugin;
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
            TextureManifest manifest = ManifestLoader.load(settings);
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

            active = true;
            Global.getLogger(HypernovaPlugin.class).info("Hypernova active: " + cap.reason()
                    + ", manifest=" + manifest.size() + " paths, discarded=" + manifest.discardedCount()
                    + ", crossLayer=" + manifest.crossLayerConflictCount());
        } catch (Throwable t) {
            active = false;
            Global.getLogger(HypernovaPlugin.class).error("Hypernova disabled: init failure", t);
        }
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
        } catch (Throwable ignored) {
            // 接线失败不能让读档中断；后续 onGameLoad 会重试
        }
    }
}
