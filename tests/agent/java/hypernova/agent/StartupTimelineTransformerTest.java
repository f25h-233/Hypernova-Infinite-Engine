package hypernova.agent;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class StartupTimelineTransformerTest {

    @BeforeEach
    void reset() {
        StartupTimeline.resetForTest();
        // mark() is a no-op until start() arms the baseline (premain calls it in
        // production); resetForTest() clears it, so re-arm here.
        StartupTimeline.start();
    }

    @Test
    void injectsStartAndEndMarksIntoAllThreeMethods() throws Exception {
        byte[] original = readClassBytes();
        byte[] transformed = new StartupTimelineTransformer().transform(
                getClass().getClassLoader(), StartupTimelineTransformer.TARGET,
                null, null, original);
        assertNotNull(transformed, "transformer must patch ResourceLoaderState");
        assertTrue(new String(transformed, java.nio.charset.StandardCharsets.ISO_8859_1)
                .contains("hypernova/agent/StartupTimeline"), "mark hook reference missing");

        ByteArrayClassLoader loader = new ByteArrayClassLoader(getClass().getClassLoader());
        Class<?> cls = loader.define(StartupTimelineTransformer.TARGET.replace('/', '.'), transformed);
        Object state = cls.getDeclaredConstructor().newInstance();
        cls.getMethod("run").invoke(state);

        List<String> marks = StartupTimeline.marksForTest();
        assertTrue(marks.contains("initFileLoaders.start"), marks.toString());
        assertTrue(marks.contains("initFileLoaders.end"), marks.toString());
        assertTrue(marks.contains("initSpecStore.start"), marks.toString());
        assertTrue(marks.contains("initSpecStore.end"), marks.toString());
        assertTrue(marks.contains("initMods.start"), marks.toString());
        assertTrue(marks.contains("initMods.end"), marks.toString());
    }

    @Test
    void ignoresNonTargetClass() {
        byte[] transformed = new StartupTimelineTransformer().transform(
                getClass().getClassLoader(), "java/lang/String", null, null, new byte[]{0});
        assertNull(transformed);
    }

    private static byte[] readClassBytes() throws Exception {
        String resource = "/" + StartupTimelineTransformer.TARGET + ".class";
        try (InputStream in = StartupTimelineTransformerTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "fixture class not on test classpath: " + resource);
            return in.readAllBytes();
        }
    }

    static final class ByteArrayClassLoader extends ClassLoader {
        ByteArrayClassLoader(ClassLoader parent) { super(parent); }
        Class<?> define(String name, byte[] bytes) { return defineClass(name, bytes, 0, bytes.length); }
    }
}
