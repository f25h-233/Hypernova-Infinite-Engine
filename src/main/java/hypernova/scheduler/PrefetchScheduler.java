package hypernova.scheduler;

import hypernova.manifest.Layer;

public interface PrefetchScheduler {
    void enqueue(Iterable<String> paths, Layer layer);

    void tick();

    SchedulerStats stats();

    int backlog();
}
