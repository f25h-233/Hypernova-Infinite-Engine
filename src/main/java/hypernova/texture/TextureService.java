package hypernova.texture;

import java.util.List;

public interface TextureService {
    TextureLoadResult ensureLoaded(String path);

    boolean isLoaded(String path);

    boolean acquire(String path);

    void release(String path);

    boolean unload(String path);

    List<String> drainPending(int max);

    int pendingCount();
}
