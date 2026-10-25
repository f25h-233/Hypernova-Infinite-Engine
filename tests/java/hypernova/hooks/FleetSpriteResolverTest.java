package hypernova.hooks;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FleetSpriteResolverTest {

    static final class StubSource implements SpriteNameSource {
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
                case "onslaught_Standard" -> List.of("graphics/ships/onslaught.png");
                case "wolf_Starting" -> List.of("graphics/ships/wolf.png");
                default -> List.of();
            };
        }
    }

    @Test
    void resolvesHullSpritePerMember() {
        FleetSpriteResolver r = new FleetSpriteResolver(new StubSource());
        List<String> out = r.resolve(new FleetView("heg", List.of(
                new VariantRef("onslaught", "onslaught_Standard", List.of()))));
        assertEquals(List.of("graphics/ships/onslaught.png"), out);
    }

    @Test
    void deduplicatesAndPreservesOrder() {
        FleetSpriteResolver r = new FleetSpriteResolver(new StubSource());
        List<String> out = r.resolve(new FleetView("heg", List.of(
                new VariantRef("onslaught", "onslaught_Standard", List.of()),
                new VariantRef("onslaught", "onslaught_Standard", List.of()),
                new VariantRef("wolf", "wolf_Starting", List.of()))));
        assertEquals(List.of("graphics/ships/onslaught.png", "graphics/ships/wolf.png"), out);
    }

    @Test
    void unknownVariantContributesNothing() {
        FleetSpriteResolver r = new FleetSpriteResolver(new StubSource());
        List<String> out = r.resolve(new FleetView("x", List.of(
                new VariantRef("mystery", "mystery_Standard", List.of()))));
        assertTrue(out.isEmpty());
    }

    @Test
    void hookEnqueuesResolvedPaths() {
        List<String> enqueued = new ArrayList<>();
        List<hypernova.manifest.Layer> layers = new ArrayList<>();
        hypernova.scheduler.PrefetchScheduler sched = new hypernova.scheduler.PrefetchScheduler() {
            @Override
            public void enqueue(Iterable<String> paths, hypernova.manifest.Layer layer) {
                paths.forEach(enqueued::add);
                layers.add(layer);
            }

            @Override
            public void tick() {
            }

            @Override
            public hypernova.scheduler.SchedulerStats stats() {
                return new hypernova.scheduler.SchedulerStats(0, 0, 0, 0, 0, 0);
            }

            @Override
            public int backlog() {
                return 0;
            }
        };
        FleetDiscoveryHook hook = new FleetDiscoveryHook(sched, new FleetSpriteResolver(new StubSource()));
        hook.onFleetDetected(new FleetView("heg", List.of(
                new VariantRef("onslaught", "onslaught_Standard", List.of()))));
        assertEquals(List.of("graphics/ships/onslaught.png"), enqueued);
        assertEquals(List.of(hypernova.manifest.Layer.L2), layers);
    }

    @Test
    void duplicateFleetIsSuppressedWithinWindow() {
        List<String> enqueued = new ArrayList<>();
        hypernova.scheduler.PrefetchScheduler sched = new hypernova.scheduler.PrefetchScheduler() {
            @Override
            public void enqueue(Iterable<String> paths, hypernova.manifest.Layer layer) {
                paths.forEach(enqueued::add);
            }

            @Override
            public void tick() {
            }

            @Override
            public hypernova.scheduler.SchedulerStats stats() {
                return new hypernova.scheduler.SchedulerStats(0, 0, 0, 0, 0, 0);
            }

            @Override
            public int backlog() {
                return 0;
            }
        };
        FleetDiscoveryHook hook = new FleetDiscoveryHook(sched, new FleetSpriteResolver(new StubSource()), () -> 1_000L, 300_000L);
        FleetView f = new FleetView("heg", List.of(
                new VariantRef("onslaught", "onslaught_Standard", List.of())));
        hook.onFleetDetected(f);
        hook.onFleetDetected(f);
        assertEquals(List.of("graphics/ships/onslaught.png"), enqueued);
    }
}
