package hypernova;

import hypernova.agent.textures.LazyTextureTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

class LazyTransformTest {
    private static final String LOADER = "com/fs/graphics/TextureLoader";
    private static final String REPO = "com/fs/graphics/oOoO";
    private static final String LAMBDA = "lambda$queueImage$0";
    private static final String LAMBDA_DESC = "(Ljava/lang/String;Ljava/lang/String;Z)V";
    private static final String LOOKUP_DESC = "(Ljava/lang/String;)Lcom/fs/graphics/Object;";

    @Test
    void addsQueueLambdaWhenAbsent() {
        byte[] in = classBytes(LOADER, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC, "loadTextureAsync",
                    "(Ljava/lang/String;Ljava/lang/String;)V", null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.RETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyTextureTransformer().transform(null, LOADER, null, null, in);
        assertNotNull(out);
        Map<String, List<String>> shape = readShape(out);
        List<String> lambda = shape.get(LAMBDA + LAMBDA_DESC);
        assertNotNull(lambda);
        assertTrue(lambda.contains("hypernova/agent/textures/LazyTextures#queue"));
    }

    @Test
    void existingLambdaIsLeftUntouched() {
        byte[] in = classBytes(LOADER, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PRIVATE | Opcodes.ACC_SYNTHETIC,
                    LAMBDA, LAMBDA_DESC, null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.RETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        assertNull(new LazyTextureTransformer().transform(null, LOADER, null, null, in));
    }

    @Test
    void wrapsRepositoryLookup() {
        byte[] in = classBytes(REPO, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "lookup", LOOKUP_DESC, null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.ACONST_NULL);
            mv.visitInsn(Opcodes.ARETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyTextureTransformer().transform(null, REPO, null, null, in);
        assertNotNull(out);
        Map<String, List<String>> shape = readShape(out);
        assertNotNull(shape.get("hypernova$getOriginal" + LOOKUP_DESC));
        List<String> wrapper = shape.get("lookup" + LOOKUP_DESC);
        assertNotNull(wrapper);
        assertTrue(wrapper.contains("hypernova/agent/textures/LazyTextures#probeLookup"));
        assertTrue(wrapper.contains("com/fs/graphics/oOoO#hypernova$getOriginal"));
        assertTrue(wrapper.contains("hypernova/agent/textures/LazyTextures#probeResult"));
        assertTrue(wrapper.contains("hypernova/agent/textures/LazyTextures#lookup"));
    }

    @Test
    void repositoryWithoutUniqueShapeIsUntouched() {
        byte[] in = classBytes(REPO, cv -> {
            for (int i = 0; i < 2; i++) {
                MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                        "lookup" + i, LOOKUP_DESC, null, null);
                mv.visitCode();
                mv.visitInsn(Opcodes.ACONST_NULL);
                mv.visitInsn(Opcodes.ARETURN);
                mv.visitMaxs(0, 0);
                mv.visitEnd();
            }
        });
        assertNull(new LazyTextureTransformer().transform(null, REPO, null, null, in));
    }

    @Test
    void malformedBytesReturnNull() {
        assertNull(new LazyTextureTransformer().transform(null, LOADER, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] classBytes(String name, Consumer<ClassVisitor> body) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        body.accept(cw);
        cw.visitEnd();
        return cw.toByteArray();
    }

    /** Reads the transformed class with ASM core only (asm-tree is not bundled). */
    private static Map<String, List<String>> readShape(byte[] bytes) {
        Map<String, List<String>> methods = new LinkedHashMap<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                List<String> calls = new ArrayList<>();
                methods.put(name + desc, calls);
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override
                    public void visitMethodInsn(int opcode, String owner, String name,
                                                String desc, boolean isInterface) {
                        calls.add(owner + "#" + name);
                    }
                };
            }
        }, 0);
        return methods;
    }
}
