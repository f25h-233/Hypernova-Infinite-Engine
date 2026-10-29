package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;

import static org.junit.jupiter.api.Assertions.*;

class ScriptCacheKeyTest {
    @TempDir Path tmp;

    @Test
    void keyIsStableAndChangesWithSourceAndModList() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path src = mod.resolve("src/a/A.java");
        Files.writeString(src, "package a; public class A {}");
        RuntimeContext ctx = ctx(game, mods);

        String k1 = ScriptCacheKey.compute(ctx).id();
        String k2 = ScriptCacheKey.compute(ctx).id();
        assertEquals(k1, k2, "same inputs must produce the same key");

        Files.writeString(src, "package a; public class A { int x; }");
        Files.setLastModifiedTime(src,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        String k3 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k1, k3, "source change must change the key");

        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        String k4 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k3, k4, "mod list change must change the key");
    }

    @Test
    void keyIncludesModJar() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("bar");
        Files.createDirectories(mod.resolve("jars"));
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"bar\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"bar\"]}");
        Path jar = mod.resolve("jars/bar.jar");
        Files.write(jar, new byte[]{1, 2, 3});
        RuntimeContext ctx = ctx(game, mods);
        String k1 = ScriptCacheKey.compute(ctx).id();

        Files.write(jar, new byte[]{1, 2, 4});
        Files.setLastModifiedTime(jar,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        assertNotEquals(k1, ScriptCacheKey.compute(ctx).id());
    }

    @Test
    void keyChangesWhenEnabledModOrderChanges() throws Exception {
        Path game = tmp.resolve("game3");
        Path mods = game.resolve("mods");
        for (String id : new String[]{"foo", "bar"}) {
            Path mod = mods.resolve(id);
            Files.createDirectories(mod.resolve("src/" + id));
            Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"" + id + "\"}");
            Files.writeString(mod.resolve("src/" + id + "/" + id + ".java"),
                    "package " + id + "; public class " + id + " {}");
        }
        Path list = mods.resolve("enabled_mods.json");
        Files.writeString(list, "{\"enabledMods\":[\"foo\",\"bar\"]}");
        RuntimeContext ctx = ctx(game, mods);

        String k1 = ScriptCacheKey.compute(ctx).id();

        // 集合相同、只有顺序不同：文件集合不变，key 只能靠 enabled_mods.json 自身的哈希变化。
        Files.writeString(list, "{\"enabledMods\":[\"bar\",\"foo\"]}");
        Files.setLastModifiedTime(list,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        String k2 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k1, k2, "enabled_mods order must change the key");
    }

    @Test
    void staleMtimeIsRacyCleanGuarded() throws Exception {
        Path game = tmp.resolve("game4");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path src = mod.resolve("src/a/Racy.java");
        // 未来 mtime：manifest 的 savedAt 必然早于它，模拟「清单写完后才被改」的文件。
        FileTime future = FileTime.fromMillis(System.currentTimeMillis() + 60_000);
        Files.writeString(src, "package a; public class Racy {int x;}");
        Files.setLastModifiedTime(src, future);
        RuntimeContext ctx = ctx(game, mods);
        String k1 = ScriptCacheKey.compute(ctx).id();

        // 同尺寸、不同内容，且 mtime 保持原值（size+mtime 短发会误判为未变）。
        Files.writeString(src, "package a; public class Racy {int y;}");
        Files.setLastModifiedTime(src, future);
        String k2 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k1, k2, "content change with unchanged mtime must not reuse stale sha256");
    }

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
