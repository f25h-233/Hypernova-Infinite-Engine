package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.texture.TextureService;

import java.util.List;

public final class PostLoadWarmupHook {
    private static final int MAX_FRAMES = 3;
    private static final int DRAIN_PER_FRAME = 64;

    private final PrefetchScheduler scheduler;
    private final TextureService service;
    private boolean pendingWarmup;
    private int framesLeft;

    public PostLoadWarmupHook(PrefetchScheduler scheduler, TextureService service) {
        this.scheduler = scheduler;
        this.service = service;
    }

    public void onGameLoaded() {
        pendingWarmup = true;
        framesLeft = MAX_FRAMES;
    }

    /**
     * 分帧排空待加载队列：最多 {@value #MAX_FRAMES} 帧、每帧 {@value #DRAIN_PER_FRAME} 条。
     * 用帧数封顶而不是「一次排空」，避免读档后单帧突发；超过上限的余量留给
     * SaveLoadGuard 的常规 drain 路径继续消化。
     */
    public void tick() {
        if (!pendingWarmup || framesLeft <= 0) {
            return;
        }
        framesLeft--;
        List<String> drained = service.drainPending(DRAIN_PER_FRAME);
        if (framesLeft == 0) {
            pendingWarmup = false;
        }
        if (!drained.isEmpty()) {
            scheduler.enqueue(drained, Layer.L3);
        }
    }
}
