package hypernova.agent;

import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Injects {@link FrameProbe#frame(String)} at the start of
 * {@code org.lwjgl.opengl.Display.update(Z)V}. Display.update is the
 * per-frame buffer swap inside the title/campaign/combat loops; do not use
 * BaseGameState.traverse/CombatState.traverse, which are whole-state loops.
 *
 * <p>Only {@code update(Z)V} is patched: {@code update()V} delegates to it
 * ({@code iconst_1; invokestatic update:(Z)V}), so patching both would sample
 * every frame twice. A missing method is logged and left untouched; transform
 * failures are fail-open and visible in the agent log.
 */
public final class FrameProbeTransformer implements ClassFileTransformer {
    static final String TARGET = "org/lwjgl/opengl/Display";
    private static final String METHOD = "update";
    private static final String DESC = "(Z)V";
    private static final String SOURCE = "Display.update";
    private static final String HOOK = "hypernova/agent/FrameProbe";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null || bytes == null) {
            return null;
        }
        if (!TARGET.equals(className)) {
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
                            super.visitLdcInsn(SOURCE);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "frame", "(Ljava/lang/String;)V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("frame probe: Display.update(Z)V missing; no samples");
                return null;
            }
            AgentLog.info("frame probe: hook added to Display.update");
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("frame probe: Display transform failed", t);
            return null;
        }
    }
}
