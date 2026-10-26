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

        /** 百科（Codex）是否打开。这是**辅助预取**入口，不是 spec 的触发点②。 */
        boolean codexOpen();

        /**
         * 舰队接触对话框是否打开。实现必须校验「当前 dialog 的 target 是
         * {@link CampaignFleetAPI}」——只判断 isShowingDialog() 会把空间站/行星对话也算进来。
         */
        boolean contactDialogOpen();

        /** 接触对话框对应的舰队名；无 fleet 对话框时返回 null。 */
        String contactDialogFleetName();

        /** 接触对话框对应舰队的 hullVariantId 列表；无 fleet 对话框时返回空表。 */
        List<String> contactDialogFleetVariantIds();

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
    private boolean lastCodex;
    private boolean lastInCombat;
    private boolean lastContactDialog;
    private final Set<String> seenVisibleFleetNames = new HashSet<>();

    public TriggerPoller(World world,
                         FleetViewFactory factory,
                         FleetDiscoveryHook discoveryHook,
                         ContactDialogHook contactDialogHook,
                         SystemEnterHook systemHook,
                         DeploymentHook deploymentHook) {
        this.world = world;
        this.factory = factory;
        this.discoveryHook = discoveryHook;
        this.contactHook = contactDialogHook;
        this.systemHook = systemHook;
        this.deploymentHook = deploymentHook;
    }

    public void tick() {
        try {
            tickLocation();
            tickCombat();
            tickContactDialog();
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

    /**
     * 触发点②：舰队接触对话框上升沿。只预取对话框指向的那支舰队（spec 的原文语义），
     * 不再把「打开百科」当成接触界面（I6）。
     */
    private void tickContactDialog() {
        boolean open = world.contactDialogOpen();
        boolean rising = open && !lastContactDialog;
        lastContactDialog = open;
        if (!rising) {
            return;
        }
        String name = world.contactDialogFleetName();
        if (name == null) {
            return; // dialog 存在但 target 不是舰队：实现层已经过滤，这里再兜一层
        }
        contactHook.onDialogShown(factory.build(name, world.contactDialogFleetVariantIds()));
    }

    /**
     * 百科辅助预取（不是触发点②）：打开百科时把当前星系内舰队按 L2 入队。
     * 与接触界面共用 {@link ContactDialogHook}（同为 L2，语义都是「即时场景的大图」）。
     */
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
