package hypernova.hooks;

import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.scheduler.SchedulerStats;
import hypernova.texture.TextureLoadResult;
import hypernova.texture.TextureService;
import hypernova.texture.TextureState;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class RemainingHooksTest {

    static final class RecordingScheduler implements PrefetchScheduler {
        final List<String> queued = new ArrayList<>();
        final List<Layer> layers = new ArrayList<>();

        @Override
        public void enqueue(Iterable<String> paths, Layer layer) {
            paths.forEach(queued::add);
            layers.add(layer);
        }

        @Override
        public void tick() {
        }

        @Override
        public SchedulerStats stats() {
            return new SchedulerStats(0, 0, 0, 0, 0, 0);
        }

        @Override
        public int backlog() {
            return 0;
        }
    }

    static class StubService implements TextureService { // 非 final：I3 的预算测试要子类化

        final List<String> loaded = new ArrayList<>();
        final List<String> pending = new ArrayList<>();
        final AtomicBoolean loading;

        StubService(AtomicBoolean loading) {
            this.loading = loading;
        }

        @Override
        public boolean bindMainThread(Thread thread) {
            return false;
        }

        @Override
        public TextureLoadResult ensureLoaded(String path) {
            if (loading.get()) {
                pending.add(path);
                return new TextureLoadResult(false, true, 0L, TextureState.QUEUED);
            }
            loaded.add(path);
            return new TextureLoadResult(true, false, 0L, TextureState.LIVE);
        }

        @Override
        public boolean isLoaded(String path) {
            return false;
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
            if (loading.get()) {
                return List.of();
            }
            List<String> out = new ArrayList<>(pending.subList(0, Math.min(max, pending.size())));
            pending.removeAll(out);
            return out;
        }

        @Override
        public int pendingCount() {
            return pending.size();
        }
    }

    static FleetView fleet(String name, String variant, String sprite) {
        SpriteNameSource src = new SpriteNameSource() {
            @Override
            public List<String> hullSpriteNames() {
                return List.of();
            }

            @Override
            public List<String> weaponSpriteNames() {
                return List.of();
            }

            @Override
            public List<String> variantHullSprites(String hullVariantId) {
                return variant.equals(hullVariantId) ? List.of(sprite) : List.of();
            }
        };
        // resolver 由调用方构造；这里只造 view
        return new FleetView(name, List.of(new VariantRef("h", variant, List.of())));
    }

    static FleetSpriteResolver resolver() {
        return new FleetSpriteResolver(new SpriteNameSource() {
            @Override
            public List<String> hullSpriteNames() {
                return List.of();
            }

            @Override
            public List<String> weaponSpriteNames() {
                return List.of();
            }

            @Override
            public List<String> variantHullSprites(String hullVariantId) {
                return switch (hullVariantId) {
                    case "onslaught_Standard" -> List.of("ships/onslaught.png");
                    case "wolf_Starting" -> List.of("ships/wolf.png");
                    default -> List.of();
                };
            }
        });
    }

    @Test
    void deploymentMergesBothFleetsAsL1() {
        RecordingScheduler s = new RecordingScheduler();
        DeploymentHook h = new DeploymentHook(s, resolver());
        h.onDeploymentScreen(
                fleet("player", "onslaught_Standard", "ships/onslaught.png"),
                fleet("enemy", "wolf_Starting", "ships/wolf.png"));
        assertEquals(List.of("ships/onslaught.png", "ships/wolf.png"), s.queued);
        assertEquals(List.of(Layer.L1), s.layers);
    }

    @Test
    void deploymentEnqueuesOnlyOncePerBattle() {
        RecordingScheduler s = new RecordingScheduler();
        DeploymentHook h = new DeploymentHook(s, resolver());
        FleetView p = fleet("player", "onslaught_Standard", "ships/onslaught.png");
        FleetView e = fleet("enemy", "wolf_Starting", "ships/wolf.png");
        h.onDeploymentScreen(p, e);
        h.onDeploymentScreen(p, e);
        assertEquals(2, s.queued.size());
    }

    @Test
    void systemEnterEnqueuesAllFleetSpritesAsL2() {
        RecordingScheduler s = new RecordingScheduler();
        SystemEnterHook h = new SystemEnterHook(s, resolver(), () -> 1_000L, 60_000L);
        h.onSystemEntered("sys_a", List.of(
                fleet("f1", "onslaught_Standard", "ships/onslaught.png"),
                fleet("f2", "wolf_Starting", "ships/wolf.png")));
        assertEquals(List.of("ships/onslaught.png", "ships/wolf.png"), s.queued);
        assertEquals(List.of(Layer.L2), s.layers);
    }

    @Test
    void systemEnterDedupesWithinWindow() {
        RecordingScheduler s = new RecordingScheduler();
        SystemEnterHook h = new SystemEnterHook(s, resolver(), () -> 1_000L, 60_000L);
        List<FleetView> fleets = List.of(fleet("f1", "onslaught_Standard", "x"));
        h.onSystemEntered("sys_a", fleets);
        h.onSystemEntered("sys_a", fleets);
        assertEquals(1, s.queued.size());
    }

    @Test
    void postLoadWarmupEnqueuesDrainedPendingAsL3() {
        RecordingScheduler s = new RecordingScheduler();
        AtomicBoolean loading = new AtomicBoolean(true);
        StubService svc = new StubService(loading);
        svc.ensureLoaded("a.png");
        svc.ensureLoaded("b.png");
        loading.set(false);
        PostLoadWarmupHook h = new PostLoadWarmupHook(s, svc);
        h.onGameLoaded();
        h.tick();
        assertEquals(List.of("a.png", "b.png"), s.queued);
        assertEquals(List.of(Layer.L3), s.layers);
        h.tick();
        assertEquals(2, s.queued.size());
    }

    @Test
    void saveLoadGuardLoadsPendingOnlyAfterWindowCloses() {
        AtomicBoolean loading = new AtomicBoolean(true);
        StubService svc = new StubService(loading);
        svc.ensureLoaded("a.png");
        SaveLoadGuard g = new SaveLoadGuard(loading::get, svc);
        assertEquals(0, g.tick());
        assertEquals(1, svc.pending.size());
        loading.set(false);
        assertEquals(1, g.tick());
        assertEquals(List.of("a.png"), svc.loaded);
    }

    // 追加（brief 之外）：上面的桩把「读档窗口」守卫也复制进了 StubService.drainPending，
    // 于是 SaveLoadGuard 自己的守卫零覆盖——删掉它测试仍全绿。读档窗口内发生加载是本组件
    // 最贵的错误（REQ-R1-09 / INV-09），故用「drainPending 不设防」的桩单独锁住。
    @Test
    void saveLoadGuardBlocksDrainEvenWhenServiceIgnoresWindow() {
        AtomicBoolean windowOpen = new AtomicBoolean(true);      // 装配层报告的读档窗口
        AtomicBoolean serviceWindow = new AtomicBoolean(false);  // 桩故意不设防
        StubService svc = new StubService(serviceWindow);
        svc.pending.add("a.png");
        SaveLoadGuard g = new SaveLoadGuard(windowOpen::get, svc);
        assertEquals(0, g.tick());
        assertEquals(List.of("a.png"), svc.pending);
        assertTrue(svc.loaded.isEmpty());
    }

    // I3：SaveLoadGuard 必须有帧预算，超预算立即停手，剩余 pending 留给下一帧。
    @Test
    void saveLoadGuardStopsWhenBudgetExhausted() {
        // 桩服务每次加载让假时钟前进 1 ms；预算 1 ms → 第一张就超时。
        AtomicBoolean loading = new AtomicBoolean(false);
        long[] now = {0L};
        StubService svc = new StubService(loading) {
            @Override
            public TextureLoadResult ensureLoaded(String path) {
                now[0] += 1_000_000L; // 1 ms
                return super.ensureLoaded(path);
            }
        };
        for (int i = 0; i < 10; i++) {
            svc.pending.add("p" + i + ".png");
        }
        SaveLoadGuard g = new SaveLoadGuard(loading::get, svc, () -> now[0], 1_000_000L);
        assertEquals(1, g.tick(), "预算 1 ms、单张 1 ms：只应加载 1 张");
        assertEquals(9, svc.pending.size(), "未加载的必须留在 pending，不能丢弃");
    }

    @Test
    void saveLoadGuardLoadsAllWhenBudgetIsLarge() {
        AtomicBoolean loading = new AtomicBoolean(false);
        long[] now = {0L};
        StubService svc = new StubService(loading) {
            @Override
            public TextureLoadResult ensureLoaded(String path) {
                now[0] += 1_000L; // 1 µs
                return super.ensureLoaded(path);
            }
        };
        for (int i = 0; i < 5; i++) {
            svc.pending.add("p" + i + ".png");
        }
        SaveLoadGuard g = new SaveLoadGuard(loading::get, svc, () -> now[0], 2_000_000L);
        assertEquals(5, g.tick());
        assertEquals(0, svc.pending.size());
    }

    @Test
    void saveLoadGuardBudgetBoundaryIsInclusive() {
        // 与 FrameBudgetScheduler 一致：elapsed >= budget 即停手。
        AtomicBoolean loading = new AtomicBoolean(false);
        long[] now = {0L};
        StubService svc = new StubService(loading) {
            @Override
            public TextureLoadResult ensureLoaded(String path) {
                now[0] += 2_000_000L; // 恰好 2 ms
                return super.ensureLoaded(path);
            }
        };
        svc.pending.add("a.png");
        svc.pending.add("b.png");
        SaveLoadGuard g = new SaveLoadGuard(loading::get, svc, () -> now[0], 2_000_000L);
        assertEquals(1, g.tick(), "恰好等于预算即停手（边界含等于）");
        assertEquals(1, svc.pending.size());
    }

    // 追加（Fix loop 1）：Interfaces 的「最多连续 3 帧」语义。
    // 200 条 pending 超过 3×64=192 的单轮上限，故终止条件来自帧数封顶而非队列排空——
    // 这条同时锁住 framesLeft 递减、每帧 64 条上限、以及第 4 帧起彻底停手。
    @Test
    void warmupDrainsAcrossAtMostThreeFrames() {
        RecordingScheduler s = new RecordingScheduler();
        StubService svc = new StubService(new AtomicBoolean(false));
        for (int i = 0; i < 200; i++) {
            svc.pending.add("p" + i + ".png");
        }
        PostLoadWarmupHook h = new PostLoadWarmupHook(s, svc);
        h.onGameLoaded();
        for (int frame = 1; frame <= 5; frame++) {
            int before = s.queued.size();
            h.tick();
            if (frame <= 3) {
                assertTrue(s.queued.size() > before, "第 " + frame + " 帧应当有入队");
            } else {
                assertEquals(before, s.queued.size(), "第 " + frame + " 帧不应再入队");
            }
        }
        assertEquals(3 * 64, s.queued.size());                 // = min(200, 192)
        assertEquals(List.of("p0.png"), s.queued.subList(0, 1)); // 顺序保持
        assertEquals(200 - 192, svc.pending.size());            // 余量留给常规 drain
        assertEquals(List.of(Layer.L3, Layer.L3, Layer.L3), s.layers);
    }

    // 追加（Fix loop 1）：队列先于帧数上限耗尽时，后续帧必须空转而不是反复 enqueue。
    @Test
    void warmupStopsWhenPendingExhausted() {
        RecordingScheduler s = new RecordingScheduler();
        StubService svc = new StubService(new AtomicBoolean(false));
        svc.pending.add("a.png");
        svc.pending.add("b.png");
        PostLoadWarmupHook h = new PostLoadWarmupHook(s, svc);
        h.onGameLoaded();
        h.tick();
        assertEquals(2, s.queued.size(), "第 1 帧排空 2 条");
        h.tick();
        assertEquals(2, s.queued.size(), "第 2 帧入队 0 条");
        h.tick();
        assertEquals(2, s.queued.size(), "第 3 帧入队 0 条");
    }

    // 追加（Fix loop 1）：onGameLoaded() 必须重置帧预算，否则第二次读档只有 0 帧可用。
    @Test
    void warmupFrameBudgetResetsOnEachGameLoad() {
        RecordingScheduler s = new RecordingScheduler();
        StubService svc = new StubService(new AtomicBoolean(false));
        svc.pending.add("a.png");
        PostLoadWarmupHook h = new PostLoadWarmupHook(s, svc);
        h.onGameLoaded();
        h.tick();
        h.tick();
        h.tick();
        assertEquals(1, s.queued.size());
        svc.pending.add("b.png");
        h.tick();
        assertEquals(1, s.queued.size(), "帧预算耗尽后不应自发复活");
        h.onGameLoaded();
        h.tick();
        assertEquals(List.of("a.png", "b.png"), s.queued, "再次读档应重新获得帧预算");
    }
}
