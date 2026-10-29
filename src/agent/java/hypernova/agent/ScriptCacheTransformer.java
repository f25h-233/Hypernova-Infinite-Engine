package hypernova.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScriptCacheTransformer implements ClassFileTransformer {
    public static final String TARGET =
            "com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader";
    public static final String HOOK = "hypernova/agent/ScriptCacheHook";
    static final String CTOR_DESC = "(Ljava/lang/ClassLoader;)V";
    static final String FIND_DESC = "(Ljava/lang/String;)Ljava/lang/Class;";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || !TARGET.equals(className) || redefined != null) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, 0);
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
                    if ("<init>".equals(name) && CTOR_DESC.equals(descriptor)) {
                        return new MethodVisitor(Opcodes.ASM9, mv) {
                            @Override
                            public void visitInsn(int opcode) {
                                if (opcode == Opcodes.RETURN) {
                                    super.visitVarInsn(Opcodes.ALOAD, 0);
                                    super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "preload",
                                            "(Ljava/lang/Object;)V", false);
                                }
                                super.visitInsn(opcode);
                            }
                        };
                    }
                    if ("findClass".equals(name) && FIND_DESC.equals(descriptor)) {
                        return new MethodVisitor(Opcodes.ASM9, mv) {
                            @Override
                            public void visitCode() {
                                super.visitCode();
                                super.visitVarInsn(Opcodes.ALOAD, 0);
                                super.visitVarInsn(Opcodes.ALOAD, 1);
                                super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "onFindClass",
                                        "(Ljava/lang/Object;Ljava/lang/String;)V", false);
                            }
                        };
                    }
                    return mv;
                }
            };
            reader.accept(visitor, 0);
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("transform failed for " + className, t);
            return null;
        }
    }
}
