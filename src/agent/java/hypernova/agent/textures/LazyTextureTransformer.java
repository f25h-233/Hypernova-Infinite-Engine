package hypernova.agent.textures;

import hypernova.agent.AgentLog;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Task 1 probe transformer.
 *
 * <p>Hook 1: com/fs/graphics/TextureLoader is the executed class. FR renames
 * its 7-arg o00000 to loadTexture_vanilla and merges the donor
 * com/genir/renderer/overrides/loading/textures/TextureLoader. MethodCopier
 * skips donor methods whose name+descriptor already exists, so adding the
 * donor's lambda here makes the queue workers execute our probe.
 *
 * <p>Hook 2: com/fs/graphics/oOoO.get is the only global texture lookup. It is
 * renamed to hypernova$getOriginal and wrapped; the wrapper records demand and
 * returns exactly the same value. The same class's static register method
 * super(String,Object) gets an onRegister probe at its head so real objects that
 * someone loads for a skipped path are absorbed into the proxy.
 */
public final class LazyTextureTransformer implements ClassFileTransformer {
    public static final String TEXTURE_LOADER = "com/fs/graphics/TextureLoader";
    public static final String REPOSITORY = "com/fs/graphics/oOoO";
    private static final String HOOK = "hypernova/agent/textures/LazyTextures";
    private static final String LAMBDA = "lambda$queueImage$0";
    private static final String LAMBDA_DESC = "(Ljava/lang/String;Ljava/lang/String;Z)V";
    private static final String LOOKUP_DESC = "(Ljava/lang/String;)Lcom/fs/graphics/Object;";
    private static final String RENAMED_LOOKUP = "hypernova$getOriginal";
    private static final String REGISTER_NAME = "super";
    private static final String REGISTER_DESC = "(Ljava/lang/String;Lcom/fs/graphics/Object;)V";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null || bytes == null) return null;
        try {
            if (TEXTURE_LOADER.equals(className)) return patchQueueLambda(bytes);
            if (REPOSITORY.equals(className)) return patchRepository(bytes);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: transform failed for " + className + "; left untouched", t);
        }
        return null;
    }

    private static byte[] patchQueueLambda(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        boolean[] present = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                if (LAMBDA.equals(name) && LAMBDA_DESC.equals(desc)) present[0] = true;
                return super.visitMethod(access, name, desc, signature, exceptions);
            }

            @Override
            public void visitEnd() {
                if (!present[0]) {
                    addQueueLambda(super.visitMethod(
                            Opcodes.ACC_PRIVATE | Opcodes.ACC_SYNTHETIC,
                            LAMBDA, LAMBDA_DESC, null, null));
                }
                super.visitEnd();
            }
        };
        reader.accept(visitor, 0);
        if (present[0]) {
            AgentLog.info("lazy probe: " + LAMBDA + " already present in " + TEXTURE_LOADER
                    + "; transform skipped (agent ordered after FR?)");
            return null;
        }
        AgentLog.info("lazy probe: queue lambda hook added to " + TEXTURE_LOADER);
        LazyTextures.noteQueueArmed();
        return writer.toByteArray();
    }

    private static void addQueueLambda(MethodVisitor mv) {
        Label start = new Label();
        Label end = new Label();
        Label handler = new Label();
        Label rethrow = new Label();
        Label done = new Label();
        mv.visitCode();
        mv.visitTryCatchBlock(start, end, handler, "java/lang/Throwable");
        mv.visitLabel(start);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "queue",
                "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V", false);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "markRenderProgress", "()V", false);
        mv.visitLabel(end);
        mv.visitJumpInsn(Opcodes.GOTO, done);
        mv.visitLabel(handler);
        mv.visitFrame(Opcodes.F_SAME1, 0, null, 1, new Object[]{"java/lang/Throwable"});
        mv.visitVarInsn(Opcodes.ILOAD, 3);
        mv.visitJumpInsn(Opcodes.IFEQ, rethrow);
        mv.visitInsn(Opcodes.POP);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "removeKnown",
                "(Ljava/lang/Object;Ljava/lang/String;)V", false);
        mv.visitJumpInsn(Opcodes.GOTO, done);
        mv.visitLabel(rethrow);
        mv.visitFrame(Opcodes.F_SAME1, 0, null, 1, new Object[]{"java/lang/Throwable"});
        mv.visitInsn(Opcodes.ATHROW);
        mv.visitLabel(done);
        mv.visitFrame(Opcodes.F_SAME, 0, null, 0, null);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }

    private static byte[] patchRepository(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        String[] found = {null};
        int[] count = {0};
        boolean[] registerPatched = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                if (LOOKUP_DESC.equals(desc) && (access & Opcodes.ACC_STATIC) != 0) {
                    count[0]++;
                    found[0] = name;
                    return super.visitMethod(access, RENAMED_LOOKUP, desc, signature, exceptions);
                }
                MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                if (REGISTER_NAME.equals(name) && REGISTER_DESC.equals(desc)
                        && (access & Opcodes.ACC_STATIC) != 0) {
                    registerPatched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitVarInsn(Opcodes.ALOAD, 0);
                            super.visitVarInsn(Opcodes.ALOAD, 1);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "onRegister",
                                    "(Ljava/lang/String;Ljava/lang/Object;)V", false);
                        }
                    };
                }
                return mv;
            }

            @Override
            public void visitEnd() {
                if (count[0] == 1) {
                    addRepositoryWrapper(super.visitMethod(
                            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                            found[0], LOOKUP_DESC, null, null));
                }
                super.visitEnd();
            }
        };
        reader.accept(visitor, 0);
        if (count[0] != 1) {
            AgentLog.info("lazy probe: " + REPOSITORY + " lookup shape not unique (candidates="
                    + count[0] + "); transform skipped");
            return null;
        }
        AgentLog.info("lazy probe: repository lookup hook added to " + REPOSITORY
                + " (method=" + found[0] + ")");
        if (registerPatched[0]) {
            AgentLog.info("lazy probe: engine map register hook added to " + REPOSITORY
                    + " (method=" + REGISTER_NAME + ")");
            LazyTextures.noteRegisterArmed();
        } else {
            AgentLog.info("lazy probe: engine map register hook missing in " + REPOSITORY
                    + "; onRegister disabled");
        }
        return writer.toByteArray();
    }

    private static void addRepositoryWrapper(MethodVisitor mv) {
        Label miss = new Label();
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "probeLookup",
                "(Ljava/lang/String;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, REPOSITORY, RENAMED_LOOKUP,
                LOOKUP_DESC, false);
        mv.visitVarInsn(Opcodes.ASTORE, 1);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "probeResult",
                "(Ljava/lang/String;Ljava/lang/Object;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitJumpInsn(Opcodes.IFNULL, miss);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitLabel(miss);
        mv.visitFrame(Opcodes.F_APPEND, 1, new Object[]{"java/lang/Object"}, 0, null);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "lookup",
                "(Ljava/lang/String;)Ljava/lang/Object;", false);
        mv.visitTypeInsn(Opcodes.CHECKCAST, "com/fs/graphics/Object");
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }
}
