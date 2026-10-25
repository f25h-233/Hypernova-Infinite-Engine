package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.LongSupplier;

public final class FleetDiscoveryHook {
    private final PrefetchScheduler scheduler;
    private final FleetSpriteResolver resolver;
    private final LongSupplier clockMillis;
    private final long windowMillis;
    private final Map<String, Long> seen = new HashMap<>();

    public FleetDiscoveryHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver) {
        this(scheduler, resolver, System::currentTimeMillis, 300_000L);
    }

    public FleetDiscoveryHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver,
                              LongSupplier clockMillis, long windowMillis) {
        this.scheduler = scheduler;
        this.resolver = resolver;
        this.clockMillis = clockMillis;
        this.windowMillis = windowMillis;
    }

    public void onFleetDetected(FleetView view) {
        long now = clockMillis.getAsLong();
        Long last = seen.get(view.name());
        if (last != null && now - last < windowMillis) {
            return;
        }
        seen.put(view.name(), now);
        List<String> paths = resolver.resolve(view);
        if (!paths.isEmpty()) {
            scheduler.enqueue(paths, Layer.L2);
        }
    }
}
