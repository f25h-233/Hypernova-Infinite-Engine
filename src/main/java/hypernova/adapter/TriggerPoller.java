package hypernova.adapter;

import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import hypernova.hooks.ContactDialogHook;
import hypernova.hooks.DeploymentHook;
import hypernova.hooks.FleetDiscoveryHook;
import hypernova.hooks.FleetView;
import hypernova.hooks.SystemEnterHook;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class TriggerPoller {

    public interface World {
        String currentLocationName();

        String combatsKey();

        boolean codexOpen();

        boolean contactDialogOpen();

        List<CampaignFleetAPI> fleetsInLocation();

        List<CampaignFleetAPI> playerVisibleFleets();

        boolean inCombat();

        List<String> deployedVariantIds();
    }

    private final World world;
    private final FleetViewFactory factory;
    private final FleetDiscoveryHook discoveryHook;
    private final ContactDialogHook contactHook;
    private final SystemEnterHook systemHook;
    private final DeploymentHook deploymentHook;

    private String lastLocation;
    private String lastCombatsKey = "";
    private boolean lastCodex;
    private boolean lastInCombat;
    private final Set<String> seenVisibleFleetNames = new HashSet<>();

    public TriggerPoller(World world,
                         FleetViewFactory factory,
                         FleetDiscoveryHook discoveryHook,
                         ContactDialogHook contactHook,
                         SystemEnterHook systemHook,
                         DeploymentHook deploymentHook) {
        this.world = world;
        this.factory = factory;
        this.discoveryHook = discoveryHook;
        this.contactHook = contactHook;
        this.systemHook = systemHook;
        this.deploymentHook = deploymentHook;
    }

    public void tick() {
        try {
            tickLocation();
            tickCombat();
            tickCodex();
            tickVisibleFleets();
        } catch (Throwable t) {
            // 只记首次，避免每帧刷屏；仍然不打断游戏（INV-05 的失败方向）
            if (firstTickError == null) {
                firstTickError = t;
                com.fs.starfarer.api.Global.getLogger(TriggerPoller.class)
                        .error("TriggerPoller.tick failed (reported once)", t);
            }
        }
    }

    private Throwable firstTickError;

    private void tickLocation() {
        String location = world.currentLocationName();
        if (location == null || location.equals(lastLocation)) {
            return;
        }
        lastLocation = location;
        systemHook.onSystemEntered(location, views(world.fleetsInLocation()));
    }

    private void tickCombat() {
        boolean combat = world.inCombat();
        boolean rising = combat && !lastInCombat;
        lastInCombat = combat;
        if (!rising) {
            return;
        }
        deploymentHook.onDeploymentScreen(
                factory.build("combat", world.deployedVariantIds()),
                factory.build("enemy", List.of()));
    }

    private void tickCodex() {
        boolean open = world.codexOpen();
        boolean rising = open && !lastCodex;
        lastCodex = open;
        if (!rising) {
            return;
        }
        for (FleetView view : views(world.fleetsInLocation())) {
            contactHook.onDialogShown(view);
        }
    }

    private void tickVisibleFleets() {
        for (CampaignFleetAPI fleet : world.playerVisibleFleets()) {
            String name = fleet.getName();
            if (name != null && seenVisibleFleetNames.add(name)) {
                discoveryHook.onFleetDetected(factory.toView(fleet));
            }
        }
    }

    private List<FleetView> views(List<CampaignFleetAPI> fleets) {
        List<FleetView> out = new ArrayList<>(fleets.size());
        for (CampaignFleetAPI fleet : fleets) {
            out.add(factory.toView(fleet));
        }
        return out;
    }
}
