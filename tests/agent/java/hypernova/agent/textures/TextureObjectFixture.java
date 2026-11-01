package hypernova.agent.textures;

import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.awt.Color;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

/**
 * Test fixtures for {@code com.fs.graphics.Object} (0.98a-RC8) and its proxy
 * subclass.
 *
 * <p>The real class declares three fields whose names are Java keywords
 * ({@code for}, {@code int}, {@code public}), so the fixtures cannot be written
 * as Java source. They are generated with ASM and defined in this package:
 * a super class with the same 14 field names/types plus the 3-arg constructor,
 * and a sub class that only adds a matching constructor (mirroring
 * LazyProxyObject). This wrapper supplies the brief's getters/setters.
 */
final class TextureObjectFixture {
    private static final String SUPER_NAME = "hypernova/agent/textures/TextureObjectFixtureSuper";
    private static final String SUB_NAME = "hypernova/agent/textures/TextureObjectFixtureSub";
    private static final Class<?> SUPER = define(superBytes());
    private static final Class<?> SUB = define(subBytes());

    private final Object raw;

    TextureObjectFixture(Object raw) {
        this.raw = raw;
    }

    TextureObjectFixture(int target, int id, String path) {
        this(create(target, id, path));
    }

    /** Field carrier type: stands in for com.fs.graphics.Object. */
    static Class<?> type() {
        return SUPER;
    }

    /** Constructor carrier type: stands in for LazyProxyObject. */
    static Class<?> proxyType() {
        return SUB;
    }

    Object raw() {
        return raw;
    }

    private static Object create(int target, int id, String path) {
        try {
            var ctor = SUB.getDeclaredConstructor(int.class, int.class, String.class);
            ctor.setAccessible(true);
            return ctor.newInstance(target, id, path);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError(e);
        }
    }

    int target() {
        return (Integer) get("ö00000");
    }

    int id() {
        return (Integer) get("ô00000");
    }

    int width() {
        return (Integer) get("oO0000");
    }

    int height() {
        return (Integer) get("Object");
    }

    int imageWidth() {
        return (Integer) get("Ô00000");
    }

    int imageHeight() {
        return (Integer) get("ÒO0000");
    }

    float texWidth() {
        return (Float) get("for");
    }

    float texHeight() {
        return (Float) get("ø00000");
    }

    String path() {
        return (String) get("int");
    }

    String stringId() {
        return (String) get("Ò00000");
    }

    Color color0() {
        return (Color) get("Õ00000");
    }

    Color color1() {
        return (Color) get("o00000");
    }

    Color color2() {
        return (Color) get("public");
    }

    void setWidth(int v) {
        set("oO0000", v);
    }

    void setHeight(int v) {
        set("Object", v);
    }

    void setImageWidth(int v) {
        set("Ô00000", v);
    }

    void setImageHeight(int v) {
        set("ÒO0000", v);
    }

    void setColors(Color a, Color b, Color c) {
        set("Õ00000", a);
        set("o00000", b);
        set("public", c);
    }

    private Object get(String name) {
        try {
            Field f = SUPER.getDeclaredField(name);
            f.setAccessible(true);
            return f.get(raw);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError(e);
        }
    }

    private void set(String name, Object value) {
        try {
            Field f = SUPER.getDeclaredField(name);
            f.setAccessible(true);
            f.set(raw, value);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError(e);
        }
    }

    private static Class<?> define(byte[] bytes) {
        try {
            return MethodHandles.lookup().defineClass(bytes);
        } catch (IllegalAccessException e) {
            throw new AssertionError(e);
        }
    }

    private static byte[] superBytes() {
        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER,
                SUPER_NAME, null, "java/lang/Object", null);
        field(cw, "ö00000", "I");
        field(cw, "ô00000", "I");
        field(cw, "ÒO0000", "I");
        field(cw, "Ô00000", "I");
        field(cw, "oO0000", "I");
        field(cw, "Object", "I");
        field(cw, "for", "F");
        field(cw, "ø00000", "F");
        field(cw, "int", "Ljava/lang/String;");
        field(cw, "Ò00000", "Ljava/lang/String;");
        field(cw, "Ø00000", "Z");
        field(cw, "Õ00000", "Ljava/awt/Color;");
        field(cw, "o00000", "Ljava/awt/Color;");
        field(cw, "public", "Ljava/awt/Color;");

        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "<init>",
                "(IILjava/lang/String;)V", null, null);
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        put(mv, "ö00000", "I", Opcodes.ILOAD, 1);
        put(mv, "ô00000", "I", Opcodes.ILOAD, 2);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitFieldInsn(Opcodes.PUTFIELD, SUPER_NAME, "int", "Ljava/lang/String;");
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitInsn(Opcodes.ICONST_0);
        mv.visitFieldInsn(Opcodes.PUTFIELD, SUPER_NAME, "Ø00000", "Z");
        for (String color : new String[]{"Õ00000", "o00000", "public"}) {
            mv.visitVarInsn(Opcodes.ALOAD, 0);
            mv.visitFieldInsn(Opcodes.GETSTATIC, "java/awt/Color", "white",
                    "Ljava/awt/Color;");
            mv.visitFieldInsn(Opcodes.PUTFIELD, SUPER_NAME, color, "Ljava/awt/Color;");
        }
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static byte[] subBytes() {
        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER,
                SUB_NAME, null, SUPER_NAME, null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "<init>",
                "(IILjava/lang/String;)V", null, null);
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ILOAD, 1);
        mv.visitVarInsn(Opcodes.ILOAD, 2);
        mv.visitVarInsn(Opcodes.ALOAD, 3);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, SUPER_NAME, "<init>",
                "(IILjava/lang/String;)V", false);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static void put(MethodVisitor mv, String field, String desc, int loadOp, int slot) {
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(loadOp, slot);
        mv.visitFieldInsn(Opcodes.PUTFIELD, SUPER_NAME, field, desc);
    }

    private static void field(ClassWriter cw, String name, String desc) {
        cw.visitField(Opcodes.ACC_PRIVATE, name, desc, null, null).visitEnd();
    }
}
