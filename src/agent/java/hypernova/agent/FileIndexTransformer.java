package hypernova.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/** Replaces FR's directory crawl with a cached lookup when valid. */
public final class FileIndexTransformer implements ClassFileTransformer {
    public static final String TARGET =
            "com/genir/renderer/overrides/loading/FileLoaderFast$DirectoryCrawler";
    private static final String HOOK = "hypernova/agent/FileIndexHook";

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
                    if (!"cacheLocations".equals(name) || !"()I".equals(descriptor)) return mv;
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitVarInsn(Opcodes.ALOAD, 0);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "tryLoad",
                                    "(Ljava/lang/Object;)I", false);
                            super.visitVarInsn(Opcodes.ISTORE, 1);
                            super.visitVarInsn(Opcodes.ILOAD, 1);
                            Label continueCrawl = new Label();
                            super.visitJumpInsn(Opcodes.IFLT, continueCrawl);
                            super.visitVarInsn(Opcodes.ILOAD, 1);
                            super.visitInsn(Opcodes.IRETURN);
                            super.visitLabel(continueCrawl);
                            super.visitFrame(Opcodes.F_SAME, 0, null, 0, null);
                        }

                        @Override
                        public void visitInsn(int opcode) {
                            if (opcode == Opcodes.IRETURN) {
                                super.visitVarInsn(Opcodes.ALOAD, 0);
                                super.visitVarInsn(Opcodes.ILOAD, 1);
                                super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "save",
                                        "(Ljava/lang/Object;I)V", false);
                            }
                            super.visitInsn(opcode);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            return patched[0] ? writer.toByteArray() : null;
        } catch (Throwable t) {
            AgentLog.fail("file index transform failed; FR crawl stays untouched", t);
            return null;
        }
    }
}
