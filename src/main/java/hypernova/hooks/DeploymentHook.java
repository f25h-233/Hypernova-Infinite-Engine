package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;

import java.util.ArrayList;
import java.util.List;

public final class DeploymentHook {
    private final PrefetchScheduler scheduler;
    private final FleetSpriteResolver resolver;
    private boolean firedThisBattle;

    public DeploymentHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver) {
        this.scheduler = scheduler;
        this.resolver = resolver;
    }

    public void onDeploymentScreen(FleetView playerFleet, FleetView enemyFleet) {
        if (firedThisBattle) {
            return;
        }
        firedThisBattle = true;
        List<String> paths = new ArrayList<>(resolver.resolve(playerFleet));
        for (String p : resolver.resolve(enemyFleet)) {
            if (!paths.contains(p)) {
                paths.add(p);
            }
        }
        if (!paths.isEmpty()) {
            scheduler.enqueue(paths, Layer.L1);
        }
    }

    /** 战斗结束时由装配层调用，允许下一场战斗再次触发。 */
    public void onBattleEnded() {
        firedThisBattle = false;
    }
}
