package hypernova;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeWiringTest {
    @Test
    void premainRegistersProbeBeforeScriptsEarlyReturn() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int probe = src.indexOf("new FrameProbeTransformer()");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(probe > 0, "must register FrameProbeTransformer");
        assertTrue(probe < scriptsGate,
                "probe must register before the scripts early return");
        assertTrue(src.contains("Boolean.getBoolean(\"hypernova.frameProbe\")"),
                "probe must be opt-in by system property");
    }
}
