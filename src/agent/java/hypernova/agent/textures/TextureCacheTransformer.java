package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 把 GraphicsLib 的 TextureData 替换成「缓存法线图只登记、不加载」的补丁类。
 *
 * <p>每个受支持的 GraphicsLib 版本各有一份预编译补丁类，索引在
 * {@code variants.properties}；运行时按加载到的原类 SHA-256 精确匹配。
 * 匹配不到任何变体就 no-op（fail-closed），只记一条可诊断日志，绝不猜测。
 */
public final class TextureCacheTransformer implements ClassFileTransformer {
    public static final String TARGET = "org/dark/shaders/util/TextureData";

    private static final String INDEX = "/hypernova/agent/textures/variants.properties";

    /** 一个受支持版本的补丁：原类 SHA-256 → 已编译的替换类。 */
    static final class Variant {
        final String version;
        final String sourceSha;
        final String patchedSha;
        final byte[] bytes;

        Variant(String version, String sourceSha, String patchedSha, byte[] bytes) {
            this.version = version;
            this.sourceSha = sourceSha;
            this.patchedSha = patchedSha;
            this.bytes = bytes;
        }
    }

    private final Map<String, Variant> bySourceSha;
    private final AtomicBoolean applied = new AtomicBoolean();
    private final AtomicBoolean unsupportedLogged = new AtomicBoolean();

    TextureCacheTransformer(Map<String, Variant> bySourceSha) {
        this.bySourceSha = bySourceSha;
    }

    /** 读取打包的变体索引；缺失/损坏返回 null，agent 继续启动。 */
    public static TextureCacheTransformer create() {
        try (InputStream in = TextureCacheTransformer.class.getResourceAsStream(INDEX)) {
            if (in == null) {
                AgentLog.info("textures: variants.properties missing; texture patch disabled");
                return null;
            }
            Map<String, Variant> variants = loadIndex(in);
            if (variants.isEmpty()) {
                AgentLog.info("textures: no usable variants; texture patch disabled");
                return null;
            }
            StringBuilder supported = new StringBuilder();
            for (Variant v : variants.values()) {
                if (supported.length() > 0) supported.append(", ");
                supported.append(v.version).append(" (").append(v.sourceSha, 0, 12).append(')');
            }
            AgentLog.info("textures: patch resources loaded, variants=" + variants.size()
                    + " [" + supported + "]");
            return new TextureCacheTransformer(variants);
        } catch (Throwable t) {
            AgentLog.fail("textures: cannot load patch resources", t);
            return null;
        }
    }

    /** 解析索引并读取每个变体的补丁类；单个变体坏掉不影响其它变体。 */
    static Map<String, Variant> loadIndex(InputStream in) throws Exception {
        Properties props = new Properties();
        props.load(in);
        int count;
        try {
            count = Integer.parseInt(props.getProperty("count", "0").trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("bad variant count", e);
        }
        Map<String, Variant> out = new LinkedHashMap<>();
        for (int i = 0; i < count; i++) {
            String prefix = "variant." + i + ".";
            String version = props.getProperty(prefix + "graphicsLibVersion", "").trim();
            String sourceSha = props.getProperty(prefix + "sourceSha256", "").trim();
            String patchedSha = props.getProperty(prefix + "patchedSha256", "").trim();
            String resource = props.getProperty(prefix + "resource", "").trim();
            if (version.isEmpty() || sourceSha.isEmpty() || patchedSha.isEmpty() || resource.isEmpty()) {
                AgentLog.info("textures: variant " + i + " incomplete; skipped");
                continue;
            }
            try {
                byte[] bytes = readAll(TextureCacheTransformer.class.getResourceAsStream(resource));
                if (bytes == null || bytes.length == 0) {
                    AgentLog.info("textures: variant " + version + " resource missing; skipped");
                    continue;
                }
                String actual = sha256(bytes);
                if (!patchedSha.equals(actual)) {
                    AgentLog.info("textures: variant " + version + " resource corrupt (expected="
                            + patchedSha + ", actual=" + actual + "); skipped");
                    continue;
                }
                out.put(sourceSha, new Variant(version, sourceSha, patchedSha, bytes));
            } catch (Throwable t) {
                AgentLog.fail("textures: variant " + version + " load failed; skipped", t);
            }
        }
        return out;
    }

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (!TARGET.equals(className) || bytes == null || redefined != null) return null;
        try {
            String actual = sha256(bytes);
            Variant variant = bySourceSha.get(actual);
            if (variant == null) {
                if (unsupportedLogged.compareAndSet(false, true)) {
                    AgentLog.info("textures: unsupported GraphicsLib TextureData (sha256=" + actual
                            + "); supported=" + supportedVersions()
                            + "; lazy normal cache disabled for this version");
                }
                return null;
            }
            if (applied.compareAndSet(false, true)) {
                initCacheProbe(protectionDomain);
                AgentLog.info("textures: patched " + className
                        + " (GraphicsLib " + variant.version + " lazy normal cache)");
            }
            return variant.bytes.clone();
        } catch (Throwable t) {
            AgentLog.fail("textures: transform failed", t);
            return null;
        }
    }

    private String supportedVersions() {
        StringBuilder sb = new StringBuilder();
        for (Variant v : bySourceSha.values()) {
            if (sb.length() > 0) sb.append(", ");
            sb.append(v.version);
        }
        return sb.length() == 0 ? "none" : sb.toString();
    }

    /**
     * 在 agent 域扫描 GraphicsLib 的 cache/ 目录。补丁类运行在脚本域，
     * 脚本安全管理器拒绝 File 访问，所以文件探测必须在这里一次做完。
     * PD 为 null（单测）或路径不可解析时跳过，CacheProbe 保持空集（回退原路径）。
     */
    private static void initCacheProbe(ProtectionDomain protectionDomain) {
        if (protectionDomain == null) return;
        try {
            CodeSource source = protectionDomain.getCodeSource();
            if (source == null || source.getLocation() == null) return;
            Path jar = Path.of(source.getLocation().toURI());
            Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
            if (modRoot == null) return;
            CacheProbe.init(modRoot.toString());
            AgentLog.info("textures: cache probe ready, files=" + CacheProbe.size());
        } catch (Throwable t) {
            AgentLog.fail("textures: cache probe init failed", t);
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
