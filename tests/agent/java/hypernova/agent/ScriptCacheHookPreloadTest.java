package hypernova.agent;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Task 3: preload 真实填充 FR bytecodeCache,find 命中/未命中走真实计数。
 *
 * <p>controller 裁决 P2:fixture 必须先经 {@link ScriptCacheTransformer} 转换,再用
 * define 辅助 loader 定义出转换后的类;直接 new 原始 fixture 的话它的 findClass
 * 里没有 onFindClass 调用,hits() 恒为 0。测试因此不能把 loader 变量声明为
 * MultiThreadedJaninoClassLoader 类型(被转换的类与被测试类路径上的原始 fixture
 * 是两个不同的 Class),改用反射调用 bytecodeCache()/find(String)。
 */
class ScriptCacheHookPreloadTest {
    @TempDir Path tmp;

    @BeforeEach
    void clean() {
        // 其他测试类共用这些静态计数器;保证本类每个用例都从干净状态开始。
        ScriptCacheHook.resetForTest();
    }

    @AfterEach
    void reset() {
        ScriptCacheHook.resetForTest();
    }

    @Test
    void preloadPopulatesBytecodeCacheAndFindClassHits() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src"));
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path saves = tmp.resolve("saves");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);

        String key = ScriptCacheKey.compute(ctx).id();
        Map<String, byte[]> entries = Map.of("hypernova.cache.Generated", generatedClass());
        new CacheStore(ctx.cacheRoot(), 2, 1L << 30).save(key, entries);

        Object loader = transformedLoader();
        ScriptCacheHook.preload(loader, ctx);

        assertTrue(bytecodeCache(loader).containsKey("hypernova.cache.Generated"));
        Class<?> clazz = find(loader, "hypernova.cache.Generated");
        assertEquals("hypernova.cache.Generated", clazz.getName());
        assertEquals(1, ScriptCacheHook.hits());
        assertEquals(0, ScriptCacheHook.misses());
    }

    @Test
    void coldPreloadCountsMissingAsMiss() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Files.createDirectories(mods);
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        Path saves = tmp.resolve("saves2");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);

        Object loader = transformedLoader();
        ScriptCacheHook.preload(loader, ctx);
        assertTrue(bytecodeCache(loader).isEmpty());
        assertThrows(ClassNotFoundException.class, () -> find(loader, "missing.Class"));
        assertEquals(1, ScriptCacheHook.misses());
        assertEquals(0, ScriptCacheHook.hits());
    }

    /**
     * P2 装配:fixture 原始字节 -> transformer 转换 -> define 辅助 loader 定义 -> 实例化。
     * 这样实例的 findClass 里才有 ScriptCacheHook.onFindClass 调用。
     */
    private static Object transformedLoader() throws Exception {
        ClassLoader parent = ScriptCacheHookPreloadTest.class.getClassLoader();
        byte[] original = readFixtureBytes();
        byte[] transformed = new ScriptCacheTransformer().transform(
                parent, ScriptCacheTransformer.TARGET, null, null, original);
        assertNotNull(transformed, "transformer must produce bytes for the FR loader fixture");
        Class<?> cls = new ByteArrayDefiner(parent)
                .define(ScriptCacheTransformer.TARGET.replace('/', '.'), transformed);
        Constructor<?> ctor = cls.getConstructor(ClassLoader.class);
        return ctor.newInstance(parent);
    }

    private static byte[] readFixtureBytes() throws Exception {
        String resource = "/" + ScriptCacheTransformer.TARGET + ".class";
        try (InputStream in = ScriptCacheHookPreloadTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "fixture class not on test classpath: " + resource);
            return in.readAllBytes();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, byte[]> bytecodeCache(Object loader) throws Exception {
        Method m = loader.getClass().getMethod("bytecodeCache");
        return (Map<String, byte[]>) m.invoke(loader);
    }

    private static Class<?> find(Object loader, String name) throws Exception {
        Method m = loader.getClass().getMethod("find", String.class);
        try {
            return (Class<?>) m.invoke(loader, name);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception ex) throw ex;
            if (cause instanceof Error err) throw err;
            throw e;
        }
    }

    private static byte[] generatedClass() {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "hypernova/cache/Generated", null,
                "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "<init>", "()V", null, null);
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(1, 1);
        mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    /** 与 ScriptCacheTransformerTest.ByteArrayClassLoader 同一模式。 */
    private static final class ByteArrayDefiner extends ClassLoader {
        ByteArrayDefiner(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }
}
