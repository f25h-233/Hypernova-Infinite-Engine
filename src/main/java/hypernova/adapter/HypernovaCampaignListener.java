package hypernova.adapter;

import com.fs.starfarer.api.campaign.BaseCampaignEventListener;
import com.fs.starfarer.api.campaign.BattleAPI;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.CoreUITabId;
import com.fs.starfarer.api.campaign.listeners.CoreUITabListener;
import hypernova.hooks.ContactDialogHook;
import hypernova.hooks.DeploymentHook;

/**
 * 两个回调走两套派发通道，必须分别注册：
 * <ul>
 *   <li>{@code reportAboutToOpenCoreTab}：{@code ListenerUtil} 从
 *       {@code getListenerManager().getListeners(CoreUITabListener.class)} 派发；</li>
 *   <li>{@code reportBattleFinished}：{@code CampaignEngine} 从 {@code getAllListeners()}
 *       （即 {@code SectorAPI.addListener/addTransientListener} 那条链）派发。</li>
 * </ul>
 * 因此基类必须是 {@code BaseCampaignEventListener}（实现 CampaignEventListener）；
 * {@code BaseFleetEventListener} 只有 FleetEventListener 的两个方法，没有 reportBattleFinished，
 * 用它会让战斗结束复位永远不被派发（第二场战斗不再触发 L1 预取）。
 */
public final class HypernovaCampaignListener extends BaseCampaignEventListener implements CoreUITabListener {

    private final FleetViewFactory factory;
    private final ContactDialogHook contactDialogHook;
    private final DeploymentHook deploymentHook;

    public HypernovaCampaignListener(FleetViewFactory factory,
                                     ContactDialogHook contactDialogHook,
                                     DeploymentHook deploymentHook) {
        // 手动注册（装配层在 onGameLoad/onNewGame 里做）：构造期不碰 Global.getSector()，
        // 否则 onApplicationLoad 阶段 sector 为 null 会 NPE。
        super(false);
        this.factory = factory;
        this.contactDialogHook = contactDialogHook;
        this.deploymentHook = deploymentHook;
    }

    @Override
    public void reportAboutToOpenCoreTab(CoreUITabId tab, Object param) {
        if (param instanceof CampaignFleetAPI fleet) {
            contactDialogHook.onDialogShown(factory.toView(fleet));
        }
    }

    @Override
    public void reportBattleFinished(CampaignFleetAPI playerFleet, BattleAPI battle) {
        deploymentHook.onBattleEnded();
    }
}
