package adebug;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.io.File;
import java.io.FileWriter;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

/**
 * Diagnostic-only agent for Route A.
 *
 * <p>Two independent MixinFR behaviours make FR 0.9.5 recompile every mod
 * source at startup:
 *
 * <ol>
 *   <li>MixinLib's {@code StarsectorTransformer} empties the URL array passed
 *       to the game's {@code ScriptStore} URLClassLoader, so mod jar URLs are
 *       no longer visible to the script loader.</li>
 *   <li>FR's script loader parent is the loader of {@code ScriptStore}; under
 *       MixinFR this can be the minimal system loader rather than the
 *       TargetClassLoader that owns the game jars.</li>
 * </ol>
 *
 * <p>This agent (a) turns MixinLib's {@code StarsectorTransformer.transform}
 * into an identity function so the original URL list survives, and (b) forces
 * the script loader parent to the classloader that defined
 * {@code com.fs.starfarer.loading.scripts.B} (MixinLib's TargetClassLoader).
 * No game or vendor file is modified on disk.
 */
public final class AProxyParentAgent {
    private static final String TARGET_B =
            "com/fs/starfarer/loading/scripts/B";
    private static final String TARGET_SECURE =
            "com/fs/starfarer/loading/scripts/SecureClassLoader";
    private static final String TARGET_TRANSFORMER =
            "com/github/alphardpaarthurnax/mixinlib/janino/StarsectorTransformer";
    private static final String DESC = "(Ljava/lang/ClassLoader;)V";
    private static final String SELF = "adebug/AProxyParentAgent";

    private static volatile ClassLoader targetLoader;

    private AProxyParentAgent() {
    }

    public static ClassLoader targetLoader() {
        ClassLoader loader = targetLoader;
        if (loader != null) {
            return loader;
        }
        return Thread.currentThread().getContextClassLoader();
    }

    public static void premain(String args, Instrumentation inst) {
        log("premain");
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                                    Class<?> redefined,
                                    ProtectionDomain protectionDomain,
                                    byte[] bytes) {
                if (redefined != null) {
                    return null;
                }
                if (TARGET_TRANSFORMER.equals(className)) {
                    try {
                        byte[] patched = identityTransformer(bytes);
                        log("patched StarsectorTransformer (identity)");
                        return patched;
                    } catch (Throwable t) {
                        log("transformer patch failed: " + t);
                        return null;
                    }
                }
                boolean isB = TARGET_B.equals(className);
                boolean isSecure = TARGET_SECURE.equals(className);
                if (!isB && !isSecure) {
                    return null;
                }
                if (isB && loader != null) {
                    targetLoader = loader;
                    log("captured target loader=" + loader);
                }
                try {
                    ClassReader reader = new ClassReader(bytes);
                    ClassWriter writer = new ClassWriter(reader, 0);
                    ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                        @Override
                        public MethodVisitor visitMethod(int access, String name,
                                                         String descriptor,
                                                         String signature,
                                                         String[] exceptions) {
                            MethodVisitor mv = super.visitMethod(
                                    access, name, descriptor, signature, exceptions);
                            if (!"<init>".equals(name) || !DESC.equals(descriptor)) {
                                return mv;
                            }
                            return new MethodVisitor(Opcodes.ASM9, mv) {
                                @Override
                                public void visitVarInsn(int opcode, int var) {
                                    if (opcode == Opcodes.ALOAD && var == 1) {
                                        return;
                                    }
                                    super.visitVarInsn(opcode, var);
                                }

                                @Override
                                public void visitMethodInsn(int opcode, String owner,
                                                            String name2, String desc2,
                                                            boolean isInterface) {
                                    if (opcode == Opcodes.INVOKESPECIAL
                                            && "java/lang/ClassLoader".equals(owner)
                                            && "<init>".equals(name2)
                                            && (DESC.equals(desc2)
                                                || "()V".equals(desc2))) {
                                        super.visitMethodInsn(
                                                Opcodes.INVOKESTATIC, SELF,
                                                "targetLoader",
                                                "()Ljava/lang/ClassLoader;", false);
                                        super.visitMethodInsn(
                                                opcode, owner, name2, DESC, isInterface);
                                        return;
                                    }
                                    super.visitMethodInsn(opcode, owner, name2, desc2,
                                            isInterface);
                                }
                            };
                        }
                    };
                    reader.accept(visitor, 0);
                    log("patched " + className + " ctor loader=" + loader);
                    return writer.toByteArray();
                } catch (Throwable t) {
                    log("transform failed for " + className + ": " + t);
                    return null;
                }
            }
        });
    }

    /** Replace StarsectorTransformer.transform(String, byte[]) with `return bytes;`. */
    private static byte[] identityTransformer(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, 0);
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String descriptor,
                                             String signature, String[] exceptions) {
                MethodVisitor mv = super.visitMethod(
                        access, name, descriptor, signature, exceptions);
                if (!"transform".equals(name)
                        || !"(Ljava/lang/String;[B)[B".equals(descriptor)) {
                    return mv;
                }
                return new MethodVisitor(Opcodes.ASM9, mv) {
                    @Override
                    public void visitCode() {
                        super.visitCode();
                    }

                    @Override
                    public void visitInsn(int opcode) {
                    }

                    @Override
                    public void visitVarInsn(int opcode, int var) {
                    }

                    @Override
                    public void visitTypeInsn(int opcode, String type) {
                    }

                    @Override
                    public void visitFieldInsn(int opcode, String owner, String name2,
                                               String desc2) {
                    }

                    @Override
                    public void visitMethodInsn(int opcode, String owner, String name2,
                                                String desc2, boolean isInterface) {
                    }

                    @Override
                    public void visitInvokeDynamicInsn(String name2, String desc2,
                                                       Handle bsm, Object... bsmArgs) {
                    }

                    @Override
                    public void visitJumpInsn(int opcode, Label label) {
                    }

                    @Override
                    public void visitLabel(Label label) {
                    }

                    @Override
                    public void visitLdcInsn(Object value) {
                    }

                    @Override
                    public void visitIincInsn(int var, int increment) {
                    }

                    @Override
                    public void visitTableSwitchInsn(int min, int max, Label dflt,
                                                     Label... labels) {
                    }

                    @Override
                    public void visitLookupSwitchInsn(Label dflt, int[] keys,
                                                      Label[] labels) {
                    }

                    @Override
                    public void visitMultiANewArrayInsn(String desc2, int numDimensions) {
                    }

                    @Override
                    public void visitFrame(int type, int numLocal, Object[] local,
                                           int numStack, Object[] stack) {
                    }

                    @Override
                    public void visitLineNumber(int line, Label start) {
                    }

                    @Override
                    public void visitTryCatchBlock(Label start, Label end, Label handler,
                                                   String type) {
                    }

                    @Override
                    public void visitLocalVariable(String name2, String desc2,
                                                   String signature2, Label start,
                                                   Label end, int index) {
                    }

                    @Override
                    public void visitMaxs(int maxStack, int maxLocals) {
                        super.visitVarInsn(Opcodes.ALOAD, 1);
                        super.visitInsn(Opcodes.ARETURN);
                        super.visitMaxs(1, 2);
                    }
                };
            }
        };
        reader.accept(visitor, 0);
        return writer.toByteArray();
    }

    private static synchronized void log(String message) {
        try {
            File file = new File(System.getProperty("user.dir", "."),
                    "adebug-agent.log");
            try (FileWriter writer = new FileWriter(file, true)) {
                writer.write(message + "\n");
            }
        } catch (Throwable ignored) {
            // diagnostic logging must never break the game
        }
        System.out.println("[adebug-agent] " + message);
    }
}
