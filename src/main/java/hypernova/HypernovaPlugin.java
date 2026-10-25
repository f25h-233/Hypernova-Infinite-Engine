package hypernova;

import com.fs.starfarer.api.BaseModPlugin;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.SettingsAPI;
import com.fs.starfarer.api.combat.ShipHullSpecAPI;
import com.fs.starfarer.api.combat.ShipVariantAPI;
import hypernova.adapter.GameBackend;
import hypernova.adapter.GameSpriteSource;
import hypernova.adapter.GameTelemetrySink;
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
    }

    @Override
    public void onNewGame() {
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
    }
}
