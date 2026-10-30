package hypernova.agent;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/**
 * KeyScanner 的语义锚点：它必须与旧的 collectFiles（Files.walk + 逐文件 stat）
 * 找到**完全相同**的文件集合，同时只做一次属性读取。
 */
class KeyScannerTest {
    @TempDir Path tmp;

    @Test
    void scanFindsExactlyTheLegacyFileSet() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");

        Path a = mods.resolve("modA");
        Files.createDirectories(a.resolve("src/x/y"));
        Files.createDirectories(a.resolve("jars/sub"));
        Files.createDirectories(a.resolve("data/scripts/z"));
        Files.writeString(a.resolve("mod_info.json"), "{\"id\":\"a\"}");
        Files.writeString(a.resolve("src/x/A.java"), "class A {}");
        Files.writeString(a.resolve("src/x/y/B.JAVA"), "class B {}");
        Files.writeString(a.resolve("src/x/notes.txt"), "ignore");
        Files.write(a.resolve("jars/a.jar"), new byte[]{1});
        Files.write(a.resolve("jars/sub/nested.jar"), new byte[]{2});
        Files.write(a.resolve("jars/hypernova.agent.jar"), new byte[]{3});
        Files.write(a.resolve("root.jar"), new byte[]{4});
        Files.writeString(a.resolve("data/scripts/z/S.java"), "class S {}");
        // 目录名以 .jar 结尾：旧实现只收普通文件，必须排除。
        Files.createDirectories(a.resolve("dir.jar"));

        // 没有 mod_info.json 的目录：整棵跳过。
        Path b = mods.resolve("modB");
        Files.createDirectories(b.resolve("src"));
        Files.writeString(b.resolve("src/No.java"), "class No {}");

        // 与 mods/ 同级的副本目录：不在扫描范围内。
        Path sibling = game.resolve("mods - copy/m");
        Files.createDirectories(sibling.resolve("src"));
        Files.writeString(sibling.resolve("mod_info.json"), "{}");
        Files.writeString(sibling.resolve("src/Copy.java"), "class Copy {}");

        Files.createDirectories(game.resolve("starsector-core/data/scripts/core"));
        Files.writeString(game.resolve("starsector-core/data/scripts/core/Core.java"),
                "class Core {}");
        Files.write(game.resolve("starsector-core/fr.agent.jar"), new byte[]{5});
        Files.write(game.resolve("starsector-core/fr.jar"), new byte[]{6});
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");

        RuntimeContext ctx = ctx(game, mods);
        Set<String> legacy = legacyCollect(ctx);
        Set<String> scanned = paths(KeyScanner.scan(ctx));

