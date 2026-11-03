package hypernova.agent;

import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Injects {@link FrameProbe#frame(String)} at the start of
 * {@code BaseGameState.traverse} (title/campaign) and
 * {@code CombatState.traverse} (combat).
 *
 * <p>BaseGameState is not an FR merge target. CombatState is merged, but the
 * FR donor has no traverse method, so the target's traverse (with this call)
 * is preserved by mergeClass. A missing method is logged and left untouched.
 */
public final class FrameProbeTransformer implements ClassFileTransformer {
    static final String BASE = "com/fs/starfarer/BaseGameState";
    static final String COMBAT = "com/fs/starfarer/combat/CombatState";
    private static final String METHOD = "traverse";
    private static final String DESC = "()Ljava/lang/String;";
    private static final String HOOK = "hypernova/agent/FrameProbe";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null || bytes == null) {
            return null;
        }
        if (!BASE.equals(className) && !COMBAT.equals(className)) {
            return null;
        }
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            boolean[] patched = {false};
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String desc,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                    if (!METHOD.equals(name) || !DESC.equals(desc)) {
                        return mv;
                    }
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitLdcInsn(className);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "frame", "(Ljava/lang/String;)V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("frame probe: " + className + ".traverse missing; no samples from it");
                return null;
            }
            AgentLog.info("frame probe: hook added to " + className + ".traverse");
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("frame probe: " + className + " transform failed", t);
            return null;
        }
    }
}
