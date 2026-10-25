package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.texture.TextureService;

import java.util.List;

public final class PostLoadWarmupHook {
    private final PrefetchScheduler scheduler;
    private final TextureService service;
    private boolean pendingWarmup;

    public PostLoadWarmupHook(PrefetchScheduler scheduler, TextureService service) {
        this.scheduler = scheduler;
        this.service = service;
    }

    public void onGameLoaded() {
        pendingWarmup = true;
    }

    public void tick() {
        if (!pendingWarmup) {
            return;
        }
        List<String> drained = service.drainPending(64);
        pendingWarmup = false;
        if (!drained.isEmpty()) {
            scheduler.enqueue(drained, Layer.L3);
        }
    }
}
