package hypernova.adapter;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.CampaignUIAPI;
import com.fs.starfarer.api.campaign.InteractionDialogAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
import com.fs.starfarer.api.campaign.SectorEntityToken;
import com.fs.starfarer.api.combat.CombatEngineAPI;
import com.fs.starfarer.api.combat.CombatFleetManagerAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;

import java.util.ArrayList;
import java.util.List;

public final class GameWorld implements TriggerPoller.World {

    @Override
    public String currentLocationName() {
        LocationAPI loc = Global.getSector() == null ? null : Global.getSector().getCurrentLocation();
        return loc == null ? null : loc.getName();
    }

    @Override
    public boolean codexOpen() {
        return Global.getSettings().isShowingCodex();
    }

    /**
     * 触发点②的判据：对话框可见 **且** 目标是一支舰队。
     * 只看 isShowingDialog() 会把空间站、行星、market 等所有对话都算成「接触界面」。
     */
    @Override
    public boolean contactDialogOpen() {
        return contactDialogFleet() != null;
    }

    @Override
    public String contactDialogFleetName() {
        CampaignFleetAPI fleet = contactDialogFleet();
        return fleet == null ? null : fleet.getName();
    }

    @Override
    public List<String> contactDialogFleetVariantIds() {
        CampaignFleetAPI fleet = contactDialogFleet();
        if (fleet == null) {
            return List.of();
        }
        List<String> ids = new ArrayList<>();
        for (FleetMemberAPI member : fleet.getMembersWithFightersCopy()) {
            if (member.getVariant() != null) {
                ids.add(member.getVariant().getHullVariantId());
            }
        }
        return ids;
    }

    private static CampaignFleetAPI contactDialogFleet() {
        if (Global.getSector() == null) {
            return null;
        }
        CampaignUIAPI ui = Global.getSector().getCampaignUI();
        if (ui == null || !ui.isShowingDialog()) {
            return null;
        }
        InteractionDialogAPI dialog = ui.getCurrentInteractionDialog();
        if (dialog == null) {
            return null;
        }
        SectorEntityToken target = dialog.getInteractionTarget();
        return target instanceof CampaignFleetAPI fleet ? fleet : null;
    }

    @Override
    public List<CampaignFleetAPI> fleetsInLocation() {
        LocationAPI loc = Global.getSector() == null ? null : Global.getSector().getCurrentLocation();
        return loc == null ? List.of() : loc.getFleets();
    }

    @Override
    public List<CampaignFleetAPI> playerVisibleFleets() {
        List<CampaignFleetAPI> out = new ArrayList<>();
        if (Global.getSector() == null) {
            return out;
        }
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        LocationAPI loc = Global.getSector().getCurrentLocation();
        if (player == null || loc == null) {
            return out;
        }
        for (CampaignFleetAPI fleet : loc.getFleets()) {
            if (fleet != player && fleet.isVisibleToPlayerFleet()) {
                out.add(fleet);
            }
        }
        return out;
    }

    @Override
    public boolean inCombat() {
        return Global.getCombatEngine() != null;
    }

    @Override
    public List<String> deployedVariantIds() {
        List<String> ids = new ArrayList<>();
        CombatEngineAPI engine = Global.getCombatEngine();
        if (engine == null) {
            return ids;
        }
        for (int side = 0; side <= 1; side++) {
            CombatFleetManagerAPI manager = engine.getFleetManager(side);
            if (manager == null) {
                continue;
            }
            for (FleetMemberAPI m : manager.getDeployedCopy()) {
                if (m.getVariant() != null) {
                    ids.add(m.getVariant().getHullVariantId());
                }
            }
            for (FleetMemberAPI m : manager.getReservesCopy()) {
                if (m.getVariant() != null) {
                    ids.add(m.getVariant().getHullVariantId());
                }
            }
        }
        return ids;
    }
}
