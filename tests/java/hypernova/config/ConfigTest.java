package hypernova.config;

import org.json.JSONObject;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConfigTest {
    @Test
    void defaultsWhenEmpty() {
        HypernovaConfig c = HypernovaConfig.fromJson(new JSONObject());
        assertTrue(c.enabled());
        assertFalse(c.eviction());
        assertEquals(2000, c.frameBudgetMicros());
        assertEquals(4096, c.telemetryBufferLines());
        assertFalse(c.verbose());
    }

    @Test
    void overrides() throws Exception {
        JSONObject o = new JSONObject();
        o.put("enabled", false);
        o.put("eviction", true);
        o.put("frame_budget_micros", 1500);
        o.put("telemetry_buffer_lines", 10);
        o.put("verbose", true);
        HypernovaConfig c = HypernovaConfig.fromJson(o);
        assertFalse(c.enabled());
        assertTrue(c.eviction());
        assertEquals(1500, c.frameBudgetMicros());
        assertEquals(10, c.telemetryBufferLines());
        assertTrue(c.verbose());
    }

    @Test
    void versionProbeAcceptsRc8() {
        Capability cap = VersionProbe.probe("Starsector 0.98a-RC8", true);
        assertTrue(cap.gameOk());
        assertTrue(cap.frAvailable());
    }

    @Test
    void versionProbeRejectsOtherVersion() {
        Capability cap = VersionProbe.probe("Starsector 0.97a-RC11", true);
        assertFalse(cap.gameOk());
    }

    @Test
    void versionProbeRejectsNull() {
        Capability cap = VersionProbe.probe(null, false);
        assertFalse(cap.gameOk());
        assertEquals("version string unavailable", cap.reason());
    }

    @Test
    void frMissingIsNotFatal() {
        Capability cap = VersionProbe.probe("Starsector 0.98a-RC8", false);
        assertTrue(cap.gameOk());
        assertFalse(cap.frAvailable());
    }
}
