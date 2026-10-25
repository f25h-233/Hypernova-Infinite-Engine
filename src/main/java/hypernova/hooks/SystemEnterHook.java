package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.LongSupplier;

public final class SystemEnterHook {
    private final PrefetchScheduler scheduler;
    private final FleetSpriteResolver resolver;
    private final LongSupplier clockMillis;
    private final long windowMillis;
    private final Map<String, Long> lastEntered = new HashMap<>();

    public SystemEnterHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver) {
        this(scheduler, resolver, System::currentTimeMillis, 60_000L);
    }

    public SystemEnterHook(PrefetchScheduler scheduler, FleetSpriteResolver resolver,
                           LongSupplier clockMillis, long windowMillis) {
        this.scheduler = scheduler;
        this.resolver = resolver;
        this.clockMillis = clockMillis;
        this.windowMillis = windowMillis;
    }

    public void onSystemEntered(String systemId, List<FleetView> fleets) {
        long now = clockMillis.getAsLong();
        Long last = lastEntered.get(systemId);
        if (last != null && now - last < windowMillis) {
            return;
        }
        lastEntered.put(systemId, now);
        List<String> paths = new ArrayList<>();
        for (FleetView f : fleets) {
            for (String p : resolver.resolve(f)) {
                if (!paths.contains(p)) {
                    paths.add(p);
                }
            }
        }
        if (!paths.isEmpty()) {
            scheduler.enqueue(paths, Layer.L2);
        }
    }
}