        assertEquals(legacy, scanned, "new scanner must reproduce the legacy file set exactly");
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("hypernova.agent.jar")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("dir.jar")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("No.java")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("Copy.java")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("notes.txt")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("B.JAVA")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("nested.jar")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("root.jar")));
    }

    @Test
    void scanCarriesSizeAndMtime() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m\"}");
        Path f = mod.resolve("src/F.java");
        Files.writeString(f, "class F {}");
        long mtime = 1_700_000_000_123L;
        Files.setLastModifiedTime(f, FileTime.fromMillis(mtime));
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");

        KeyScanner.FileInfo info = KeyScanner.scan(ctx(game, mods)).stream()
                .filter(i -> i.path().equals(f.toAbsolutePath().normalize()))
                .findFirst().orElseThrow();

        assertEquals(Files.size(f), info.size());
        assertEquals(mtime, info.mtimeMillis());
    }

    @Test
    void parallelAndSerialProduceSameSet() throws Exception {
        Path game = tmp.resolve("game3");
        Path mods = game.resolve("mods");
        for (int m = 0; m < 12; m++) {
            Path mod = mods.resolve("m" + m);
            Files.createDirectories(mod.resolve("src/a"));
            Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m" + m + "\"}");
            Files.writeString(mod.resolve("src/a/C" + m + ".java"), "class C" + m + " {}");
        }
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        RuntimeContext ctx = ctx(game, mods);

        String old = System.getProperty("hypernova.keyThreads");
        try {
            System.setProperty("hypernova.keyThreads", "1");
            Set<String> serial = paths(KeyScanner.scan(ctx));
            System.setProperty("hypernova.keyThreads", "4");
            Set<String> parallel = paths(KeyScanner.scan(ctx));
            assertEquals(serial, parallel, "parallel scan must not add or drop files");
        } finally {
            if (old == null) System.clearProperty("hypernova.keyThreads");
            else System.setProperty("hypernova.keyThreads", old);
        }
    }

    @Test
    void symlinkToFileFollowsLegacySemantics() throws Exception {
        Path game = tmp.resolve("game4");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m\"}");
        Path target = mod.resolve("src/Real.java");
        Files.writeString(target, "class Real {}");
        Path link = mod.resolve("src/Link.java");
        try {
            Files.createSymbolicLink(link, target);
        } catch (IOException | UnsupportedOperationException e) {
            Assumptions.assumeTrue(false, "symlinks unsupported here: " + e);
        }
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        RuntimeContext ctx = ctx(game, mods);

        Set<String> legacy = legacyCollect(ctx);
        Set<String> scanned = paths(KeyScanner.scan(ctx));
        assertEquals(legacy, scanned,
                "a symlink to a regular file was fingerprinted by the legacy walk; keep it");
    }

    private Set<String> paths(java.util.List<KeyScanner.FileInfo> files) {
        Set<String> out = new TreeSet<>();
        for (KeyScanner.FileInfo f : files) out.add(f.path().toString());
        return out;
    }

    /** 旧 collectFiles 的逐字复刻，仅作为测试预言机；生产已不再走这条路径。 */
    private Set<String> legacyCollect(RuntimeContext ctx) throws IOException {
        Set<Path> files = new TreeSet<>();
        Path mods = ctx.modsRoot();
        if (Files.isDirectory(mods)) {
            try (DirectoryStream<Path> ds = Files.newDirectoryStream(mods)) {
                for (Path dir : ds) {
                    if (!Files.isDirectory(dir)) continue;
                    if (!Files.isRegularFile(dir.resolve("mod_info.json"))) continue;
                    legacyTree(dir.resolve("src"), files);
                    legacyTree(dir.resolve("jars"), files);
                    legacyTree(dir.resolve("data/scripts"), files);
                    legacyFile(dir.resolve("mod_info.json"), files);
                    try (DirectoryStream<Path> jars = Files.newDirectoryStream(dir)) {
                        for (Path p : jars) {
                            if (p.getFileName().toString().toLowerCase(Locale.ROOT)
                                    .endsWith(".jar")) {
                                legacyFile(p, files);
                            }
                        }
                    }
                }
            }
        }
        legacyFile(mods.resolve("enabled_mods.json"), files);
        legacyTree(ctx.gameRoot().resolve("starsector-core/data/scripts"), files);
        legacyFile(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"), files);
        legacyFile(ctx.gameRoot().resolve("starsector-core/fr.jar"), files);
        for (String cp : ScriptCacheKey.classpathOrder(ctx)) legacyFile(Path.of(cp), files);

        Set<String> out = new TreeSet<>();
        for (Path p : files) out.add(p.toString());
        return out;
    }

    private void legacyTree(Path root, Set<Path> out) throws IOException {
        if (!Files.isDirectory(root)) return;
        try (Stream<Path> s = Files.walk(root)) {
            for (java.util.Iterator<Path> it = s.iterator(); it.hasNext(); ) {
                Path p = it.next();
                if (!Files.isRegularFile(p)) continue;
                String n = p.getFileName().toString().toLowerCase(Locale.ROOT);
                if (n.endsWith(".java") || n.endsWith(".jar") || n.equals("mod_info.json")) {
                    legacyFile(p, out);
                }
            }
        }
    }

    private void legacyFile(Path p, Set<Path> out) {
        if (p == null || !Files.isRegularFile(p)) return;
        if (p.getFileName().toString().equals("hypernova.agent.jar")) return;
        out.add(p.toAbsolutePath().normalize());
    }

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
