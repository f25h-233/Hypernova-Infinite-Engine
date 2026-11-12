package hypernova.agent.fonts;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class DynFontHdTest {

    @TempDir
    Path tmp;

    private static final class TestLog implements DynFontHd.Log {
        final List<String> lines = new ArrayList<>();
        final List<Throwable> failures = new ArrayList<>();

        @Override
        public void info(String msg) {
            lines.add(msg);
        }

        @Override
        public void fail(String msg, Throwable t) {
            lines.add(msg);
            failures.add(t);
        }
    }

    private Path core() throws Exception {
        Path core = tmp.resolve("starsector-core");
        Files.createDirectories(core.resolve("graphics/fonts"));
        return core;
    }

    private Path cache(Path core, String name) throws Exception {
        Path cache = core.resolve("graphics/fonts/dyn_font/cache").resolve(name);
        Files.createDirectories(cache);
        Files.writeString(cache.resolve(".complete"), "");
        return cache;
    }

    private static void writeFnt(Path path, int w, int h, String page) throws Exception {
        Files.writeString(path,
                "info face=\"test\" size=15\n"
                        + "common lineHeight=17 base=15 scaleW=" + w
                        + " scaleH=" + h + " pages=1 packed=0\n"
                        + "page id=0 file=\"" + page + "\"\n",
                StandardCharsets.ISO_8859_1);
    }

    /** 只写 pngSize() 会读的头部：签名 + IHDR length/tag + 宽高。 */
    private static void writePng(Path path, int w, int h) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.write(new byte[]{(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'});
        out.writeInt(13);
        out.write(new byte[]{'I', 'H', 'D', 'R'});
        out.writeInt(w);
        out.writeInt(h);
        out.writeByte(8);
        out.writeByte(6);
        out.writeByte(0);
        out.writeByte(0);
        out.writeByte(0);
        out.flush();
        Files.write(path, bytes.toByteArray());
    }

    @Test
    void scansOnlyCompleteMatchingPairs() throws Exception {
        Path core = core();
        Path fonts = core.resolve("graphics/fonts");
        Files.writeString(fonts.resolve("fontA.fnt"), "original-a");
        Files.writeString(fonts.resolve("fontA_0.png"), "original-a-page");
        Files.writeString(fonts.resolve("fontC.fnt"), "original-c");
        Files.writeString(fonts.resolve("fontC_0.png"), "original-c-page");

        Path cache = cache(core, "s1.00-abc");
        writeFnt(cache.resolve("fontA.fnt"), 4096, 512, "fontA_0.png");
        writePng(cache.resolve("fontA_0.png"), 4096, 512);

        // _exact 必须被跳过
        writeFnt(cache.resolve("fontA_exact.fnt"), 262144, 131072, "fontA_exact_0.png");
        writePng(cache.resolve("fontA_exact_0.png"), 262144, 131072);

        // 目标不存在，跳过
        writeFnt(cache.resolve("fontB.fnt"), 4096, 512, "fontB_0.png");
        writePng(cache.resolve("fontB_0.png"), 4096, 512);

        // fnt 与 png 尺寸不一致，跳过
        writeFnt(cache.resolve("fontC.fnt"), 4096, 512, "fontC_0.png");
        writePng(cache.resolve("fontC_0.png"), 2048, 1024);

        List<DynFontHd.Pair> pairs = DynFontHd.scanCache(cache, fonts, new TestLog());
        assertEquals(1, pairs.size());
        assertEquals("fontA.fnt", pairs.get(0).sourceFnt.getFileName().toString());
        assertEquals("fontA_0.png", pairs.get(0).sourcePage.getFileName().toString());
    }

    @Test
    void appliesPairAndCreatesOneTimeBackups() throws Exception {
        Path core = core();
        Path fonts = core.resolve("graphics/fonts");
        Files.writeString(fonts.resolve("fontA.fnt"), "original-a");
        Files.writeString(fonts.resolve("fontA_0.png"), "original-a-page");

        Path cache = cache(core, "s1.00-abc");
        writeFnt(cache.resolve("fontA.fnt"), 4096, 512, "fontA_0.png");
        writePng(cache.resolve("fontA_0.png"), 4096, 512);

        TestLog log = new TestLog();
        List<DynFontHd.Pair> pairs = DynFontHd.scanCache(cache, fonts, log);
        DynFontHd.Counter first = DynFontHd.applyPairs(fonts, pairs, false, log);
        assertEquals(1, first.applied);
        assertEquals(0, first.already);
        assertEquals(0, first.failed);

        assertEquals(Files.readString(cache.resolve("fontA.fnt")),
                Files.readString(fonts.resolve("fontA.fnt")));
        assertArrayEquals(Files.readAllBytes(cache.resolve("fontA_0.png")),
                Files.readAllBytes(fonts.resolve("fontA_0.png")));
        assertEquals("original-a", Files.readString(
                fonts.resolve("fontA.fnt.bak-hypernova-hd")));
        assertEquals("original-a-page", Files.readString(
                fonts.resolve("fontA_0.png.bak-hypernova-hd")));

        // 第二次应识别为 already，且不新增备份/不改备份内容。
        DynFontHd.Counter second = DynFontHd.applyPairs(fonts, pairs, false, log);
        assertEquals(0, second.applied);
        assertEquals(1, second.already);
        assertEquals("original-a", Files.readString(
                fonts.resolve("fontA.fnt.bak-hypernova-hd")));
    }

    @Test
    void dryRunDoesNotWriteAnything() throws Exception {
        Path core = core();
        Path fonts = core.resolve("graphics/fonts");
        Files.writeString(fonts.resolve("fontA.fnt"), "original-a");
        Files.writeString(fonts.resolve("fontA_0.png"), "original-a-page");

        Path cache = cache(core, "s1.00-abc");
        writeFnt(cache.resolve("fontA.fnt"), 4096, 512, "fontA_0.png");
        writePng(cache.resolve("fontA_0.png"), 4096, 512);

        TestLog log = new TestLog();
        List<DynFontHd.Pair> pairs = DynFontHd.scanCache(cache, fonts, log);
        DynFontHd.Counter counter = DynFontHd.applyPairs(fonts, pairs, true, log);
        assertEquals(1, counter.applied);
        assertEquals("original-a", Files.readString(fonts.resolve("fontA.fnt")));
        assertEquals("original-a-page",
                Files.readString(fonts.resolve("fontA_0.png")));
        assertFalse(Files.exists(fonts.resolve("fontA.fnt.bak-hypernova-hd")));
    }

    @Test
    void latestCompleteCacheIgnoresIncompleteAndOldDirectories() throws Exception {
        Path core = core();
        Path root = core.resolve("graphics/fonts/dyn_font/cache");
        Path old = cache(core, "s1.00-old");
        Path incomplete = root.resolve("s2.00-incomplete");
        Files.createDirectories(incomplete);
        Path newest = cache(core, "s1.50-new");

        Files.setLastModifiedTime(old, FileTime.fromMillis(1_000));
        Files.setLastModifiedTime(incomplete, FileTime.fromMillis(3_000));
        Files.setLastModifiedTime(newest, FileTime.fromMillis(2_000));

        assertEquals(newest.getFileName().toString(),
                DynFontHd.latestCompleteCache(root).getFileName().toString());
    }
}
