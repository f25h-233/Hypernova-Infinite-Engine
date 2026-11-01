package hypernova.agent;

import com.fs.util.FileLoader;
import com.fs.util.ObfuscatedLocation;
import com.genir.renderer.overrides.loading.FileLoaderFast;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class FileIndexHookTest {

    @TempDir
    Path tmp;

    private RuntimeContext ctx;

    @BeforeEach
    void setUp() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");
        Path saves = game.resolve("saves");
        Path mod = mods.resolve("mod1");
        Files.createDirectories(mod.resolve("graphics"));
        Files.createDirectories(game.resolve("starsector-core"));
        Files.writeString(game.resolve("starsector-core/fr.version.txt"), "v0.9.7rc2");
        Files.writeString(mod.resolve("graphics/a.png"), "a");
        Files.writeString(mod.resolve("data.json"), "{}");
        ctx = new RuntimeContext(
                game, mods, saves,
                saves.resolve("hypernova/scripts-cache"),
                saves.resolve("hypernova/scripts-agent.log"),
                saves.resolve("hypernova/scripts-telemetry.jsonl"),
                new ScriptCacheConfig(true, 1L << 20, 1, 1000, false));
        System.clearProperty("hypernova.fileIndex");
        FileIndexHook.resetForTest();
        FileIndexHook.setContext(ctx);
    }

    @Test
    void buildsThenLoadsFromIndex() throws Exception {
        Object loc = location(tmp.resolve("game/mods/mod1"));
        FileLoaderFast first = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        int built = first.crawlAndSave();
        assertTrue(built > 0, "fixture crawl must find files");

        FileLoaderFast second = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        int loaded = FileIndexHook.tryLoad(crawlerOf(second));
        assertTrue(loaded > 0, "index must produce a hit");
        assertEquals(mapOf(first).keySet(), mapOf(second).keySet(),
                "index must replay every cached file key");
        assertEquals(loaded, FileIndexHook.lastLoadedForTest());
    }

    @Test
    void changedDirectoryFallsBackWithoutPollutingMap() throws Exception {
        Object loc = location(tmp.resolve("game/mods/mod1"));
        FileLoaderFast first = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        int built = first.crawlAndSave();

        Files.writeString(tmp.resolve("game/mods/mod1/graphics/new.png"), "new");
        Thread.sleep(20);

        FileLoaderFast second = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(second)),
                "changed directory must invalidate the index");
        assertTrue(mapOf(second).isEmpty(), "failed load must not leave partial entries");
        assertTrue(crawl(second) > built, "full crawl must see the new file");
    }

    @Test
    void corruptIndexFallsBack() throws Exception {
        Files.createDirectories(ctx.cacheRoot().getParent());
        Files.write(ctx.cacheRoot().getParent().resolve("file-index.idx.gz"), new byte[]{1, 2, 3});
        Object loc = location(tmp.resolve("game/mods/mod1"));
        FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(fast)));
        assertTrue(crawl(fast) > 0);
    }

    @Test
    void systemPropertyDisablesTheLever() throws Exception {
        System.setProperty("hypernova.fileIndex", "false");
        try {
            Object loc = location(tmp.resolve("game/mods/mod1"));
            FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
            assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(fast)));
            assertTrue(crawl(fast) > 0);
        } finally {
            System.clearProperty("hypernova.fileIndex");
        }
    }

    @Test
    void volatileRootsAreRescannedOnEveryHit() throws Exception {
        String oldDir = System.getProperty("user.dir");
        String oldSaves = System.getProperty("com.fs.starfarer.settings.paths.saves");
        String oldMods = System.getProperty("com.fs.starfarer.settings.paths.mods");
        try {
            Path game = tmp.resolve("game2");
            Path core = game.resolve("starsector-core");
            Path saves = game.resolve("saves");
            Path mods = game.resolve("mods");
            Path mod = mods.resolve("mod1");
            Files.createDirectories(core.resolve("graphics"));
            Files.writeString(core.resolve("graphics/core.png"), "core");
            Files.writeString(core.resolve("fr.version.txt"), "v0.9.7rc2");
            Files.createDirectories(saves);
            Files.writeString(saves.resolve("old.sav"), "old");
            Files.createDirectories(mod.resolve("graphics"));
            Files.writeString(mod.resolve("graphics/a.png"), "a");
            Files.writeString(mods.resolve("enabled_mods.json"), "{}");
            System.setProperty("user.dir", core.toString());
            System.setProperty("com.fs.starfarer.settings.paths.saves", "../saves");
            System.setProperty("com.fs.starfarer.settings.paths.mods", "../mods");

            RuntimeContext ctx2 = new RuntimeContext(
                    game, mods, saves,
                    saves.resolve("hypernova/scripts-cache"),
                    saves.resolve("hypernova/scripts-agent.log"),
                    saves.resolve("hypernova/scripts-telemetry.jsonl"),
                    new ScriptCacheConfig(true, 1L << 20, 1, 1000, false));
            FileIndexHook.resetForTest();
            FileIndexHook.setContext(ctx2);

            Object abs = new FileLoader.ResourceLocation(
                    FileLoader.Type.ABSOLUTE_AND_CWD, core.toString(), false);
            Object dir = new FileLoader.ResourceLocation(
                    FileLoader.Type.DIRECTORY, mod.toString(), true);
            List<FileLoader.ResourceLocation> locs =
                    List.of((FileLoader.ResourceLocation) abs,
                            (FileLoader.ResourceLocation) dir);
            FileLoaderFast first = new FileLoaderFast(locs);
            int built = first.crawlAndSave();
            assertTrue(built > 0);

            Files.writeString(saves.resolve("new.sav"), "new");
            Thread.sleep(20);

            FileLoaderFast second = new FileLoaderFast(locs);
            int loaded = FileIndexHook.tryLoad(crawlerOf(second));
            assertTrue(loaded > 0, "cache hit must still enumerate the volatile roots");
            assertTrue(mapOf(second).keySet().stream().anyMatch(k -> k.endsWith("new.sav")),
                    "new save must be visible on a cache hit");
            assertTrue(mapOf(second).keySet().contains("../saves/new.sav"),
                    "FR keeps '..' in volatile-root keys (no path normalization)");
        } finally {
            if (oldDir == null) System.clearProperty("user.dir");
            else System.setProperty("user.dir", oldDir);
            if (oldSaves == null) System.clearProperty("com.fs.starfarer.settings.paths.saves");
            else System.setProperty("com.fs.starfarer.settings.paths.saves", oldSaves);
            if (oldMods == null) System.clearProperty("com.fs.starfarer.settings.paths.mods");
            else System.setProperty("com.fs.starfarer.settings.paths.mods", oldMods);
        }
    }

    @Test
    void shapeResolutionHandlesRenamedFields() {
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(List.of(
                new ObfuscatedLocation(ObfuscatedLocation.Kind.DIRECTORY, "/tmp/x", true)));
        assertEquals(List.of(new FileIndex.Location("DIRECTORY", "/tmp/x", true)), keys);
    }

    @Test
    void nullPathIsCanonicalized() {
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(List.of(
                new FileLoader.ResourceLocation(
                        FileLoader.Type.ABSOLUTE_AND_CWD, null, false)));
        assertEquals(List.of(new FileIndex.Location("ABSOLUTE_AND_CWD", "", false)), keys);
    }

    @Test
    void excludedDirectoryIsSkipped() {
        assertTrue(FileIndexHook.isExcludedForTest("DIRECTORY", "../starfarer.res/res"));
        assertTrue(FileIndexHook.isExcludedForTest("CLASSPATH", ""));
        assertFalse(FileIndexHook.isExcludedForTest("DIRECTORY", "mods/mod1"));
    }

    @Test
    void nullPathAndExcludedLocationsAreHandledEndToEnd() throws Exception {
        String oldDir = System.getProperty("user.dir");
        String oldSaves = System.getProperty("com.fs.starfarer.settings.paths.saves");
        String oldMods = System.getProperty("com.fs.starfarer.settings.paths.mods");
        try {
            Path game = tmp.resolve("game3");
            Path core = game.resolve("starsector-core");
            Path saves = game.resolve("saves");
            Path mods = game.resolve("mods");
            Path mod = mods.resolve("mod1");
            Path excluded = game.resolve("starfarer.res/res");
            Files.createDirectories(core);
            Files.writeString(core.resolve("core.dat"), "core");
            Files.writeString(core.resolve("fr.version.txt"), "v0.9.7rc2");
            Files.createDirectories(saves);
            Files.createDirectories(mod);
            Files.writeString(mod.resolve("a.png"), "a");
            Files.createDirectories(excluded);
            Files.writeString(excluded.resolve("excluded.dat"), "x");
            Files.writeString(mods.resolve("enabled_mods.json"), "{}");
            System.setProperty("user.dir", core.toString());
            System.setProperty("com.fs.starfarer.settings.paths.saves", "../saves");
            System.setProperty("com.fs.starfarer.settings.paths.mods", "../mods");

            RuntimeContext ctx3 = new RuntimeContext(
                    game, mods, saves,
                    saves.resolve("hypernova/scripts-cache"),
                    saves.resolve("hypernova/scripts-agent.log"),
                    saves.resolve("hypernova/scripts-telemetry.jsonl"),
                    new ScriptCacheConfig(true, 1L << 20, 1, 1000, false));
            FileIndexHook.resetForTest();
            FileIndexHook.setContext(ctx3);

            Object abs = new FileLoader.ResourceLocation(
                    FileLoader.Type.ABSOLUTE_AND_CWD, null, false);
            Object dir = new FileLoader.ResourceLocation(
                    FileLoader.Type.DIRECTORY, mod.toString(), true);
            Object excludedLoc = new FileLoader.ResourceLocation(
                    FileLoader.Type.DIRECTORY, "../starfarer.res/res", false);
            List<FileLoader.ResourceLocation> locs = List.of(
                    (FileLoader.ResourceLocation) abs,
                    (FileLoader.ResourceLocation) dir,
                    (FileLoader.ResourceLocation) excludedLoc);

            FileLoaderFast first = new FileLoaderFast(locs);
            assertTrue(first.crawlAndSave() > 0);

            FileLoaderFast second = new FileLoaderFast(locs);
            int loaded = FileIndexHook.tryLoad(crawlerOf(second));
            assertTrue(loaded > 0, "null-path ABSOLUTE location must not abort the index");
            assertTrue(mapOf(second).keySet().stream().anyMatch(k -> k.endsWith("a.png")));
            assertTrue(mapOf(second).keySet().stream().noneMatch(k -> k.contains("excluded.dat")),
                    "excluded ../starfarer.res/res must be skipped on a cache hit");
        } finally {
            if (oldDir == null) System.clearProperty("user.dir");
            else System.setProperty("user.dir", oldDir);
            if (oldSaves == null) System.clearProperty("com.fs.starfarer.settings.paths.saves");
            else System.setProperty("com.fs.starfarer.settings.paths.saves", oldSaves);
            if (oldMods == null) System.clearProperty("com.fs.starfarer.settings.paths.mods");
            else System.setProperty("com.fs.starfarer.settings.paths.mods", oldMods);
        }
    }

    @Test
    void emptyLeafDirectoryInvalidatesWhenAFileAppears() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Path empty = mod.resolve("graphics/empty");
        Files.createDirectories(empty);
        Object loc = location(mod);
        FileLoaderFast first = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertTrue(first.crawlAndSave() > 0);
        Path indexFile = ctx.cacheRoot().getParent().resolve("file-index.idx.gz");
        assertTrue(Files.isRegularFile(indexFile), "first crawl must persist an index");

        Files.writeString(empty.resolve("new.png"), "new");
        Thread.sleep(20);
        empty.toFile().setLastModified(System.currentTimeMillis());

        FileLoaderFast second = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(second)),
                "a directory that was empty at build time must invalidate the index");
        assertTrue(mapOf(second).isEmpty(), "failed load must not leave partial entries");
        assertTrue(crawl(second) > 0, "full crawl must see the new file");
    }

    @Test
    void captureDirsRejectsChangedAndMissingDirectories() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Files.createDirectories(mod);
        long stableCrawlEnd = System.currentTimeMillis() + 5_000;
        List<FileIndex.Dir> ok = FileIndexHook.captureDirs(Set.of(mod.toString()), stableCrawlEnd);
        assertNotNull(ok);
        assertEquals(1, ok.size());
        long exact = mod.toFile().lastModified();
        assertNotNull(FileIndexHook.captureDirs(Set.of(mod.toString()), exact),
                "an mtime exactly equal to the crawl end must be accepted");
        assertNull(FileIndexHook.captureDirs(Set.of(mod.toString()), 0L),
                "a directory modified after the crawl must abort the save");
        assertNull(FileIndexHook.captureDirs(
                Set.of(tmp.resolve("game/mods/never-existed").toString()), stableCrawlEnd),
                "a missing directory must abort the save");
    }

    @Test
    void writeIndexSkipsWhenTheDirectorySetChangedAfterTheCrawl() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Object loc = location(mod);
        FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        Object crawler = crawlerOf(fast);
        cacheLocations(crawler);
        Object outer = field(crawler, "this$0");
        @SuppressWarnings("unchecked")
        List<Object> locations = (List<Object>) field(outer, "allLocations");
        @SuppressWarnings("unchecked")
        List<Object> collector = (List<Object>) field(crawler, "collector");
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(locations);
        Path target = tmp.resolve("idx.gz");
        assertFalse(FileIndexHook.writeIndex("0.9.7rc2", "stamp", keys,
                locations.toArray(), collector.toArray(), target, 0L));
        assertFalse(Files.exists(target), "aborted save must not write the final file");
    }

    @Test
    void writeIndexPersistsAReadableIndexWhenDirectoriesAreStable() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Object loc = location(mod);
        FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        Object crawler = crawlerOf(fast);
        cacheLocations(crawler);
        Object outer = field(crawler, "this$0");
        @SuppressWarnings("unchecked")
        List<Object> locations = (List<Object>) field(outer, "allLocations");
        @SuppressWarnings("unchecked")
        List<Object> collector = (List<Object>) field(crawler, "collector");
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(locations);
        Path target = tmp.resolve("idx.gz");
        assertTrue(FileIndexHook.writeIndex("0.9.7rc2", "stamp", keys,
                locations.toArray(), collector.toArray(), target,
                System.currentTimeMillis() + 5_000));
        FileIndex index = FileIndex.read(target, "0.9.7rc2", "stamp");
        assertNotNull(index, "written index must be readable with the same stamps");
        assertNull(index.firstMismatchedDir(), "recorded mtimes must match the directories");
        assertEquals(keys, index.locations());
        assertFalse(index.entries().isEmpty());
    }

    private static Object field(Object target, String name) throws Exception {
        Field f = target.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(target);
    }

    @Test
    void supportedFrVersionsArePinned() {
        assertTrue(FileIndexHook.supportedFrVersion("0.9.7rc2"));
        assertTrue(FileIndexHook.supportedFrVersion("v0.9.7rc2"));
        assertTrue(FileIndexHook.supportedFrVersion("V0.9.7RC2"));
        assertTrue(FileIndexHook.supportedFrVersion("0.9.7"));
        assertTrue(FileIndexHook.supportedFrVersion("v0.9.7"));
        // fr.version.txt is read with its trailing newline; lazy textures reuse
        // the same pinned gate, so the normalization must survive it.
        assertTrue(FileIndexHook.supportedFrVersion(" 0.9.7rc2\n"));
        assertFalse(FileIndexHook.supportedFrVersion("0.9.5"));
        assertFalse(FileIndexHook.supportedFrVersion("0.9.6"));
        assertFalse(FileIndexHook.supportedFrVersion("0.9.8"));
        assertFalse(FileIndexHook.supportedFrVersion("unknown"));
        assertFalse(FileIndexHook.supportedFrVersion(""));
        assertFalse(FileIndexHook.supportedFrVersion(null));
    }

    @Test
    void unsupportedFrVersionRejectsIndexAndFallsBack() throws Exception {
        Object loc = location(tmp.resolve("game/mods/mod1"));
        FileLoaderFast first = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertTrue(first.crawlAndSave() > 0);

        Files.writeString(
                ctx.gameRoot().resolve("starsector-core/fr.version.txt"), "v0.9.5");

        FileLoaderFast second = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(second)),
                "index built under 0.9.7rc2 must not replay under another FR version");
        assertTrue(mapOf(second).isEmpty(), "rejected index must not pollute cachedFiles");
        assertTrue(crawl(second) > 0, "FR's own crawl must still run");
    }

    private static Object location(Path path) {
        return new FileLoader.ResourceLocation(FileLoader.Type.DIRECTORY, path.toString(), true);
    }

    private static Object crawlerOf(FileLoaderFast fast) throws Exception {
        Class<?> inner = Class.forName(
                "com.genir.renderer.overrides.loading.FileLoaderFast$DirectoryCrawler");
        Constructor<?> ctor = inner.getDeclaredConstructor(FileLoaderFast.class);
        ctor.setAccessible(true);
        return ctor.newInstance(fast);
    }

    private static int crawl(FileLoaderFast fast) throws Exception {
        return cacheLocations(crawlerOf(fast));
    }

    private static int cacheLocations(Object crawler) throws Exception {
        Method m = crawler.getClass().getDeclaredMethod("cacheLocations");
        m.setAccessible(true);
        return (Integer) m.invoke(crawler);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, List<Object>> mapOf(FileLoaderFast fast) throws Exception {
        Field f = FileLoaderFast.class.getDeclaredField("cachedFiles");
        f.setAccessible(true);
        return (Map<String, List<Object>>) f.get(fast);
    }
}
