package hypernova.scheduler;

import hypernova.manifest.Layer;
import hypernova.manifest.TextureManifest;
import hypernova.telemetry.Telemetry;
import hypernova.texture.TextureLoadResult;
import hypernova.texture.TextureService;
import hypernova.texture.TextureState;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class FrameBudgetSchedulerTest {

    // json.jar 是 2010 版 org.json，put(...) 抛受检 JSONException，故辅助方法显式声明 throws。
    static TextureManifest manifest(int n) throws JSONException {
        JSONObject root = new JSONObject();
        JSONObject layers = new JSONObject();
        JSONArray l1 = new JSONArray();
        for (int i = 0; i < n; i++) {
            JSONObject e = new JSONObject();
            e.put("path", "p" + i);
            e.put("modId", "m");
            e.put("w", 1);
            e.put("h", 1);
            e.put("baked", true);
            l1.put(e);
        }
        layers.put("L1", l1);
        layers.put("L2", new JSONArray());
        layers.put("L3", new JSONArray());
        root.put("layers", layers);
        return TextureManifest.fromJson(root);
    }

    /**
     * 可控耗时：每次 ensureLoaded 让假时钟前进 sleepMillis。
     * 假时钟由测试持有并注入调度器，两边共用同一个时间源。
     */
    static final class StubService implements TextureService {
        final List<String> loaded = new ArrayList<>();
        final Set<String> known;
        long sleepMillis;
        long nowNanos;

        StubService(Set<String> known) {
            this.known = known;
        }

        @Override
        public TextureLoadResult ensureLoaded(String path) {
            loaded.add(path);
            if (sleepMillis > 0) {
                nowNanos += sleepMillis * 1_000_000L;
            }
            return new TextureLoadResult(known.contains(path), false, sleepMillis * 1_000_000L, TextureState.LIVE);
        }

        @Override
        public boolean isLoaded(String path) {
            return known.contains(path);
        }

        @Override
        public boolean acquire(String path) {
            return true;
        }

        @Override
        public void release(String path) {
        }

        @Override
        public boolean unload(String path) {
            return false;
        }

        @Override
        public List<String> drainPending(int max) {
            return List.of();
        }

        @Override
        public int pendingCount() {
            return 0;
        }
    }

    static final class NoTelemetry implements Telemetry {
        @Override
        public void event(String kind, String path, long nanos, String detail) {
        }

        @Override
        public void flush() {
        }

        @Override
        public int buffered() {
            return 0;
        }
    }

    @Test
    void drainsWithinBudget() {
        StubService svc = new StubService(Set.of("p0", "p1", "p2", "p3"));
        List<String> paths = List.of("p0", "p1", "p2", "p3");
        // 预算 10 ms，4 张各 1 ms，全部在预算内。
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 10_000, 100, () -> svc.nowNanos);
        s.enqueue(paths, Layer.L1);
        assertEquals(4, s.backlog());
        svc.sleepMillis = 1;
        s.tick();
        assertEquals(4, svc.loaded.size());
        assertEquals(0, s.backlog());
    }

    @Test
    void stopsWhenBudgetExhausted() {
        StubService svc = new StubService(Set.of("p0", "p1", "p2", "p3", "p4"));
        // 预算 2 ms，每张 1 ms：应加载 2 张后停手。
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 2_000, 100, () -> svc.nowNanos);
        s.enqueue(List.of("p0", "p1", "p2", "p3", "p4"), Layer.L1);
        svc.sleepMillis = 1; // 每张 1 ms
        s.tick();
        assertTrue(svc.loaded.size() >= 1);
        assertTrue(svc.loaded.size() < 5, "should stop before draining all: " + svc.loaded.size());
        assertTrue(s.backlog() > 0);
    }

    @Test
    void singleOverBudgetItemCompletesThenStops() {
        StubService svc = new StubService(Set.of("a", "b"));
        // 预算 1 ms，单张 5 ms：第一张允许完成后本帧停止。
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 1_000, 100, () -> svc.nowNanos);
        s.enqueue(List.of("a", "b"), Layer.L1);
        svc.sleepMillis = 5; // 单张 5 ms > 1 ms 预算
        s.tick();
        assertEquals(List.of("a"), svc.loaded);
        assertEquals(1, s.backlog());
    }

    @Test
    void perTickCapPreventsStarvation() {
        StubService svc = new StubService(Set.of("p0", "p1", "p2"));
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 10_000_000, 2, () -> svc.nowNanos);
        s.enqueue(List.of("p0", "p1", "p2"), Layer.L1);
        svc.sleepMillis = 0;
        s.tick();
        assertEquals(2, svc.loaded.size());
        s.tick();
        assertEquals(3, svc.loaded.size());
        assertEquals(0, s.backlog());
    }

    @Test
    void higherLayerWinsWhenBacklogged() {
        StubService svc = new StubService(Set.of("l3a", "l1a"));
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 10_000_000, 1, () -> svc.nowNanos);
        s.enqueue(List.of("l3a"), Layer.L3);
        s.enqueue(List.of("l1a"), Layer.L1);
        s.tick();
        assertEquals(List.of("l1a"), svc.loaded);
    }

    @Test
    void statsAccumulate() {
        StubService svc = new StubService(Set.of("a"));
        FrameBudgetScheduler s = new FrameBudgetScheduler(svc, 10_000_000, 10, () -> svc.nowNanos);
        s.enqueue(List.of("a"), Layer.L1);
        s.tick();
        SchedulerStats st = s.stats();
        assertEquals(1, st.queued());
        assertEquals(1, st.loaded());
        assertEquals(0, st.failed());
        assertEquals(1, st.ticks());
    }
}
