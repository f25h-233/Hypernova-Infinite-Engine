package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.HexFormat;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 把 GraphicsLib 1.12.1 的 TextureData 替换成「缓存法线图只登记、不加载」的补丁类。
 *
 * <p>只对 SHA-256 精确匹配的原类生效；其它版本一律 no-op，绝不猜测。
 */
public final class TextureCacheTransformer implements ClassFileTransformer {
    public static final String TARGET = "org/dark/shaders/util/TextureData";

    private static final String RES =
            "/hypernova/agent/textures/TextureData.class.bin";
    private static final String PROPS =
            "/hypernova/agent/textures/patch.properties";

    private final byte[] patched;
    private final String expectedSha;
    private final AtomicBoolean applied = new AtomicBoolean();
    private final AtomicBoolean mismatch = new AtomicBoolean();

    TextureCacheTransformer(byte[] patched, String expectedSha) {
        this.patched = patched;
        this.expectedSha = expectedSha;
    }

    /** 读取打包资源；缺失/损坏返回 null，agent 继续启动。 */
    public static TextureCacheTransformer create() {
        try {
            byte[] bytes = readAll(TextureCacheTransformer.class.getResourceAsStream(RES));
            Properties props = new Properties();
            try (InputStream in = TextureCacheTransformer.class.getResourceAsStream(PROPS)) {
                if (in == null) {
                    AgentLog.info("textures: patch.properties missing; texture patch disabled");
                    return null;
                }
                props.load(in);
            }
            String sha = props.getProperty("sourceSha256", "");
            if (bytes == null || bytes.length == 0 || sha.isEmpty()) {
                AgentLog.info("textures: patch resource incomplete; texture patch disabled");
                return null;
            }
            AgentLog.info("textures: patch resource loaded, sourceSha256=" + sha
                    + ", bytes=" + bytes.length);
            return new TextureCacheTransformer(bytes, sha);
        } catch (Throwable t) {
            AgentLog.fail("textures: cannot load patch resource", t);
            return null;
        }
    }

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (!TARGET.equals(className) || bytes == null || redefined != null) return null;
        try {
            String actual = sha256(bytes);
            if (!expectedSha.equals(actual)) {
                if (mismatch.compareAndSet(false, true)) {
                    AgentLog.info("textures: TextureData sha mismatch, not patching (expected="
                            + expectedSha + ", actual=" + actual + ")");
                }
                return null;
            }
            if (applied.compareAndSet(false, true)) {
                AgentLog.info("textures: patched " + className
                        + " (shaderLib 1.12.1 lazy normal cache)");
            }
            return patched.clone();
        } catch (Throwable t) {
            AgentLog.fail("textures: transform failed", t);
            return null;
        }
    }

    static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static byte[] readAll(InputStream in) throws Exception {
        if (in == null) return null;
        try (InputStream src = in; ByteArrayOutputStream out = new ByteArrayOutputStream(96 * 1024)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = src.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
