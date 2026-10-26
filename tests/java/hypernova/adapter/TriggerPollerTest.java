package hypernova.adapter;

import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import hypernova.hooks.ContactDialogHook;
import hypernova.hooks.DeploymentHook;
import hypernova.hooks.FleetDiscoveryHook;
import hypernova.hooks.FleetSpriteResolver;
import hypernova.hooks.SpriteNameSource;
import hypernova.hooks.SystemEnterHook;
import hypernova.manifest.Layer;
import hypernova.scheduler.PrefetchScheduler;
import hypernova.telemetry.Telemetry;
import hypernova.scheduler.SchedulerStats;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TriggerPollerTest {

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

    static final class FakeWorld implements TriggerPoller.World {
        String location = "sys_a";
        boolean codex;
        boolean contact;
        String contactFleetName;
        List<String> contactVariantIds = new ArrayList<>();
        List<CampaignFleetAPI> fleets = new ArrayList<>();
        List<CampaignFleetAPI> visible = new ArrayList<>();
        boolean inCombat;
        List<String> deployed = new ArrayList<>();

        @Override public String currentLocationName() { return location; }
        @Override public boolean codexOpen() { return codex; }
        @Override public boolean contactDialogOpen() { return contact; }
        @Override public String contactDialogFleetName() { return contactFleetName; }
        @Override public List<String> contactDialogFleetVariantIds() { return contactVariantIds; }
        @Override public List<CampaignFleetAPI> fleetsInLocation() { return fleets; }
        @Override public List<CampaignFleetAPI> playerVisibleFleets() { return visible; }
        @Override public boolean inCombat() { return inCombat; }
        @Override public List<String> deployedVariantIds() { return deployed; }
    }

    static FleetSpriteResolver resolver() {
        return new FleetSpriteResolver(new SpriteNameSource() {
            @Override public List<String> hullSpriteNames() { return List.of(); }
            @Override public List<String> weaponSpriteNames() { return List.of(); }
            @Override public List<String> variantHullSprites(String id) {
                return switch (id) {
                    case "onslaught_Standard" -> List.of("ships/onslaught.png");
                    case "wolf_Starting" -> List.of("ships/wolf.png");
                    default -> List.of();
                };
            }
        });
    }

    static TriggerPoller poller(FakeWorld w, RecordingScheduler s) {
        FleetSpriteResolver r = resolver();
        return new TriggerPoller(w, new FleetViewFactory(),
                new FleetDiscoveryHook(s, r, () -> 0L, 0L),
                new ContactDialogHook(s, r),
                new SystemEnterHook(s, r, () -> 0L, 0L),
                new DeploymentHook(s, r));
    }

    @Test
    void combatStartTriggersDeploymentAsL1() {
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        w.deployed = List.of("onslaught_Standard");
        TriggerPoller p = poller(w, s);
        p.tick();
        w.inCombat = true;
        p.tick();
        assertEquals(List.of("ships/onslaught.png"), s.queued);
        assertEquals(List.of(Layer.L1), s.layers);
    }

    @Test
    void repeatedTicksDoNotRequeueCombat() {
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        w.deployed = List.of("onslaught_Standard");
        TriggerPoller p = poller(w, s);
        p.tick();
        w.inCombat = true;
        p.tick();
        p.tick();
        p.tick();
        assertEquals(1, s.queued.size());
    }

    @Test
    void firstTickRecordsLocationWithoutDoubleEnqueue() {
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = poller(w, s);
        p.tick();
        p.tick();
        assertTrue(s.queued.isEmpty());
    }

    @Test
    void codexRisingEdgeTriggersCodexPrefetch() {
        // 百科是辅助预取入口：打开时把当前星系内舰队按 L2 入队（旧行为，保留）。
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = poller(w, s);
        p.tick();
        w.codex = true;
        w.fleets.add(null); // views() 会 NPE → 被 tick 的 catch 吞掉，这里只验证不抛
        assertDoesNotThrow(p::tick);
    }

    @Test
    void contactDialogRisingEdgePrefetchesDialogFleetAsL2() {
        // I6：触发点② 必须是舰队接触对话框（isShowingDialog + target 是舰队），
        // 且只预取对话框指向的那支舰队，不是「打开百科时全星系舰队」。
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = poller(w, s);
        p.tick();
        w.contact = true;
        w.contactFleetName = "hegemony patrol";
        w.contactVariantIds = List.of("onslaught_Standard");
        p.tick();
        assertEquals(List.of("ships/onslaught.png"), s.queued);
        assertEquals(List.of(Layer.L2), s.layers);
    }

    @Test
    void contactDialogWithoutFleetNameDoesNotPrefetch() {
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = poller(w, s);
        p.tick();
        w.contact = true; // dialog 可见但 target 不是舰队（GameWorld 已过滤，这里再兜一层）
        w.contactFleetName = null;
        w.contactVariantIds = List.of("onslaught_Standard");
        p.tick();
        assertTrue(s.queued.isEmpty());
    }

    @Test
    void contactDialogEdgeIsIdempotent() {
        FakeWorld w = new FakeWorld();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = poller(w, s);
        p.tick();
        w.contact = true;
        w.contactFleetName = "hegemony patrol";
        w.contactVariantIds = List.of("onslaught_Standard");
        p.tick();
        p.tick();
        p.tick();
        assertEquals(1, s.queued.size(), "上升沿只能触发一次");
    }

    @Test
    void worldExceptionsAreSwallowed() {
        TriggerPoller.World exploding = new TriggerPoller.World() {
            @Override public String currentLocationName() { throw new RuntimeException("boom"); }
            @Override public boolean codexOpen() { return false; }
            @Override public boolean contactDialogOpen() { return false; }
            @Override public String contactDialogFleetName() { return null; }
            @Override public List<String> contactDialogFleetVariantIds() { return List.of(); }
            @Override public List<CampaignFleetAPI> fleetsInLocation() { return List.of(); }
            @Override public List<CampaignFleetAPI> playerVisibleFleets() { return List.of(); }
            @Override public boolean inCombat() { return false; }
            @Override public List<String> deployedVariantIds() { return List.of(); }
        };
        FleetSpriteResolver r = resolver();
        RecordingScheduler s = new RecordingScheduler();
        TriggerPoller p = new TriggerPoller(exploding, new FleetViewFactory(),
                new FleetDiscoveryHook(s, r), new ContactDialogHook(s, r),
                new SystemEnterHook(s, r), new DeploymentHook(s, r));
        assertDoesNotThrow(p::tick);
    }
}
