package hypernova.agent;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * The transformer must patch classes that are actually loaded and executed under
 * their own names. The old donor-class fixture was a false green: FR merges those
 * donor bytes into game classes, so the donor class itself never ran.
 */
class StartupTimelineTransformerTest {

    @BeforeEach
    void reset() {
        StartupTimeline.resetForTest();
        // mark() is a no-op until start() arms the baseline (premain calls it in
        // production); resetForTest() clears it, so re-arm here.
        StartupTimeline.start();
    }

    @Test
    void injectsLoaderStartAndEndIntoFileLoaderFastConstructor() throws Exception {
        Class<?> cls = defineTransformed(
                StartupTimelineTransformer.LOADER_TARGET, "<init>", "(Ljava/util/List;)V");
        assertNotNull(cls, "FileLoaderFast constructor must be patched");

        Constructor<?> ctor = cls.getConstructor(List.class);
        ctor.newInstance(List.of());

        List<String> marks = StartupTimeline.marksForTest();
        assertTrue(marks.contains("loader.start"), marks.toString());
        assertTrue(marks.contains("loader.end"), marks.toString());
    }

    @Test
    void injectsDdsStartAndEndIntoInitialize() throws Exception {
        Class<?> cls = defineTransformed(
                StartupTimelineTransformer.DDS_TARGET, "initialize", "()V");
        assertNotNull(cls, "DDSIntegration.initialize must be patched");

        cls.getMethod("initialize").invoke(null);

        List<String> marks = StartupTimeline.marksForTest();
        assertTrue(marks.contains("dds.start"), marks.toString());
        assertTrue(marks.contains("dds.end"), marks.toString());
    }

    @Test
    void injectsModsStartIntoExecutedMarkovNamesAnchor() throws Exception {
        Class<?> cls = defineTransformed(
                StartupTimelineTransformer.MODS_TARGET, "loadIfNeeded", "()V");
        assertNotNull(cls, "MarkovNames.loadIfNeeded must be patched");

        Method load = cls.getMethod("loadIfNeeded");
        load.invoke(null);

        List<String> marks = StartupTimeline.marksForTest();
        assertTrue(marks.contains("mods.start"), marks.toString());
        assertFalse(marks.contains("mods.end"), "mods phase ends at the menu, not in this method");
    }

    @Test
    void ignoresNonTargetClass() {
        byte[] transformed = new StartupTimelineTransformer().transform(
                getClass().getClassLoader(), "java/lang/String", null, null, new byte[]{0});
        assertNull(transformed);
    }

    private Class<?> defineTransformed(String target, String method, String descriptor) throws Exception {
        byte[] original = readClassBytes(target);
        byte[] transformed = new StartupTimelineTransformer().transform(
                getClass().getClassLoader(), target, null, null, original);
        if (transformed == null) return null;
        assertTrue(new String(transformed, StandardCharsets.ISO_8859_1)
                .contains("hypernova/agent/StartupTimeline"), "mark hook reference missing");
        ByteArrayClassLoader loader = new ByteArrayClassLoader(getClass().getClassLoader());
        return loader.define(target.replace('/', '.'), transformed);
    }

    private static byte[] readClassBytes(String target) throws Exception {
        String resource = "/" + target + ".class";
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
