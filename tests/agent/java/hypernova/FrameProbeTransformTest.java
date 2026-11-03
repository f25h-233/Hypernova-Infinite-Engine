package hypernova;

import hypernova.agent.FrameProbeTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeTransformTest {
    private static final String DISPLAY = "org/lwjgl/opengl/Display";

    @Test
    void injectsOnceWhenBothOverloadsExist() {
        byte[] in = displayClass(true, true);
        byte[] out = new FrameProbeTransformer().transform(null, DISPLAY, null, null, in);
        assertNotNull(out);
        assertEquals(1, calls(out, "hypernova/agent/FrameProbe", "frame"));
    }

    @Test
    void delegatesOnlyClassIsUntouched() {
        assertNull(new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, displayClass(true, false)));
    }

    @Test
    void injectsIntoUpdateZOnlyClass() {
        byte[] out = new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, displayClass(false, true));
        assertNotNull(out);
        assertEquals(1, calls(out, "hypernova/agent/FrameProbe", "frame"));
    }

    @Test
    void missingUpdateIsUntouched() {
        assertNull(new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, classBytesWithoutUpdate()));
    }

    @Test
    void otherClassAndMalformedBytesAreIgnored() {
        assertNull(new FrameProbeTransformer().transform(
                null, "org/lwjgl/opengl/Other", null, null, displayClass(true, true)));
        assertNull(new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, new byte[]{1, 2, 3}));
    }

    @Test
    void injectedCallIsTheFirstInstructionOfUpdateZ() {
        byte[] out = new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, displayClass(true, true));
        assertNotNull(out);
        boolean[] found = {false};
        new ClassReader(out).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                if (!"update".equals(n) || !"(Z)V".equals(d)) return null;
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitMethodInsn(int op, String o, String mn,
                                                          String dd, boolean itf) {
                        if (!found[0]) {
                            found[0] = true;
                            assertEquals("hypernova/agent/FrameProbe", o);
                            assertEquals("frame", mn);
                        }
                    }
                };
            }
        }, 0);
        assertTrue(found[0], "update(Z)V must contain the probe call");
    }

    private static byte[] displayClass(boolean noArg, boolean boolArg) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC | Opcodes.ACC_FINAL,
                DISPLAY, null, "java/lang/Object", null);
        if (noArg) {
            MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "update", "()V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        }
        if (boolArg) {
            MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "update", "(Z)V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        }
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static byte[] classBytesWithoutUpdate() {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, DISPLAY, null, "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                "sync", "(I)V", null, null);
        mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static int calls(byte[] bytes, String owner, String name) {
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
        return hits.size();
    }
}
