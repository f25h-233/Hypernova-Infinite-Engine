package hypernova.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/** Marks FR's three startup phases without touching their logic. */
public final class StartupTimelineTransformer implements ClassFileTransformer {
    public static final String TARGET = "com/genir/renderer/overrides/loading/ResourceLoaderState";
    private static final String HOOK = "hypernova/agent/StartupTimeline";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || !TARGET.equals(className) || redefined != null) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            boolean[] patched = {false};
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
                    String label = labelFor(name, descriptor);
                    if (label == null) return mv;
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitLdcInsn(label + ".start");
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "mark",
                                    "(Ljava/lang/String;)V", false);
                        }

                        @Override
                        public void visitInsn(int opcode) {
                            if (opcode == Opcodes.RETURN) {
                                super.visitLdcInsn(label + ".end");
                                super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "mark",
                                        "(Ljava/lang/String;)V", false);
                            }
                            super.visitInsn(opcode);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            return patched[0] ? writer.toByteArray() : null;
        } catch (Throwable t) {
            AgentLog.fail("startup timeline transform failed; phase marks disabled", t);
            return null;
        }
    }

    private static String labelFor(String name, String descriptor) {
        if ("initFileLoaders".equals(name) && "()V".equals(descriptor)) return "initFileLoaders";
        if ("initSpecStore".equals(name) && "(Ljava/util/Map;)V".equals(descriptor)) return "initSpecStore";
        if ("initMods".equals(name) && "()V".equals(descriptor)) return "initMods";
        return null;
    }
}
