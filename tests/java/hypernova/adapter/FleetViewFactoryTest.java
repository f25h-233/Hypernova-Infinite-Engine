package hypernova.adapter;

import hypernova.hooks.FleetView;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FleetViewFactoryTest {

    @Test
    void buildsViewFromMembers() {
        FleetViewFactory f = new FleetViewFactory();
        FleetView v = f.build("hegemony", List.of("onslaught_Standard", "wolf_Starting"));
        assertEquals("hegemony", v.name());
        assertEquals(2, v.members().size());
        assertEquals("onslaught_Standard", v.members().get(0).hullVariantId());
    }

    @Test
    void emptyFleetIsEmptyView() {
        FleetViewFactory f = new FleetViewFactory();
        assertTrue(f.build("empty", List.of()).members().isEmpty());
    }

    @Test
    void nullVariantIdIsSkipped() {
        FleetViewFactory f = new FleetViewFactory();
        List<String> ids = new ArrayList<>();
        ids.add("a");
        ids.add(null);
        assertEquals(1, f.build("x", ids).members().size());
    }
}
