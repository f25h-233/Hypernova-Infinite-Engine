package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * {@code CacheTool key --verify} 的守卫逻辑。
 *
 * <p>这些用例只测"比对规则"，不测 CLI 输出：{@code CacheTool} 在
 * {@code src/agent/java/hypernova/agent/tools/} 下，而 {@code run-agent-tests.sh}
 * 明确排除 tools 子目录（工具类依赖 Janino），所以被测逻辑都放在
 * {@link KeyManifest} 里，由这里直接断言。
 */
class KeyManifestVerifyTest {
    @TempDir Path tmp;

    @Test
    void headerDriftIsDetectedWhenJavaVersionDiffers() {
        String agentJava = "17.0.10";
        String currentJava = "21.0.10";
        String classpath = "fr.jar";

        assertNotEquals(agentJava, currentJava, "precondition");
        List<String> diff = KeyManifest.headerDiff(agentJava, classpath, currentJava, classpath);
        assertTrue(diff.contains("-java=17.0.10"), "must report the agent side: " + diff);
        assertTrue(diff.contains("+java=21.0.10"), "must report the current side: " + diff);
        assertEquals(2, diff.size(), "classpath is equal, so only java lines differ: " + diff);
    }

    /**
     * 这一条是 F-1 的核心：文件集完全相同（同 path/size/sha256），只有 JVM 身份不同。
     * 修复前 verify 只看文件条目，这种漂移会被判成 match；现在必须有差异输出。
     */
    @Test
    void verifyDetectsHeaderDrift() throws Exception {
        Path game = tmp.resolve("game");
        Path manifestFile = tmp.resolve("cache/key-manifest.json");

        KeyManifest m = KeyManifest.load(manifestFile);
        m.refresh(List.of());
        m.save(manifestFile);

        KeyManifest reloaded = KeyManifest.load(manifestFile);
        assertNotNull(reloaded.jvmJava(), "save must persist the writing JVM's java.version");
        assertNotNull(reloaded.jvmClasspath(), "save must persist the writing JVM's classpath");

        // 同一份清单，换一个 java.version 去看：必须产生差异行。
        String drifted = reloaded.jvmJava().equals("21.0.10") ? "17.0.10" : "21.0.10";
        List<String> diff = KeyManifest.headerDiff(
                reloaded.jvmJava(), reloaded.jvmClasspath(),
                drifted, reloaded.jvmClasspath());
        assertFalse(diff.isEmpty(), "a different java.version must not be treated as a match");
        assertTrue(diff.get(0).startsWith("-java="), "diff must show the agent side first: " + diff);
        assertTrue(diff.get(1).startsWith("+java="), "diff must show the current side: " + diff);

        // 同值时不能有差异（防止守卫恒红）。
        assertTrue(KeyManifest.headerDiff(reloaded.jvmJava(), reloaded.jvmClasspath(),
                reloaded.jvmJava(), reloaded.jvmClasspath()).isEmpty());
        assertTrue(game != null);
    }

    @Test
    void classpathDriftIsDetected() {
        List<String> diff = KeyManifest.headerDiff(
                "17.0.10", "a.jar;b.jar", "17.0.10", "a.jar;c.jar");
        assertEquals(2, diff.size(), "only the classpath pair should differ: " + diff);
        assertEquals("-classpath=a.jar;b.jar", diff.get(0));
        assertEquals("+classpath=a.jar;c.jar", diff.get(1));
    }

    /** 旧清单没有 jvm 字段：diff 必须标 missing，而不是静默判等。 */
    @Test
    void missingJvmIdentityIsReportedAsMissing() {
        List<String> diff = KeyManifest.headerDiff(null, null, "17.0.10", "a.jar");
        assertTrue(diff.contains("-java=<missing>"), diff.toString());
        assertTrue(diff.contains("-classpath=<missing>"), diff.toString());
    }

    @Test
    void scriptClasspathKeepsOnlyGameJarsInOrder() throws Exception {
        Path game = tmp.resolve("game");
        Path core = game.resolve("starsector-core");
        Files.createDirectories(core);
        Path a = core.resolve("a.jar");
        Path b = core.resolve("b.jar");
        Files.writeString(a, "a");
        Files.writeString(b, "b");
        Path outside = tmp.resolve("outside.jar");
        Files.writeString(outside, "x");

        String raw = String.join(java.io.File.pathSeparator,
                outside.toString(), b.toString(), a.toString(), "");
        String filtered = KeyManifest.scriptClasspath(raw, game);
        // 顺序必须保持输入顺序（classpath 有优先级），且只留 gameRoot 下的普通文件。
        assertEquals(b.toString() + java.io.File.pathSeparator + a.toString(), filtered);
    }

    /** R12 起 canonical 是 3 段；R12 之前是 4 段。两种都要能被识别成文件条目行。 */
    @Test
    void fileEntryLineAcceptsBothCanonicalShapes() {
        assertTrue(KeyManifest.isFileEntryLine("D:\\g\\a.jar|10|deadbeef"), "3-segment (R12)");
        assertTrue(KeyManifest.isFileEntryLine("D:\\g\\a.jar|10|1234|deadbeef"), "4-segment (pre-R12)");
        assertFalse(KeyManifest.isFileEntryLine("java=17.0.10"), "header must not look like an entry");
        assertFalse(KeyManifest.isFileEntryLine("classpath=D:\\g\\a.jar"), "classpath line has no size");
        assertFalse(KeyManifest.isFileEntryLine("enabled=a,b"), "enabled line must be skipped");
        assertFalse(KeyManifest.isFileEntryLine(""), "empty line");
    }
}
