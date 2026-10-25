package hypernova.adapter;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
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
    public String combatsKey() {
        CombatEngineAPI engine = Global.getCombatEngine();
        if (engine == null || engine.getContext() == null) {
            return "";
        }
        CampaignFleetAPI player = engine.getContext().getPlayerFleet();
        CampaignFleetAPI other = engine.getContext().getOtherFleet();
        return (player == null ? "?" : player.getId()) + "|" + (other == null ? "?" : other.getId());
    }

    @Override
    public boolean codexOpen() {
        return Global.getSettings().isShowingCodex();
    }

    @Override
    public boolean contactDialogOpen() {
        return Global.getSector() != null && Global.getSector().getCampaignUI().isShowingDialog();
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
