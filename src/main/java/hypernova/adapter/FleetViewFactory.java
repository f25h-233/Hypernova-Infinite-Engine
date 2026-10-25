package hypernova.adapter;

import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.combat.ShipVariantAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import hypernova.hooks.FleetView;
import hypernova.hooks.VariantRef;

import java.util.ArrayList;
import java.util.List;

public final class FleetViewFactory {

    public FleetView toView(CampaignFleetAPI fleet) {
        List<String> ids = new ArrayList<>();
        for (FleetMemberAPI member : fleet.getMembersWithFightersCopy()) {
            ShipVariantAPI variant = member.getVariant();
            if (variant != null) {
                ids.add(variant.getHullVariantId());
            }
        }
        return build(fleet.getName(), ids);
    }

    /** 纯逻辑构建（单测用）：按 hullVariantId 列表产出 view，跳过 null。 */
    public FleetView build(String name, List<String> hullVariantIds) {
        List<VariantRef> refs = new ArrayList<>();
        for (String id : hullVariantIds) {
            if (id != null) {
                refs.add(new VariantRef("", id, List.of()));
            }
        }
        return new FleetView(name, refs);
    }
}
