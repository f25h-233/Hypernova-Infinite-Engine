package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class TextureCacheTransformerTest {
    private static final Path ORIG = Path.of("build/agent/texture-original.class");
    private static final Path PATCHED =
            Path.of("build/agent/textures/hypernova/agent/textures/TextureData.class.bin");

    private static TextureCacheTransformer transformer() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] patched = Files.readAllBytes(PATCHED);
        return new TextureCacheTransformer(patched, TextureCacheTransformer.sha256(orig));
    }

    @Test
    void replacesTheExactKnownOriginal() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] patched = Files.readAllBytes(PATCHED);
        byte[] out = transformer().transform(null, TextureCacheTransformer.TARGET, null, null, orig);
        assertNotNull(out, "hash 匹配时必须返回补丁字节");
        assertArrayEquals(patched, out);
    }

    @Test
    void rejectsDifferentBytes() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] mutated = orig.clone();
        mutated[mutated.length - 1] ^= 0x01;
        assertNull(transformer().transform(null, TextureCacheTransformer.TARGET, null, null, mutated),
                "hash 不匹配必须 no-op，不能把 1.12.1 的字节塞进别的版本");
    }

    @Test
    void ignoresUnrelatedClassesAndNullInputs() throws Exception {
        TextureCacheTransformer t = transformer();
        assertNull(t.transform(null, "com/example/Other", null, null, new byte[]{1, 2, 3}));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, null, null, null));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, String.class, null,
                new byte[]{1, 2, 3}));
    }

    @Test
    void neverThrowsOnGarbage() throws Exception {
        TextureCacheTransformer t = transformer();
        assertDoesNotThrow(() -> t.transform(null, TextureCacheTransformer.TARGET, null, null,
                new byte[]{(byte) 0xCA, (byte) 0xFE}));
    }

    @Test
    void patchedClassIsJava17() throws Exception {
        byte[] p = Files.readAllBytes(PATCHED);
        int major = ((p[6] & 0xFF) << 8) | (p[7] & 0xFF);
        assertEquals(61, major, "补丁类必须是 --release 17（major 61）");
    }
}
