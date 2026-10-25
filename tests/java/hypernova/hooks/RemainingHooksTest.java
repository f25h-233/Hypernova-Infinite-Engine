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

    static final class StubService implements TextureService {
        final List<String> loaded = new ArrayList<>();
        final List<String> pending = new ArrayList<>();
        final AtomicBoolean loading;

        StubService(AtomicBoolean loading) {
            this.loading = loading;
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

    // 追加（brief 之外）：brief 的 warmup 测试在第一次 tick 后 pending 已空，
    // 因此删掉「清标记」后二次 tick 仍然无事可做、测试全绿。这里在两次 tick 之间
    // 新塞一条 pending，锁定「读档预热一次即止」语义。
    @Test
    void postLoadWarmupDoesNotFireAgainAfterFlagCleared() {
        RecordingScheduler s = new RecordingScheduler();
        StubService svc = new StubService(new AtomicBoolean(false));
        svc.pending.add("a.png");
        PostLoadWarmupHook h = new PostLoadWarmupHook(s, svc);
        h.onGameLoaded();
        h.tick();
        assertEquals(List.of("a.png"), s.queued);
        svc.pending.add("later.png");
        h.tick();
        assertEquals(List.of("a.png"), s.queued);
    }
}
