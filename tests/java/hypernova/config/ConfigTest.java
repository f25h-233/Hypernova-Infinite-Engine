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
        assertEquals(3000, c.heartbeatFrames());
    }

    @Test
    void overrides() throws Exception {
        JSONObject o = new JSONObject();
        o.put("enabled", false);
        o.put("eviction", true);
        o.put("frame_budget_micros", 1500);
        o.put("telemetry_buffer_lines", 10);
        o.put("heartbeat_frames", 1);
        HypernovaConfig c = HypernovaConfig.fromJson(o);
        assertFalse(c.enabled());
        assertTrue(c.eviction());
        assertEquals(1500, c.frameBudgetMicros());
        assertEquals(10, c.telemetryBufferLines());
        assertEquals(1, c.heartbeatFrames());
    }

    @Test
    void heartbeatFramesCanBeZeroToDisableHeartbeat() throws Exception {
        JSONObject o = new JSONObject();
        o.put("heartbeat_frames", 0);
        assertEquals(0, HypernovaConfig.fromJson(o).heartbeatFrames());
    }

    @Test
    void legacyVerboseKeyNoLongerAffectsConfig() throws Exception {
        // verbose 在 88a752d 后成为死开关；现已改名为 heartbeat_frames。
        // 旧配置文件里残留 verbose=true 不得再改变任何行为（只是被忽略）。
        JSONObject o = new JSONObject();
        o.put("verbose", true);
        assertEquals(3000, HypernovaConfig.fromJson(o).heartbeatFrames());
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
