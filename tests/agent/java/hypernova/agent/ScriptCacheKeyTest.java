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

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
