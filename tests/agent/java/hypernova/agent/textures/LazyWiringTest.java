package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Pure-logic seam for the fail-open wiring gate: every hook must be armed and
 * the proxy must really override bind/id before the module is allowed to skip.
 */
class LazyWiringTest {
    private static final String OBJ = "hypernova/agent/textures/WiringObject";
    private static final String PROXY = "hypernova/agent/textures/WiringProxy";
    private static final String PLAIN = "hypernova/agent/textures/WiringPlain";
    private static final String NO_METHODS = "hypernova/agent/textures/WiringNoMethods";
    private static final String NO_METHODS_PROXY = "hypernova/agent/textures/WiringNoMethodsProxy";

    private static final Class<?> OBJECT = define(OBJ, "java/lang/Object", true);
    private static final Class<?> PROXY_TYPE = define(PROXY, OBJ, true);
    private static final Class<?> PLAIN_TYPE = define(PLAIN, OBJ, false);
    private static final Class<?> NO_METHODS_TYPE = define(NO_METHODS, "java/lang/Object", false);
    private static final Class<?> NO_METHODS_PROXY_TYPE = define(NO_METHODS_PROXY, NO_METHODS, true);

    @Test
    void requiresEveryHookArmed() throws Exception {
        Method register = String.class.getMethod("length");
        assertTrue(LazyTextures.wiringOk(true, true, true, true, register, OBJECT, PROXY_TYPE));
        assertFalse(LazyTextures.wiringOk(false, true, true, true, register, OBJECT, PROXY_TYPE));
        assertFalse(LazyTextures.wiringOk(true, false, true, true, register, OBJECT, PROXY_TYPE));
        assertFalse(LazyTextures.wiringOk(true, true, false, true, register, OBJECT, PROXY_TYPE));
        assertFalse(LazyTextures.wiringOk(true, true, true, false, register, OBJECT, PROXY_TYPE));
        assertFalse(LazyTextures.wiringOk(true, true, true, true, null, OBJECT, PROXY_TYPE));
    }

    @Test
    void requiresProxyOverrides() throws Exception {
        Method register = String.class.getMethod("length");
        assertFalse(LazyTextures.wiringOk(true, true, true, true, register, OBJECT, PLAIN_TYPE));
    }

    @Test
    void requiresObjectMethods() throws Exception {
        Method register = String.class.getMethod("length");
        assertFalse(LazyTextures.wiringOk(true, true, true, true, register,
                NO_METHODS_TYPE, NO_METHODS_PROXY_TYPE));
    }

    @Test
    void transformersArmTheirHooks() {
        LazyTextures.resetWiringForTest();
        assertFalse(LazyTextures.wiringArmed());

        byte[] loader = classBytes("com/fs/graphics/TextureLoader", cv ->
                method(cv, "loadTextureAsync", "(Ljava/lang/String;Ljava/lang/String;)V"));
        assertNotNull(new LazyTextureTransformer().transform(
                null, "com/fs/graphics/TextureLoader", null, null, loader));
        assertTrue(LazyTextures.queueArmed());

        byte[] repo = classBytes("com/fs/graphics/oOoO", cv -> {
            method(cv, Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "lookup", "(Ljava/lang/String;)Lcom/fs/graphics/Object;");
            method(cv, Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "super", "(Ljava/lang/String;Lcom/fs/graphics/Object;)V");
        });
        assertNotNull(new LazyTextureTransformer().transform(
                null, "com/fs/graphics/oOoO", null, null, repo));
        assertTrue(LazyTextures.registerArmed());

        byte[] markov = classBytes("com/fs/starfarer/api/impl/campaign/procgen/MarkovNames", cv ->
                method(cv, "loadIfNeeded", "()V"));
        assertNotNull(new LazyDrainTransformer().transform(
                null, "com/fs/starfarer/api/impl/campaign/procgen/MarkovNames", null, null, markov));
        assertTrue(LazyTextures.drainArmed());

        byte[] base = classBytes("com/fs/starfarer/BaseGameState", cv ->
                method(cv, "traverse", "()Ljava/lang/String;"));
        assertNotNull(new LazyGameThreadTransformer().transform(
                null, "com/fs/starfarer/BaseGameState", null, null, base));
        assertTrue(LazyTextures.threadArmed());
        assertTrue(LazyTextures.wiringArmed());
    }

    private static Class<?> define(String name, String superName, boolean methods) {
        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER, name, null, superName, null);
        MethodVisitor init = cw.visitMethod(Opcodes.ACC_PUBLIC, "<init>", "()V", null, null);
        init.visitCode();
        init.visitVarInsn(Opcodes.ALOAD, 0);
        init.visitMethodInsn(Opcodes.INVOKESPECIAL, superName, "<init>", "()V", false);
        init.visitInsn(Opcodes.RETURN);
        init.visitMaxs(0, 0);
        init.visitEnd();
        if (methods) {
            MethodVisitor bind = cw.visitMethod(Opcodes.ACC_PUBLIC, "Ø00000", "()V", null, null);
            bind.visitCode();
            bind.visitInsn(Opcodes.RETURN);
            bind.visitMaxs(0, 0);
            bind.visitEnd();
            MethodVisitor id = cw.visitMethod(Opcodes.ACC_PUBLIC, "ö00000", "()I", null, null);
            id.visitCode();
            id.visitInsn(Opcodes.ICONST_0);
            id.visitInsn(Opcodes.IRETURN);
            id.visitMaxs(0, 0);
            id.visitEnd();
        }
        cw.visitEnd();
        try {
            return MethodHandles.lookup().defineClass(cw.toByteArray());
        } catch (IllegalAccessException e) {
            throw new AssertionError(e);
        }
    }

    private static byte[] classBytes(String name, java.util.function.Consumer<org.objectweb.asm.ClassVisitor> body) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        body.accept(cw);
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static void method(org.objectweb.asm.ClassVisitor cv, String name, String desc) {
        method(cv, Opcodes.ACC_PUBLIC, name, desc);
    }

    private static void method(org.objectweb.asm.ClassVisitor cv, int access, String name, String desc) {
        MethodVisitor mv = cv.visitMethod(access, name, desc, null, null);
        mv.visitCode();
        if (desc.endsWith(")V")) {
            mv.visitInsn(Opcodes.RETURN);
        } else if (desc.endsWith(")I")) {
            mv.visitInsn(Opcodes.ICONST_0);
            mv.visitInsn(Opcodes.IRETURN);
        } else {
            mv.visitInsn(Opcodes.ACONST_NULL);
            mv.visitInsn(Opcodes.ARETURN);
        }
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }
}
