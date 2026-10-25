package hypernova.scheduler;

import hypernova.manifest.Layer;
import hypernova.texture.TextureLoadResult;
import hypernova.texture.TextureService;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.EnumMap;
import java.util.Map;
import java.util.function.LongSupplier;
import java.util.function.Predicate;

public final class FrameBudgetScheduler implements PrefetchScheduler {
    private final TextureService service;
    private final long budgetNanos;
    private final int perTickCap;
    private final LongSupplier clock;
    private final Predicate<String> accept;
    private final Map<Layer, Deque<String>> queues = new EnumMap<>(Layer.class);

    private long queued;
    private long loaded;
    private long failed;
    private long ticks;
    private long nanosLastTick;

    public FrameBudgetScheduler(TextureService service, int frameBudgetMicros, int perTickCap, LongSupplier clock) {
        this(service, frameBudgetMicros, perTickCap, clock, p -> true);
    }

    public FrameBudgetScheduler(TextureService service, int frameBudgetMicros, int perTickCap,
                                LongSupplier clock, Predicate<String> accept) {
        this.service = service;
        this.accept = accept;
        this.budgetNanos = Math.max(1, frameBudgetMicros) * 1_000L;
        this.perTickCap = Math.max(1, perTickCap);
        this.clock = clock;
        for (Layer layer : Layer.values()) {
            queues.put(layer, new ArrayDeque<>());
        }
    }

    @Override
    public void enqueue(Iterable<String> paths, Layer layer) {
        Deque<String> q = queues.get(layer);
        for (String p : paths) {
            // manifest 外的路径不进队、不计入 queued：让 service 侧记录 MISS 即可，
            // 否则白耗帧预算与 perTickCap。
            if (!accept.test(p)) {
                continue;
            }
            q.addLast(p);
            queued++;
        }
    }

    @Override
    public void tick() {
        long start = clock.getAsLong();
        int done = 0;
        while (done < perTickCap) {
            String next = pollNext();
            if (next == null) {
                break;
            }
            TextureLoadResult r = service.ensureLoaded(next);
            done++;
            if (r.ok() || r.queued()) {
                loaded++;
            } else {
                failed++;
            }
            if (clock.getAsLong() - start >= budgetNanos) {
                break;
            }
        }
        nanosLastTick = clock.getAsLong() - start;
        ticks++;
    }

    private String pollNext() {
        for (Layer layer : Layer.values()) {
            Deque<String> q = queues.get(layer);
            if (!q.isEmpty()) {
                return q.pollFirst();
            }
        }
        return null;
    }

    @Override
    public SchedulerStats stats() {
        return new SchedulerStats(queued, loaded, failed, ticks, nanosLastTick, backlog());
    }

    @Override
    public int backlog() {
        int n = 0;
        for (Deque<String> q : queues.values()) {
            n += q.size();
        }
        return n;
    }
}
