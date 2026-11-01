package hypernova.agent.textures;

import hypernova.agent.AgentLog;
import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Captures the runtime main thread at BaseGameState.traverse(). BaseGameState
 * is not a FR merge target (only constant-pool sync), so the injected call
 * survives. GLLauncher states are ignored by LazyTextures.captureMainThread.
 */
public final class LazyGameThreadTransformer implements ClassFileTransformer {
    public static final String TARGET = "com/fs/starfarer/BaseGameState";
    private static final String METHOD = "traverse";
    private static final String DESC = "()Ljava/lang/String;";
    private static final String HOOK = "hypernova/agent/textures/LazyTextures";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || !TARGET.equals(className) || redefined != null || bytes == null) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            boolean[] patched = {false};
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String desc,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                    if (!METHOD.equals(name) || !DESC.equals(desc)) return mv;
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitVarInsn(Opcodes.ALOAD, 0);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "captureMainThread", "(Ljava/lang/Object;)V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("lazy: BaseGameState.traverse missing; runtime main-thread capture disabled");
                return null;
            }
            AgentLog.info("lazy: runtime main-thread capture hook added to BaseGameState.traverse");
            LazyTextures.noteThreadArmed();
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("lazy: BaseGameState transform failed; capture disabled", t);
            return null;
        }
    }
}
