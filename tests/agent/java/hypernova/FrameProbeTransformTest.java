package hypernova;

import hypernova.agent.FrameProbeTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeTransformTest {
    private static final String BASE = "com/fs/starfarer/BaseGameState";
    private static final String COMBAT = "com/fs/starfarer/combat/CombatState";

    @Test
    void injectsIntoBaseAndCombatTraverse() {
        for (String target : new String[]{BASE, COMBAT}) {
            byte[] in = classBytes(target);
            byte[] out = new FrameProbeTransformer().transform(null, target, null, null, in);
            assertNotNull(out, target);
            assertTrue(calls(out, "hypernova/agent/FrameProbe", "frame"), target);
        }
    }

    @Test
    void missingTraverseIsUntouched() {
        byte[] in = classBytesWithoutTraverse(COMBAT);
        assertNull(new FrameProbeTransformer().transform(null, COMBAT, null, null, in));
    }

    @Test
    void otherClassAndMalformedBytesAreIgnored() {
        assertNull(new FrameProbeTransformer().transform(
                null, "com/fs/starfarer/Other", null, null, classBytes(BASE)));
        assertNull(new FrameProbeTransformer().transform(
                null, BASE, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] classBytes(String name) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "traverse",
                "()Ljava/lang/String;", null, null);
        mv.visitCode();
        mv.visitInsn(Opcodes.ACONST_NULL);
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static byte[] classBytesWithoutTraverse(String name) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "other", "()V", null, null);
        mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static boolean calls(byte[] bytes, String owner, String name) {
        List<String> hits = new ArrayList<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitMethodInsn(int op, String o, String mn, String dd, boolean itf) {
                        if (owner.equals(o) && name.equals(mn)) hits.add(mn);
                    }
                };
            }
        }, 0);
        return !hits.isEmpty();
    }
}
