package hypernova;

import hypernova.agent.textures.LazyDrainTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class LazyDrainTransformTest {
    private static final String TARGET = "com/fs/starfarer/api/impl/campaign/procgen/MarkovNames";

    @Test
    void injectsDrainIntoLoadIfNeeded() {
        byte[] in = classBytes(TARGET, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "loadIfNeeded", "()V", null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.RETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyDrainTransformer().transform(null, TARGET, null, null, in);
        assertNotNull(out);
        assertTrue(calls(out, "loadIfNeeded", "hypernova/agent/textures/LazyTextures", "drainPending"));
    }

    @Test
    void missingMethodIsUntouched() {
        byte[] in = classBytes(TARGET, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "load", "(Ljava/lang/String;)V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        });
        assertNull(new LazyDrainTransformer().transform(null, TARGET, null, null, in));
    }

    @Test
    void malformedBytesReturnNull() {
        assertNull(new LazyDrainTransformer().transform(null, TARGET, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] classBytes(String name, java.util.function.Consumer<ClassVisitor> body) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        body.accept(cw);
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static boolean calls(byte[] bytes, String method, String owner, String name) {
        List<String> hits = new ArrayList<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitMethodInsn(int op, String o, String mn, String d, boolean itf) {
                        if (method.equals(n) && owner.equals(o) && name.equals(mn)) hits.add(mn);
                    }
                };
            }
        }, 0);
        return !hits.isEmpty();
    }
}
