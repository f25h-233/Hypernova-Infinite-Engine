package hypernova.hooks;

import hypernova.texture.TextureService;

import java.util.List;
import java.util.function.BooleanSupplier;

public final class SaveLoadGuard {
    private static final int MAX_PER_TICK = 32;

    private final BooleanSupplier loadingSave;
    private final TextureService service;

    public SaveLoadGuard(BooleanSupplier loadingSave, TextureService service) {
        this.loadingSave = loadingSave;
        this.service = service;
    }

    public int tick() {
        if (loadingSave.getAsBoolean()) {
            return 0;
        }
        List<String> drained = service.drainPending(MAX_PER_TICK);
        int loaded = 0;
        for (String path : drained) {
            if (service.ensureLoaded(path).ok()) {
                loaded++;
            }
        }
        return loaded;
    }
}
