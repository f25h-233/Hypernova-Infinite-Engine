package hypernova.agent.textures;

import hypernova.agent.AgentLog;
import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Drains pending proxies into oOoO.new before mod onApplicationLoad hooks run.
 * MarkovNames.loadIfNeeded() is the first call of ResourceLoaderState's
 * initMods lambda (FR-Main-Loader thread, i.e. FileLoader.mainThread), and
 * onApplicationLoad runs later in the same lambda. Missing method or malformed
 * bytes leave the class untouched; the lazy module then fails open (its drain
 * never runs and the gate catches it).
 */
public final class LazyDrainTransformer implements ClassFileTransformer {
    public static final String TARGET = "com/fs/starfarer/api/impl/campaign/procgen/MarkovNames";
    private static final String METHOD = "loadIfNeeded";
    private static final String DESC = "()V";
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
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "drainPending", "()V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("lazy: MarkovNames.loadIfNeeded missing; engine-map drain disabled");
                return null;
            }
            AgentLog.info("lazy: engine-map drain hook added to MarkovNames.loadIfNeeded");
            LazyTextures.noteDrainArmed();
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("lazy: MarkovNames transform failed; engine-map drain disabled", t);
            return null;
        }
    }
}
