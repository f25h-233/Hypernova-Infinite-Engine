package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * {@link CacheProbe} 的注册边界：只认 {@code cache/} 下 {@code isFile()} 且
 * {@code length() >= 8} 的文件，查询只按 basename（最后一个 '/' 或 '\' 之后）。
 *
 * <p>8 B 门槛用于过滤 0 B / 截断到只剩文件头的占位文件；它只能廉价地验证
 * “存在且非空”，不能验证内容可解码。内容损坏的 PNG 仍会被注册（见
 * {@code docs/superpowers/plans/2026-10-30-m1b-normal-cache.md} 的约束注记）。
 */
class CacheProbeTest {
    @TempDir Path tmp;

    private static void writeFile(Path path, int bytes) throws Exception {
        Files.createDirectories(path.getParent());
        Files.write(path, new byte[bytes]);
    }

    @Test
    void registersOnlyFilesOfAtLeastEightBytes() throws Exception {
        writeFile(tmp.resolve("cache/a.png"), 8);
        writeFile(tmp.resolve("cache/b.png"), 7);

        CacheProbe.init(tmp.toString());

        assertEquals(1, CacheProbe.size(), "只有 >=8 B 的 a.png 应被注册");
        assertTrue(CacheProbe.has("cache/a.png"));
        assertTrue(CacheProbe.has("cache\\a.png"), "Windows 反斜杠路径必须同样命中");
        assertFalse(CacheProbe.has("cache/b.png"), "7 B 的 b.png 不达门槛");
        assertFalse(CacheProbe.has(null));
        assertFalse(CacheProbe.has(""));
    }

    @Test
    void missingCacheDirYieldsAnEmptyProbe() throws Exception {
        CacheProbe.init(tmp.toString());

        assertEquals(0, CacheProbe.size(), "没有 cache/ 时集合必须为空，而不是保留上一次结果");
        assertFalse(CacheProbe.has("cache/a.png"));
    }

    @Test
    void matchesTheBasenameAfterTheLastSeparator() throws Exception {
        writeFile(tmp.resolve("cache/a.png"), 16);

        CacheProbe.init(tmp.toString());

        assertTrue(CacheProbe.has("a.png"), "没有分隔符时整串就是 basename");
        assertTrue(CacheProbe.has("x/y/z/a.png"), "取最后一个 '/' 之后的 basename");
        assertTrue(CacheProbe.has("x\\y\\a.png"), "取最后一个 '\\' 之后的 basename");
        assertTrue(CacheProbe.has("cache/nested/a.png"),
                "只查 basename，不要求路径真实存在");
        assertFalse(CacheProbe.has("cache/a.png/extra"), "分隔符之后的 extra 不是已注册文件");
    }
}
