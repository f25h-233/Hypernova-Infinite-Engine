package hypernova.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Marks the startup phases on classes that are actually loaded under their own
 * names. The old donor target
 * {@code com/genir/renderer/overrides/loading/ResourceLoaderState} is copied into
 * {@code com.fs.starfarer.loading.ResourceLoaderState} by FR's MethodCopier and
 * its own class is never loaded, so patching it produced zero marks.
 *
 * <p>Likewise {@code com/genir/renderer/overrides/loading/FileLoader} is a
 * {@code mergeClass} donor (merged into {@code com/fs/util/C}); its
 * {@code initModLoading} method only executes inside the game class and cannot
 * be patched by a transformer registered before FR. The first genuinely
 * executed statement of the merged {@code initMods} is
 * {@code MarkovNames.loadIfNeeded()}, so that real game class is used for the
 * {@code mods.start} anchor instead. The non-executed donor targets are logged
 * explicitly by {@link HypernovaAgent} at premain.
 */
public final class StartupTimelineTransformer implements ClassFileTransformer {
    public static final String LOADER_TARGET =
            "com/genir/renderer/overrides/loading/FileLoaderFast";
    public static final String DDS_TARGET =
            "com/genir/renderer/overrides/loading/textures/DDSIntegration";
    public static final String MODS_TARGET =
            "com/fs/starfarer/api/impl/campaign/procgen/MarkovNames";
    private static final String HOOK = "hypernova/agent/StartupTimeline";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null) return null;
        try {
            if (LOADER_TARGET.equals(className)) {
                return patch(bytes, className, "<init>", "(Ljava/util/List;)V", "loader", true);
            }
            if (DDS_TARGET.equals(className)) {
                return patch(bytes, className, "initialize", "()V", "dds", true);
            }
            if (MODS_TARGET.equals(className)) {
                return patch(bytes, className, "loadIfNeeded", "()V", "mods", false);
            }
            return null;
        } catch (Throwable t) {
            AgentLog.fail("startup timeline transform failed; phase marks disabled", t);
            return null;
        }
    }

    private static byte[] patch(byte[] bytes, String className, String method, String descriptor,
                                String label, boolean markEnd) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        boolean[] patched = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                if (!method.equals(name) || !descriptor.equals(desc)) return mv;
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
                        if (markEnd && opcode == Opcodes.RETURN) {
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
        if (!patched[0]) {
            // A target class that loads without the expected method must be visible,
            // never a silent no-op.
            AgentLog.info("timeline: target method missing " + className + "#" + method
                    + descriptor + "; phase mark disabled");
            return null;
        }
        return writer.toByteArray();
    }
}
