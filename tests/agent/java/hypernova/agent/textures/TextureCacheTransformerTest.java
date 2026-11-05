package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.*;

class TextureCacheTransformerTest {
    private static final Path CLASSPATH_ROOT = Path.of("build/agent/textures");
    private static final Path INDEX =
            CLASSPATH_ROOT.resolve("hypernova/agent/textures/variants.properties");

    /** 从构建产物读取全部变体；构建脚本保证每个变体都有原始 class 供测试。 */
    private static Map<String, TextureCacheTransformer.Variant> variants() throws Exception {
        Properties props = new Properties();
        try (InputStream in = Files.newInputStream(INDEX)) {
            props.load(in);
        }
        int count = Integer.parseInt(props.getProperty("count", "0").trim());
        Map<String, TextureCacheTransformer.Variant> out = new LinkedHashMap<>();
        for (int i = 0; i < count; i++) {
            String p = "variant." + i + ".";
            String sourceSha = props.getProperty(p + "sourceSha256");
            String patchedSha = props.getProperty(p + "patchedSha256");
            String version = props.getProperty(p + "graphicsLibVersion");
            String resource = props.getProperty(p + "resource");
            assertNotNull(sourceSha, p + "sourceSha256");
            assertNotNull(patchedSha, p + "patchedSha256");
            assertNotNull(version, p + "graphicsLibVersion");
            assertNotNull(resource, p + "resource");
            Path bin = CLASSPATH_ROOT.resolve(resource.replaceFirst("^/", ""));
            assertTrue(Files.isRegularFile(bin), "missing variant resource " + bin);
            byte[] patched = Files.readAllBytes(bin);
            assertEquals(patchedSha, TextureCacheTransformer.sha256(patched),
                    version + " patched resource must match its pinned sha256");
            out.put(sourceSha, new TextureCacheTransformer.Variant(version, sourceSha, patchedSha, patched));
        }
        return out;
    }

    private static byte[] original(String sourceSha) throws Exception {
        return Files.readAllBytes(Path.of("build/agent/texture-original-" + sourceSha + ".class"));
    }

    @Test
    void hasAtLeastTheKnownVersions() throws Exception {
        Map<String, TextureCacheTransformer.Variant> v = variants();
        assertTrue(v.size() >= 2, "expected at least 1.12.1 and 1.12.2 variants, got " + v.size());
        var versions = v.values().stream().map(x -> x.version).toList();
        assertTrue(versions.contains("1.12.1"), "missing 1.12.1 variant: " + versions);
        assertTrue(versions.contains("1.12.2"), "missing 1.12.2 variant: " + versions);
    }

    @Test
    void replacesEachExactKnownOriginal() throws Exception {
        Map<String, TextureCacheTransformer.Variant> all = variants();
        TextureCacheTransformer t = new TextureCacheTransformer(all);
        for (var e : all.entrySet()) {
            byte[] orig = original(e.getKey());
            byte[] out = t.transform(null, TextureCacheTransformer.TARGET, null, null, orig);
            assertNotNull(out, e.getValue().version + " 原类必须命中");
            assertArrayEquals(e.getValue().bytes, out, e.getValue().version + " 必须返回该版本的补丁字节");
        }
    }

    @Test
    void rejectsDifferentBytes() throws Exception {
        Map<String, TextureCacheTransformer.Variant> all = variants();
        TextureCacheTransformer t = new TextureCacheTransformer(all);
        byte[] orig = original(all.keySet().iterator().next());
        byte[] mutated = orig.clone();
        mutated[mutated.length - 1] ^= 0x01;
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, null, null, mutated),
                "hash 不匹配必须 no-op，不能把某个版本的字节塞进别的版本");
    }

    @Test
    void rejectsUnknownVersion() throws Exception {
        Map<String, TextureCacheTransformer.Variant> all = variants();
        TextureCacheTransformer t = new TextureCacheTransformer(all);
        byte[] stranger = new byte[]{0x01, 0x02, 0x03, 0x04};
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, null, null, stranger),
                "未知版本必须 no-op");
    }

    @Test
    void ignoresUnrelatedClassesAndNullInputs() throws Exception {
        TextureCacheTransformer t = new TextureCacheTransformer(variants());
        assertNull(t.transform(null, "com/example/Other", null, null, new byte[]{1, 2, 3}));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, null, null, null));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, String.class, null,
                new byte[]{1, 2, 3}));
    }

    @Test
    void neverThrowsOnGarbage() throws Exception {
        TextureCacheTransformer t = new TextureCacheTransformer(variants());
        assertDoesNotThrow(() -> t.transform(null, TextureCacheTransformer.TARGET, null, null,
                new byte[]{(byte) 0xCA, (byte) 0xFE}));
    }

    @Test
    void patchedClassesAreJava17() throws Exception {
        for (var v : variants().values()) {
            byte[] p = v.bytes;
            int major = ((p[6] & 0xFF) << 8) | (p[7] & 0xFF);
            assertEquals(61, major, v.version + " 补丁类必须是 --release 17（major 61）");
        }
    }
}
