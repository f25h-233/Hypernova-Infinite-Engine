package hypernova.texture;

import java.util.List;

public interface TextureService {
    /**
     * Bind the display/main thread. Must be called from a known main-thread
     * entrypoint ({@code onGameLoad}, {@code onNewGame}, or the first
     * {@code advance}). FR 0.9.7 runs {@code onApplicationLoad} on a worker
     * thread, so the construction thread must never be captured.
     *
     * @return true if this call established the binding; false if it was
     *         already bound, or {@code thread} is null.
     */
    boolean bindMainThread(Thread thread);

    TextureLoadResult ensureLoaded(String path);

    boolean isLoaded(String path);

    boolean acquire(String path);

    void release(String path);

    boolean unload(String path);

    List<String> drainPending(int max);

    int pendingCount();
}
