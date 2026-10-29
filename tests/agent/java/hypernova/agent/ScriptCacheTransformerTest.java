package hypernova.agent;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;

import static org.junit.jupiter.api.Assertions.*;

class ScriptCacheTransformerTest {

    @BeforeEach
    void reset() {
        ScriptCacheHook.resetForTest();
    }

    @Test
    void injectsPreloadIntoConstructorAndCountsFindClass() throws Exception {
        byte[] original = readClassBytes();
        byte[] transformed = new ScriptCacheTransformer().transform(
                getClass().getClassLoader(), ScriptCacheTransformer.TARGET, null, null, original);
        assertNotNull(transformed, "transformer must return bytes for the target class");
        assertTrue(new String(transformed, java.nio.charset.StandardCharsets.ISO_8859_1)
                .contains("hypernova/agent/ScriptCacheHook"), "injected hook reference missing");

        ByteArrayClassLoader loader = new ByteArrayClassLoader(getClass().getClassLoader());
        Class<?> cls = loader.define(ScriptCacheTransformer.TARGET.replace('/', '.'),
                transformed);

        long beforePreload = ScriptCacheHook.preloadCalls();
        Object instance = cls.getConstructor(ClassLoader.class).newInstance(getClass().getClassLoader());
        assertEquals(beforePreload + 1, ScriptCacheHook.preloadCalls(),
                "constructor must call ScriptCacheHook.preload(this) exactly once");

        long beforeFind = ScriptCacheHook.findCalls();
        var findClass = cls.getDeclaredMethod("findClass", String.class);
        findClass.setAccessible(true);
        assertThrows(InvocationTargetException.class,
                () -> findClass.invoke(instance, "does.not.Exist"));
        assertEquals(beforeFind + 1, ScriptCacheHook.findCalls(),
                "findClass entry must call ScriptCacheHook.onFindClass");
        assertEquals(1, ScriptCacheHook.misses());
    }

    private static byte[] readClassBytes() throws Exception {
        String resource = "/" + ScriptCacheTransformer.TARGET + ".class";
        try (InputStream in = ScriptCacheTransformerTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "fixture class not on test classpath: " + resource);
            return in.readAllBytes();
        }
    }

    static final class ByteArrayClassLoader extends ClassLoader {
        ByteArrayClassLoader(ClassLoader parent) { super(parent); }
        Class<?> define(String name, byte[] bytes) { return defineClass(name, bytes, 0, bytes.length); }
    }
}
