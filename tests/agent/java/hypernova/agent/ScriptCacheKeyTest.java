package hypernova.agent;

import org.json.JSONObject;
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

    @Test
    void keyCoversModsWhoseFolderNameIsNotItsId() throws Exception {
        Path game = tmp.resolve("game5");
        Path mods = game.resolve("mods");
        // 文件夹名与 mod_info.json 的 id 不一致（260mods 的真实形态）。
        Path longName = mods.resolve("A Very Long Folder Name");
        Files.createDirectories(longName);
        Files.writeString(longName.resolve("mod_info.json"), "{\"id\":\"short_id\"}");
        // enabledMods 里放的 id 根本匹配不到任何文件夹 —— 旧实现会整个跳过该 mod。
        Path unmatched = mods.resolve("some_dir");
        Files.createDirectories(unmatched.resolve("src/x"));
        Files.writeString(unmatched.resolve("mod_info.json"), "{\"id\":\"other_id\"}");
        Path java = unmatched.resolve("src/x/Unmatched.java");
        Files.writeString(java, "package x; public class Unmatched {}");
        Files.writeString(mods.resolve("enabled_mods.json"),
                "{\"enabledMods\":[\"nonexistent_id_xyz\"]}");
        RuntimeContext ctx = ctx(game, mods);

        Path javaAbs = java.toAbsolutePath().normalize();
        assertTrue(ScriptCacheKey.collectFiles(ctx).contains(javaAbs),
                "every mod folder with mod_info.json must be fingerprinted, regardless of enabledMods ids");

        ScriptCacheKey.Result r1 = ScriptCacheKey.compute(ctx);
        assertEquals(4, r1.fileCount(),
                "expected enabled_mods.json + 2x mod_info.json + the .java from the unmatched folder");

        Files.writeString(java, "package x; public class Unmatched { int y; }");
        Files.setLastModifiedTime(java,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        assertNotEquals(r1.id(), ScriptCacheKey.compute(ctx).id(),
                "editing a mod that enabledMods cannot match must still change the key");
    }

    /**
     * mod_info.json 里的 {@code #} 注释。启动器能加载这种文件（LoadingUtils 先剥注释），
     * 所以我们的剥离实现也必须能解析出 id；同时方案 B 的文件收集本来就收该 mod 的源码，
     * 这里一并验证「解析不再失败」与「源码仍进 key」。
     */
    @Test
    void parsesModInfoWithHashComments() throws Exception {
        Path game = tmp.resolve("game6");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("commented");
        Files.createDirectories(mod.resolve("src/my"));
        // 与 brief 给出的形态逐字一致：制表符缩进、注释行夹在字段中间。
        Files.writeString(mod.resolve("mod_info.json"),
                "{\n"
                        + "\t\"id\": \"my_mod\",\n"
                        + "\t#\"jars\": [\"jars/.jar\"],\n"
                        + "\t\"name\": \"x\"\n"
                        + "}\n");
        Path java = mod.resolve("src/my/Mine.java");
        Files.writeString(java, "package my; public class Mine {}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"my_mod\"]}");
        RuntimeContext ctx = ctx(game, mods);

        // 1) 剥离 + org.json 能解出 id —— 即启动器那条解析路径在本地可复现。
        String raw = Files.readString(mod.resolve("mod_info.json"));
        JSONObject parsed = new JSONObject(ScriptCacheKey.stripComments(raw));
        assertEquals("my_mod", parsed.getString("id"),
                "hash-comment stripping must make the mod_info.json parseable");

        // 2) 该 mod 的 .java 进 key 的文件集。
        assertTrue(ScriptCacheKey.collectFiles(ctx)
                        .contains(java.toAbsolutePath().normalize()),
                "commented mod's sources must still be fingerprinted");

        // 3) 守「# 只在字符串外才开注释」：字符串里的 # 必须原样保留。
        String inString = "{\"author\": \"a # b\", \"id\": \"my_mod\"}";
        assertEquals(inString, ScriptCacheKey.stripComments(inString),
                "# inside a JSON string must not start a comment");
    }

    /**
     * enabledMods 的集合变化必须改变 key（新增一个启用的 mod）。两个 mod 的源码都在
     * 文件清单里、文件集合完全不变，唯一变量就是 canonical 里的 {@code enabled=} 行。
     */
    @Test
    void keyChangesWhenEnabledListChanges() throws Exception {
        Path game = tmp.resolve("game7");
        Path mods = game.resolve("mods");
        for (String id : new String[]{"a", "b"}) {
            Path mod = mods.resolve(id);
            Files.createDirectories(mod.resolve("src/" + id));
            Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"" + id + "\"}");
            Files.writeString(mod.resolve("src/" + id + "/" + id + ".java"),
                    "package " + id + "; public class " + id + " {}");
        }
        Path list = mods.resolve("enabled_mods.json");
        Files.writeString(list, "{\"enabledMods\":[\"a\"]}");
        // 文件清单含每个文件的 mtime，所以「还原 key」必须同时还原内容与 mtime，
        // 否则断言测到的是 mtime 而非 enabled= 行。
        FileTime t1 = Files.getLastModifiedTime(list);
        RuntimeContext ctx = ctx(game, mods);
        ScriptCacheKey.Result r1 = ScriptCacheKey.compute(ctx);
        String key1 = r1.id();
        // key 的变化也可能只来自 enabled_mods.json 的字节哈希，所以这里直接钉 canonical
        // 里的 enabled= 行：没有它，本测试挡不住「删掉 enabled= 行」的变异。
        assertTrue(r1.canonical().contains("\nenabled=a\n"),
                "canonical must carry the sorted enabled set; was:\n" + r1.canonical());

        Files.writeString(list, "{\"enabledMods\":[\"a\",\"b\"]}");
        ScriptCacheKey.Result r2 = ScriptCacheKey.compute(ctx);
        String key2 = r2.id();
        assertNotEquals(key1, key2, "enabling one more mod must change the key");
        assertTrue(r2.canonical().contains("\nenabled=a,b\n"),
                "enabled set in canonical must follow enabledMods; was:\n" + r2.canonical());

        // 反向也要变（不是单调的「只会增」）。
        Files.writeString(list, "{\"enabledMods\":[\"a\"]}");
        Files.setLastModifiedTime(list, t1);
        assertEquals(key1, ScriptCacheKey.compute(ctx).id(),
                "restoring the previous enabled set (and mtime) must restore the key");
    }

    /**
     * mod_info.json 完全无法解析（启动器会跳过该 mod）时，方案 B 仍必须把它的源码
     * 收进指纹——它的 .java 可能被别的 mod 共享，漏掉会让缓存带毒。
     */
    @Test
    void modWithUnparseableInfoStillContributesSources() throws Exception {
        Path game = tmp.resolve("game8");
        Path mods = game.resolve("mods");
        Path bad = mods.resolve("broken");
        Files.createDirectories(bad.resolve("src/x"));
        Files.writeString(bad.resolve("mod_info.json"), "{ this is not json");
        Path java = bad.resolve("src/x/X.java");
        Files.writeString(java, "package x; public class X {}");
        // 一个正常 mod，确保 enabled= 解析路径也走到（坏文件不连累其它 mod）。
        Path good = mods.resolve("good");
        Files.createDirectories(good.resolve("src/y"));
        Files.writeString(good.resolve("mod_info.json"), "{\"id\":\"good\"}");
        Files.writeString(good.resolve("src/y/Y.java"), "package y; public class Y {}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"good\"]}");
        RuntimeContext ctx = ctx(game, mods);

        assertTrue(ScriptCacheKey.collectFiles(ctx).contains(java.toAbsolutePath().normalize()),
                "a mod whose mod_info.json cannot be parsed must still contribute sources");

        // 该源码的修改必须能改变 key（不是「收进来但哈希被跳过」）。
        String k1 = ScriptCacheKey.compute(ctx).id();
        Files.writeString(java, "package x; public class X { int z; }");
        Files.setLastModifiedTime(java,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        assertNotEquals(k1, ScriptCacheKey.compute(ctx).id(),
                "editing an unparseable mod's sources must change the key");
    }

    /**
     * 内容不变、只有 mtime 变，key 必须不变。sha256 已完整覆盖内容；mtime 若进 canonical，
     * 那么 git checkout / 解压 / 备份还原 / 复制粘贴这类「时间变、内容不变」的操作都会让
     * 整份缓存失效，代价是一次完整冷编译。
     */
    @Test
    void keyIgnoresMtimeWhenContentUnchanged() throws Exception {
        Path game = tmp.resolve("game9");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path java = mod.resolve("src/a/A.java");
        Files.writeString(java, "package a; public class A {}");
        RuntimeContext ctx = ctx(game, mods);

        String key1 = ScriptCacheKey.compute(ctx).id();

        // 内容一字不改，只把 mtime 推到 +1 小时。
        Files.setLastModifiedTime(java,
                FileTime.fromMillis(System.currentTimeMillis() + 3_600_000L));
        String key2 = ScriptCacheKey.compute(ctx).id();
        assertEquals(key1, key2, "an mtime-only change must not change the key");
    }

    /**
     * 本 agent 的 jar 每次重建都变，绝不能进指纹；否则每次发版都会让所有用户的
     * 缓存失效、被迫冷启动。这是 m1d S4 冒烟实际踩到的回归（重建诊断版 agent
     * 后 key 从 8a26482e… 变成 2da1735d…，缓存整体 miss）。
     */
    @Test
    void agentJarIsExcludedFromFingerprint() throws Exception {
        Path game = tmp.resolve("gameAjar");
        Path mods = game.resolve("mods");
        Path self = mods.resolve("hypernova_infinite_engine");
        Files.createDirectories(self.resolve("jars"));
        Files.writeString(self.resolve("mod_info.json"), "{\"id\":\"hypernova_infinite_engine\"}");
        Files.writeString(mods.resolve("enabled_mods.json"),
                "{\"enabledMods\":[\"hypernova_infinite_engine\"]}");

        Path agentJar = self.resolve("jars/hypernova.agent.jar");
        Files.write(agentJar, new byte[]{1, 2, 3});
        RuntimeContext ctx = ctx(game, mods);
        String key1 = ScriptCacheKey.compute(ctx).id();

        // 重建 agent：内容变、大小变、mtime 变。
        Files.write(agentJar, new byte[]{9, 9, 9, 9, 9, 9, 9});
        Files.setLastModifiedTime(agentJar,
                FileTime.fromMillis(System.currentTimeMillis() + 60_000L));
        String key2 = ScriptCacheKey.compute(ctx).id();

        assertEquals(key1, key2, "rebuilding hypernova.agent.jar must not invalidate the cache key");
    }

    /**
     * 已知限制：size+mtime 都没变、且 mtime < savedAt 时，缓存会复用旧 sha256。
     * 这是 R5 为了性能接受的窗口；-Dhypernova.rehash=true 必须能强制重算。
     */
    @Test
    void rehashPropertyForcesContentRecheck() throws Exception {
        Path game = tmp.resolve("gameRehash");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path java = mod.resolve("src/a/R.java");
        Files.writeString(java, "package a; public class R {int x;}");
        RuntimeContext ctx = ctx(game, mods);
        String k1 = ScriptCacheKey.compute(ctx).id();

        // 把清单 savedAt 推到未来，让 size+mtime 未变的文件走哈希复用路径。
        Path manifest = ctx.cacheRoot().resolve("key-manifest.json");
        JSONObject root = new JSONObject(Files.readString(manifest));
        root.put("savedAt", System.currentTimeMillis() + 3_600_000L);
        Files.writeString(manifest, root.toString());

        FileTime mtime = Files.getLastModifiedTime(java);
        Files.writeString(java, "package a; public class R {int y;}"); // 同尺寸
        Files.setLastModifiedTime(java, mtime);

        assertEquals(k1, ScriptCacheKey.compute(ctx).id(),
                "same size+mtime must reuse the cached sha256 without the rehash flag");

        System.setProperty("hypernova.rehash", "true");
        try {
            assertNotEquals(k1, ScriptCacheKey.compute(ctx).id(),
                    "-Dhypernova.rehash=true must re-hash every file");
        } finally {
            System.clearProperty("hypernova.rehash");
        }
    }

    /** 无变化时不得重写 3.3 MB 的清单（每次启动都写是纯浪费）。 */
    @Test
    void unchangedInputsDoNotRewriteManifest() throws Exception {
        Path game = tmp.resolve("gameNoWrite");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path java = mod.resolve("src/a/W.java");
        Files.writeString(java, "package a; public class W {}");
        // 把源文件 mtime 固定到过去，保证第一次 compute 的 savedAt 严格大于它。
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(java, past);
        Files.setLastModifiedTime(mod.resolve("mod_info.json"), past);
        Files.setLastModifiedTime(mods.resolve("enabled_mods.json"), past);

        RuntimeContext ctx = ctx(game, mods);
        ScriptCacheKey.compute(ctx);
        Path manifest = ctx.cacheRoot().resolve("key-manifest.json");
        FileTime firstWrite = Files.getLastModifiedTime(manifest);

        Thread.sleep(50);
        ScriptCacheKey.compute(ctx);

        assertEquals(firstWrite, Files.getLastModifiedTime(manifest),
                "a no-op refresh must not rewrite the manifest");
    }

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
