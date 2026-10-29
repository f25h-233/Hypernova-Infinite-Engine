package hypernova.agent.tools;

import hypernova.agent.CachePack;
import hypernova.agent.CacheStore;
import hypernova.agent.KeyManifest;
import hypernova.agent.RuntimeContext;
import hypernova.agent.ScriptCacheKey;
import org.codehaus.janino.JavaSourceClassLoader;
import org.codehaus.janino.util.resource.DirectoryResourceFinder;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;

public final class CacheTool {
    private CacheTool() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            return;
        }
        switch (args[0]) {
            case "key" -> key(args);
            case "inspect" -> inspect(args);
            case "seed" -> seed(args);
            default -> usage();
        }
    }

    private static void key(String[] args) {
        boolean verify = false, deep = false;
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--verify" -> verify = true;
                case "--deep" -> deep = true;
                default -> throw new IllegalArgumentException("unknown: " + args[i]);
            }
        }
        if (deep && !verify) {
            throw new IllegalArgumentException("--deep only makes sense with --verify");
        }
        RuntimeContext ctx = RuntimeContext.fromEnvironment();
        if (verify) {
            verify(ctx, deep);
            return;
        }
        ScriptCacheKey.Result r = computeKeepingManifest(ctx);
        System.out.println(r.id());
        System.out.println("files=" + r.fileCount() + " bytes=" + r.bytes()
                + " elapsed_ms=" + r.elapsedMillis());
        System.out.println("cache_root=" + ctx.cacheRoot());
    }

    /**
     * 对比 agent 上一次写下的 {@code key-manifest.json} 与当前环境算出的文件集，
     * 用来机械验证「工具算出的 key == agent 算出的 key」。
     *
     * <p>三层证据，缺一不可：
     * <ol>
     *   <li><b>文件条目</b>：逐条比对 {@code path -> "size|sha256"}（R12 起 canonical
     *       不再含 mtime）。数量与字节相同但内容不同时 key 必然不同。</li>
     *   <li><b>JVM 身份</b>：manifest 里记着写它那个进程的 {@code java.version} 与原始
     *       {@code java.class.path}，用与生产同一套规则还原成 canonical 的
     *       {@code classpath=} 行再比。这两者任一不同，key 就不同而文件集可以完全一样，
     *       所以只比文件条目会给出假绿（reviewer 用系统 Java 21 实测过）。旧清单没记
     *       这两项时输出 {@code n/a}，**不当作通过**——"没记录"和"一致"是两回事。</li>
     *   <li><b>agent 记录的 key</b>：{@code scripts-telemetry.jsonl} 里 agent 自己写下的
     *       最近一个 {@code key} 字段。这是 agent 侧最直接的证据，覆盖 canonical 全部输入。
     *       遥测不存在（游戏还没跑过）时输出 {@code (none)}，不参与判定。</li>
     * </ol>
     *
     * <p>{@code enabled=} 行不需要单独比：它由 {@code enabled_mods.json} 的字节 sha256
     * 完全决定，而该文件就在条目里。将来若 canonical 新增别的头字段，这里要跟着补。
     *
     * <p><b>--deep 的局限与作用</b>：{@code KeyManifest.refresh} 在 size+mtime 未变时
     * 会复用清单里的旧 sha256，所以第 1 层的 sha 链本身来自 agent 的清单，对"内容变了
     * 但 size+mtime 恰好没变"是循环论证。{@code --deep} 绕过清单，对每个文件独立重算
     * sha256 再比；代价是 12k 文件约 7–11 s（见进度表 R5）。
     *
     * <p>注意 {@link ScriptCacheKey#compute} 会重写 manifest；本子命令比较完会把
     * agent 原来的 manifest 原样写回（原本不存在则删除），保证 verify 只读、
     * 重复运行不会自己覆盖掉待比较的证据。
     */
    private static void verify(RuntimeContext ctx, boolean deep) {
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        byte[] original = readOrNull(manifestFile);
        Snapshot agent = Snapshot.parse(original);

        ScriptCacheKey.Result r = computeKeepingManifest(ctx);

        Map<String, String> current = parseCanonical(r.canonical());
        boolean entriesMatch = agent.present && agent.files == r.fileCount()
                && agent.bytes == r.bytes() && agent.entries.equals(current);

        String currentJava = System.getProperty("java.version", "");
        String currentClasspath = KeyManifest.scriptClasspath(
                System.getProperty("java.class.path", ""), ctx.gameRoot());
        boolean haveJvm = agent.jvmJava != null && agent.jvmClasspath != null;
        // 清单里存的是 agent 当次的**原始** java.class.path（可能含 ../mods/... 这类相对
        // 路径）。这里用当前 cwd 再过滤一次，问的是"agent 那条 classpath 若在当前环境解析，
        // 是否得到与工具相同的 canonical classpath 行"。两边都以 starsector-core 为 cwd
        // 运行时这是精确判等。
        String agentClasspath = haveJvm
                ? KeyManifest.scriptClasspath(agent.jvmClasspath, ctx.gameRoot()) : null;
        Boolean jvmMatch = haveJvm
                ? agent.jvmJava.equals(currentJava) && agentClasspath.equals(currentClasspath)
                : null;

        String agentKey = lastAgentKey(ctx.telemetryFile());
        Boolean keyMatch = agentKey == null ? null : agentKey.equals(r.id());

        System.out.println("agent_manifest: files=" + agent.files + " bytes=" + agent.bytes);
        System.out.println("current      : files=" + r.fileCount() + " bytes=" + r.bytes());
        if (jvmMatch == null) {
            System.out.println("jvm_match    : n/a (manifest has no jvm identity)");
        } else {
            System.out.println("jvm_match    : " + jvmMatch);
        }
        System.out.println("agent_key    : " + (agentKey == null ? "(none)" : agentKey));
        System.out.println("current_key  : " + r.id());
        if (keyMatch != null) System.out.println("agent_key_match: " + keyMatch);
        boolean match = entriesMatch && !Boolean.FALSE.equals(jvmMatch)
                && !Boolean.FALSE.equals(keyMatch);
        System.out.println("match: " + match);
        boolean ok = match;
        if (deep) {
            int bad = deepCompare(agent.entries);
            System.out.println("deep_sha_mismatch: " + bad);
            if (bad != 0) ok = false;
        }
        if (!ok) {
            if (!agent.present) {
                System.err.println("key-manifest.json missing or unreadable: " + manifestFile);
            }
            if (Boolean.FALSE.equals(jvmMatch)) {
                printHeaderDiff(agent.jvmJava, agentClasspath, currentJava, currentClasspath);
            }
            System.exit(1);
        }
    }

    /** JVM 身份不一致时把两边打印出来；classpath 太长，只截前 200 字符。 */
    private static void printHeaderDiff(String agentJava, String agentClasspath,
                                        String currentJava, String currentClasspath) {
        System.err.println("jvm drift (agent vs current):");
        for (String line : KeyManifest.headerDiff(agentJava, agentClasspath,
                currentJava, currentClasspath)) {
            System.err.println("  " + abbrev(line));
        }
    }

    private static String abbrev(String line) {
        String[] f = line.split("=", 2);
        // 差异行带 "-classpath=" / "+classpath=" 前缀，所以用 endsWith 而不是 equals。
        if (f.length == 2 && f[0].endsWith("classpath") && f[1].length() > 200) {
            return f[0] + "=" + f[1].substring(0, 200) + "...";
        }
        return line;
    }

    /**
     * 遥测里 agent 自己写下的最近一个 key（{@code preload} / {@code preload-miss} /
     * {@code summary} 都带）。没有遥测文件或没有这类事件时返回 {@code null}。
     *
     * <p>用完整 key 而不是只比头，是因为它直接覆盖 canonical 的**全部**输入；
     * 但 agent 侧要把头写进 manifest 需要在 {@code ScriptCacheKey} 里加一行
     * （本轮禁止改该文件），所以先以遥测作为 agent 证据来源。
     */
    static String lastAgentKey(Path telemetry) {
        if (telemetry == null || !Files.isRegularFile(telemetry)) return null;
        String last = null;
        try {
            for (String line : Files.readAllLines(telemetry, StandardCharsets.UTF_8)) {
                String trimmed = line.trim();
                if (trimmed.isEmpty()) continue;
                try {
                    JSONObject o = new JSONObject(trimmed);
                    String kind = o.optString("kind", "");
                    String key = o.optString("key", "");
                    if ((kind.equals("preload") || kind.equals("preload-miss")
                            || kind.equals("summary")) && isKey(key)) {
                        last = key;
                    }
                } catch (JSONException ignored) {
                    // 半截/损坏的遥测行跳过，不影响其余证据
                }
            }
        } catch (IOException e) {
            return null;
        }
        return last;
    }

    private static boolean isKey(String s) {
        if (s == null || s.length() != 32) return false;
        for (int i = 0; i < s.length(); i++) {
            if (Character.digit(s.charAt(i), 16) < 0) return false;
        }
        return true;
    }

    /**
     * 对清单里的每个文件独立重算 sha256（不经过 KeyManifest 的复用逻辑），
     * 返回不一致条数。sha256 取条目值的**最后一段**，这样 R12 前后两种格式
     * （{@code size|mtime|sha} 与 {@code size|sha}）都能解析。
     */
    private static int deepCompare(Map<String, String> expected) {
        int bad = 0;
        for (Map.Entry<String, String> e : expected.entrySet()) {
            String value = e.getValue();
            int bar = value.lastIndexOf('|');
            String want = bar < 0 ? null : value.substring(bar + 1);
            String actual = sha256(Path.of(e.getKey()));
            if (want == null || actual == null || !actual.equals(want)) {
                bad++;
            }
        }
        return bad;
    }

    private static String sha256(Path p) {
        try (var in = Files.newInputStream(p)) {
            var md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            return java.util.HexFormat.of().formatHex(md.digest());
        } catch (Exception e) {
            return null;
        }
    }

    private static void inspect(String[] args) {
        RuntimeContext ctx = RuntimeContext.fromEnvironment();
        String key = args.length > 1 ? args[1] : computeKeepingManifest(ctx).id();
        CachePack.Pack p = new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                ctx.config().cacheMaxBytes()).load(key);
        if (p == null) {
            System.out.println("no pack for key=" + key);
            return;
        }
        System.out.println("key=" + key + " entries=" + p.entries().size()
                + " bytes=" + p.bytes());
        p.entries().keySet().stream().sorted().limit(20)
                .forEach(k -> System.out.println("  " + k));
    }

    private static void seed(String[] args) throws Exception {
        String className = null, key = null, sourceRoot = null, outRoot = null;
        for (int i = 1; i < args.length; i += 2) {
            if (i + 1 >= args.length) throw new IllegalArgumentException("missing value for " + args[i]);
            switch (args[i]) {
                case "--class" -> className = args[i + 1];
                case "--key" -> key = args[i + 1];
                case "--source-root" -> sourceRoot = args[i + 1];
                case "--out-root" -> outRoot = args[i + 1];
                default -> throw new IllegalArgumentException("unknown: " + args[i]);
            }
        }
        if (className == null || key == null || sourceRoot == null || outRoot == null) {
            throw new IllegalArgumentException(
                    "seed needs --class --key --source-root --out-root");
        }
        Exposed loader = new Exposed(ClassLoader.getSystemClassLoader(), new File(sourceRoot));
        Map<String, byte[]> map = loader.generate(className);
        if (map == null || map.isEmpty()) {
            throw new IllegalStateException("no bytecode generated for " + className);
        }
        new CacheStore(Path.of(outRoot), 2, 1L << 30).save(key, map);
        System.out.println("seeded " + map.size() + " classes into "
                + Path.of(outRoot, key) + " (key=" + key + ")");
    }

    private static void usage() {
        System.err.println("usage: CacheTool key [--verify] | inspect [key] | "
                + "seed --class C --key K --source-root DIR --out-root DIR");
        System.exit(2);
    }

    /**
     * {@link ScriptCacheKey#compute} 会在返回前重写 {@code key-manifest.json}。
     * 本工具的任何子命令都必须先算出结果、再把 agent 的原件写回：否则工具跑一次
     * 就把 agent 留下的证据覆盖成"工具自己算的"，后续 --verify 变成自己跟自己比，
     * 永远 match。
     */
    private static ScriptCacheKey.Result computeKeepingManifest(RuntimeContext ctx) {
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        byte[] original = readOrNull(manifestFile);
        try {
            return ScriptCacheKey.compute(ctx);
        } finally {
            restore(manifestFile, original);
        }
    }

    private static void restore(Path file, byte[] original) {
        try {
            if (original == null) {
                Files.deleteIfExists(file);
            } else if (java.util.Arrays.equals(original, readOrNull(file))) {
                // 内容一致就不动它：避免无谓地刷新 mtime（manifest 的 savedAt 是
                // racy-clean 判据的一部分，没必要制造无意义的写入）。
                return;
            } else {
                Path tmp = file.resolveSibling(file.getFileName() + ".verify-tmp");
                Files.createDirectories(file.getParent());
                Files.write(tmp, original);
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);
            }
        } catch (IOException e) {
            System.err.println("WARN: cannot restore " + file + ": " + e);
        }
    }

    private static byte[] readOrNull(Path file) {
        try {
            return Files.isRegularFile(file) ? Files.readAllBytes(file) : null;
        } catch (IOException e) {
            return null;
        }
    }

    /**
     * 把 canonical 的文件条目还原成 {@code path -> "size|sha256"}。
     *
     * <p>行格式随 R12 变了：现在是 {@code path|size|sha256}（3 段），R12 之前是
     * {@code path|size|mtime|sha256}（4 段）。这里两种都接受，避免本工具与
     * {@code ScriptCacheKey} 的版本必须同步。头部行不靠数量跳过，而是靠第二段
     * 是否为纯数字识别（见 {@link #isFileEntryLine}），所以将来再加头字段也不用改。
     */
    private static Map<String, String> parseCanonical(String canonical) {
        Map<String, String> map = new HashMap<>();
        for (String line : canonical.split("\n")) {
            if (!KeyManifest.isFileEntryLine(line)) continue;
            String[] f = line.split("\\|", 4);
            String sha = f[f.length - 1];
            map.put(f[0], f[1] + "|" + sha);
        }
        return map;
    }

    private static final class Snapshot {
        final boolean present;
        final int files;
        final long bytes;
        final String jvmJava;
        final String jvmClasspath;
        final Map<String, String> entries;

        private Snapshot(boolean present, int files, long bytes, String jvmJava,
                         String jvmClasspath, Map<String, String> entries) {
            this.present = present;
            this.files = files;
            this.bytes = bytes;
            this.jvmJava = jvmJava;
            this.jvmClasspath = jvmClasspath;
            this.entries = entries;
        }

        static Snapshot parse(byte[] raw) {
            if (raw == null) return new Snapshot(false, 0, 0, null, null, Map.of());
            try {
                String text = new String(raw, StandardCharsets.UTF_8);
                // 兼容旧格式（顶层 JSONArray，无 savedAt、无 jvm 身份）。
                JSONObject root = text.stripLeading().startsWith("{")
                        ? new JSONObject(text) : null;
                JSONArray array = root != null
                        ? root.optJSONArray("entries") : new JSONArray(text);
                if (array == null) return new Snapshot(false, 0, 0, null, null, Map.of());
                String jvmJava = null, jvmClasspath = null;
                if (root != null) {
                    String j = root.optString("jvmJava", "");
                    if (!j.isEmpty()) jvmJava = j;
                    String c = root.optString("jvmClasspath", "");
                    if (!c.isEmpty()) jvmClasspath = c;
                }
                Map<String, String> map = new HashMap<>();
                long bytes = 0;
                for (int i = 0; i < array.length(); i++) {
                    JSONObject o = array.getJSONObject(i);
                    long size = o.getLong("size");
                    bytes += size;
                    // 与 parseCanonical 同形：size|sha256（R12 起 canonical 不再有 mtime）。
                    map.put(o.getString("path"), size + "|" + o.getString("sha256"));
                }
                return new Snapshot(true, array.length(), bytes, jvmJava, jvmClasspath, map);
            } catch (JSONException | RuntimeException e) {
                return new Snapshot(false, 0, 0, null, null, Map.of());
            }
        }
    }

    static final class Exposed extends JavaSourceClassLoader {
        Exposed(ClassLoader parent, File root) {
            super(parent, new DirectoryResourceFinder(root), "UTF-8");
            setDebuggingInfo(true, true, true);
        }

        Map<String, byte[]> generate(String name) throws ClassNotFoundException {
            return generateBytecodes(name);
        }
    }
}
