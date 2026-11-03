package hypernova;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeWiringTest {
    private static final String GATE =
            "if (Boolean.getBoolean(\"hypernova.frameProbe\")) {";

    @Test
    void premainRegistersInsidePropertyGateBeforeScriptsEarlyReturn() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int gate = src.indexOf(GATE);
        int add = src.indexOf(
                "instrumentation.addTransformer(new FrameProbeTransformer(), false);", gate);
        int probe = src.indexOf("new FrameProbeTransformer()");
        int lazy = src.indexOf("LazyTextureConfig lazy");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(gate > 0, "probe must be gated by the system property");
        assertTrue(add > gate && probe > gate,
                "addTransformer must be inside the property gate");
        String between = src.substring(gate + GATE.length(), add);
        assertTrue(between.trim().isEmpty(),
                "addTransformer must directly follow the property gate: <" + between + ">");
        assertTrue(probe < lazy,
                "probe must register before the lazy block");
        assertTrue(probe < scriptsGate,
                "probe must register before the scripts early return");
    }

    @Test
    void transformerTargetsUpdateZOnly() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/FrameProbeTransformer.java"));
        assertTrue(src.contains("org/lwjgl/opengl/Display"),
                "must target Display");
        assertTrue(src.contains("\"(Z)V\""),
                "must patch update(Z)V");
        assertFalse(src.contains("\"()V\""),
                "must not patch update()V directly (it delegates to update(Z)V)");
    }
}
