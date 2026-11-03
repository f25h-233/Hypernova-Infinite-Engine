package hypernova;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeWiringTest {
    @Test
    void premainRegistersInsidePropertyGateBeforeScriptsEarlyReturn() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int gate = src.indexOf(
                "if (Boolean.getBoolean(\"hypernova.frameProbe\"))");
        int probe = src.indexOf("new FrameProbeTransformer()");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(gate > 0, "probe must be gated by the system property");
        assertTrue(probe > gate,
                "addTransformer must be inside the property gate");
        assertTrue(probe < scriptsGate,
                "probe must register before the scripts early return");
    }

    @Test
    void transformerTargetsBothDisplayUpdateOverloads() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/FrameProbeTransformer.java"));
        assertTrue(src.contains("org/lwjgl/opengl/Display"),
                "must target Display");
        assertTrue(src.contains("\"()V\"") && src.contains("\"(Z)V\""),
                "must cover both update overloads");
    }
}
