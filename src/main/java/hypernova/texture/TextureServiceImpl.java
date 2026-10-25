package hypernova.texture;

import hypernova.manifest.TextureEntry;
import hypernova.manifest.TextureManifest;
import hypernova.telemetry.Telemetry;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BooleanSupplier;

public final class TextureServiceImpl implements TextureService {
    private static final int MAX_RETRIES = 1;

    private final TextureManifest manifest;
    private final TextureBackend backend;
    private final Telemetry telemetry;
    private final Thread mainThread;
    private final BooleanSupplier loadingSave;
    private final Set<String> pending = new LinkedHashSet<>();
    private final ConcurrentHashMap<String, Integer> refCounts = new ConcurrentHashMap<>();

    public TextureServiceImpl(TextureManifest manifest,
                              TextureBackend backend,
                              Telemetry telemetry,
                              Thread mainThread,
                              BooleanSupplier loadingSave) {
        this.manifest = manifest;
        this.backend = backend;
        this.telemetry = telemetry;
        this.mainThread = mainThread;
        this.loadingSave = loadingSave;
    }

    @Override
    public TextureLoadResult ensureLoaded(String path) {
        if (Thread.currentThread() != mainThread) {
            String detail = "non-main-thread:" + Thread.currentThread().getName();
            telemetry.event("rejected", path, 0L, detail);
            throw new IllegalStateException("ensureLoaded must run on the display thread (" + detail + ")");
        }
        long start = System.nanoTime();
        TextureEntry entry = manifest.lookup(path);
        if (entry == null) {
            telemetry.event("miss", path, System.nanoTime() - start, "not-in-manifest");
            return new TextureLoadResult(false, false, System.nanoTime() - start, TextureState.MISS);
        }
        if (backend.isRegistered(path)) {
            refCounts.putIfAbsent(path, 1);
            telemetry.event("hit", path, System.nanoTime() - start, entry.modId());
            return new TextureLoadResult(true, false, System.nanoTime() - start, TextureState.LIVE);
        }
        if (loadingSave.getAsBoolean()) {
            pending.add(path);
            telemetry.event("queued", path, System.nanoTime() - start, "loading-save");
            return new TextureLoadResult(false, true, System.nanoTime() - start, TextureState.QUEUED);
        }
        boolean ok = loadWithRetry(path, entry);
        long nanos = System.nanoTime() - start;
        return new TextureLoadResult(ok, false, nanos, ok ? TextureState.LIVE : TextureState.FAILED);
    }

    private boolean loadWithRetry(String path, TextureEntry entry) {
        for (int attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            try {
                backend.load(path);
                if (backend.isRegistered(path)) {
                    refCounts.putIfAbsent(path, 1);
                    telemetry.event("loaded", path, 0L, entry.modId());
                    return true;
                }
                telemetry.event("failed", path, 0L, "load-returned-but-unregistered");
            } catch (Exception e) {
                telemetry.event("failed", path, 0L, e.getClass().getSimpleName() + ":" + e.getMessage());
            }
        }
        return false;
    }

    @Override
    public boolean isLoaded(String path) {
        return backend.isRegistered(path);
    }

    @Override
    public boolean acquire(String path) {
        if (manifest.lookup(path) == null) {
            return false;
        }
        refCounts.merge(path, 1, Integer::sum);
        return true;
    }

    @Override
    public void release(String path) {
        refCounts.computeIfPresent(path, (k, v) -> v > 1 ? v - 1 : 0);
    }

    @Override
    public boolean unload(String path) {
        telemetry.event("refused", path, 0L, "eviction-disabled");
        return false;
    }

    @Override
    public List<String> drainPending(int max) {
        if (loadingSave.getAsBoolean()) {
            return List.of();
        }
        List<String> out = new ArrayList<>(Math.max(0, Math.min(max, pending.size())));
        var it = pending.iterator();
        while (it.hasNext() && out.size() < max) {
            out.add(it.next());
            it.remove();
        }
        return out;
    }

    @Override
    public int pendingCount() {
        return pending.size();
    }
}
