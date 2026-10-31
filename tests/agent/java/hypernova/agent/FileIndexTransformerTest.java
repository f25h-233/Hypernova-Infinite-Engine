package hypernova.agent;

import com.fs.util.FileLoader;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FileIndexTransformerTest {

    @TempDir
    Path tmp;

    @BeforeEach
    void reset() {
        FileIndexHook.resetForTest();
    }

    @Test
    void injectsTryLoadAndSave() throws Exception {
        byte[] original = readClassBytes();
        byte[] transformed = new FileIndexTransformer().transform(
                getClass().getClassLoader(), FileIndexTransformer.TARGET,
                null, null, original);
        assertNotNull(transformed, "transformer must patch DirectoryCrawler");
        String text = new String(transformed, java.nio.charset.StandardCharsets.ISO_8859_1);
        assertTrue(text.contains("hypernova/agent/FileIndexHook"), "hook reference missing");
        assertTrue(text.contains("tryLoad"), "tryLoad call missing");
        assertTrue(text.contains("save"), "save call missing");

        // The transformed class must verify and load.
        ByteArrayClassLoader loader = new ByteArrayClassLoader(getClass().getClassLoader());
        assertNotNull(loader.define(
                FileIndexTransformer.TARGET.replace('/', '.'), transformed));
    }

    @Test
    void ignoresNonTargetClass() {
        byte[] transformed = new FileIndexTransformer().transform(
                getClass().getClassLoader(), "java/lang/String", null, null, new byte[]{0});
        assertNull(transformed);
    }

    @Test
    void transformedCacheLocationsRunsWhenHookFailsOpen() throws Exception {
        Path mod = tmp.resolve("mods/mod1");
        Files.createDirectories(mod);
        Files.writeString(mod.resolve("a.txt"), "a");
        FileLoader.ResourceLocation loc = new FileLoader.ResourceLocation(
                FileLoader.Type.DIRECTORY, mod.toString(), true);

        byte[] transformed = new FileIndexTransformer().transform(
                getClass().getClassLoader(), FileIndexTransformer.TARGET,
                null, null, readClassBytes());
        assertNotNull(transformed);

        // The inner class must share a loader (nest) with its outer class, otherwise
        // private/nest access to FileLoaderFast fails with IllegalAccessError.
        FixtureClassLoader loader = new FixtureClassLoader(getClass().getClassLoader());
        loader.put("com.genir.renderer.overrides.loading.FileLoaderFast",
                readFixtureBytes("com/genir/renderer/overrides/loading/FileLoaderFast"));
        loader.put(FileIndexTransformer.TARGET.replace('/', '.'), transformed);

        Class<?> outerClass = loader.loadClass(
                "com.genir.renderer.overrides.loading.FileLoaderFast");
        Object outer = outerClass.getConstructor(List.class).newInstance(List.of(loc));
        Class<?> inner = loader.loadClass(FileIndexTransformer.TARGET.replace('/', '.'));
        Constructor<?> ctor = inner.getDeclaredConstructor(outerClass);
        ctor.setAccessible(true);
        Object crawler = ctor.newInstance(outer);
        Method m = inner.getDeclaredMethod("cacheLocations");
        m.setAccessible(true);
        int count = (Integer) m.invoke(crawler);
        assertTrue(count > 0, "original crawl must run when the hook fails open");
    }

    private static byte[] readClassBytes() throws Exception {
        return readFixtureBytes(FileIndexTransformer.TARGET);
    }

    private static byte[] readFixtureBytes(String internalName) throws Exception {
        String resource = "/" + internalName + ".class";
        try (InputStream in = FileIndexTransformerTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "fixture class not on test classpath: " + resource);
            return in.readAllBytes();
        }
    }

    static final class ByteArrayClassLoader extends ClassLoader {
        ByteArrayClassLoader(ClassLoader parent) { super(parent); }
        Class<?> define(String name, byte[] bytes) { return defineClass(name, bytes, 0, bytes.length); }
    }

    static final class FixtureClassLoader extends ClassLoader {
        private final java.util.Map<String, byte[]> classes = new java.util.HashMap<>();

        FixtureClassLoader(ClassLoader parent) { super(parent); }

        void put(String name, byte[] bytes) { classes.put(name, bytes); }

        @Override
        protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
            Class<?> loaded = findLoadedClass(name);
            if (loaded == null) {
                byte[] bytes = classes.get(name);
                if (bytes != null) loaded = defineClass(name, bytes, 0, bytes.length);
            }
            if (loaded == null) return super.loadClass(name, resolve);
            if (resolve) resolveClass(loaded);
            return loaded;
        }
    }
}
