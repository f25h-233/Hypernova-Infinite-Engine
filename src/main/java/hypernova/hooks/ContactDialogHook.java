package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;

import java.util.List;

public final class ContactDialogHook {
    private final PrefetchScheduler scheduler;
    private final FleetSpriteResolver resolver;

    public ContactDialogHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver) {
        this.scheduler = scheduler;
        this.resolver = resolver;
    }

    public void onDialogShown(FleetView view) {
        List<String> paths = resolver.resolve(view);
        if (!paths.isEmpty()) {
            scheduler.enqueue(paths, Layer.L2);
        }
    }
}
