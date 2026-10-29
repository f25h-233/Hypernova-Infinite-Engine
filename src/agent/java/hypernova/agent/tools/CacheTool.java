package hypernova.agent.tools;

import hypernova.agent.CachePack;
import hypernova.agent.CacheStore;
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
     * <p>匹配条件比"数量+字节"更严：逐文件比对 size/mtime/sha256。数量与字节相同
     * 但内容不同时，key 必然不同，只看数量+字节会给出假绿。java.version/classpath
     * 不参与此比对，它们由 cache-tool.sh 的 Base JRE 与公版 classpath 保证。
     *
     * <p><b>局限</b>：{@code KeyManifest.refresh} 在 size+mtime 未变时会复用清单里的
     * 旧 sha256，所以路径/mtime/复用 sha 三者都来自同一份 agent 证据，逐条比对只能
     * 抓"文件集合或 mtime 变了"，抓不到"内容变了但 size+mtime 没变"（那正是 racy-clean
     * 守卫要挡的场景，但守不住刻意改回 mtime 的情况）。加 {@code --deep} 会绕过清单、
     * 对每个文件独立重算 sha256 再比对；代价是 12k 文件约 7–11 s（见进度表 R5）。
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
        boolean match = agent.present && agent.files == r.fileCount()
                && agent.bytes == r.bytes() && agent.entries.equals(current);

        System.out.println("agent_manifest: files=" + agent.files + " bytes=" + agent.bytes);
        System.out.println("current      : files=" + r.fileCount() + " bytes=" + r.bytes());
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
            System.exit(1);
        }
    }

    /**
     * 对清单里的每个文件独立重算 sha256（不经过 KeyManifest 的复用逻辑），
     * 返回不一致条数。条目值是 "size|mtime|sha256"，sha 是最后一段。
     */
    private static int deepCompare(Map<String, String> expected) {
        int bad = 0;
        for (Map.Entry<String, String> e : expected.entrySet()) {
            String[] parts = e.getValue().split("\\|", 3);
            String actual = sha256(Path.of(e.getKey()));
            if (parts.length != 3 || actual == null || !actual.equals(parts[2])) {
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
     * 把 canonical 文本还原成 path -> "size|mtime|sha256"；前两行是 java= 与 classpath=。
     * 行格式是 {@code path|size|mtime|sha256}，path 在 Windows 上不可能含 {@code |}，
     * 所以 limit=4 的切分是安全的（用 lastIndexOf 两次会少切一段）。
     */
    private static Map<String, String> parseCanonical(String canonical) {
        Map<String, String> map = new HashMap<>();
        String[] lines = canonical.split("\n");
        for (int i = 2; i < lines.length; i++) {
            String[] f = lines[i].split("\\|", 4);
            if (f.length != 4) continue;
            map.put(f[0], f[1] + "|" + f[2] + "|" + f[3]);
        }
        return map;
    }

    private static final class Snapshot {
        final boolean present;
        final int files;
        final long bytes;
        final Map<String, String> entries;

        private Snapshot(boolean present, int files, long bytes, Map<String, String> entries) {
            this.present = present;
            this.files = files;
            this.bytes = bytes;
            this.entries = entries;
        }

        static Snapshot parse(byte[] raw) {
            if (raw == null) return new Snapshot(false, 0, 0, Map.of());
            try {
                String text = new String(raw, StandardCharsets.UTF_8);
                // 兼容旧格式（顶层 JSONArray，无 savedAt）。
                JSONArray array = text.stripLeading().startsWith("{")
                        ? new JSONObject(text).optJSONArray("entries")
                        : new JSONArray(text);
                if (array == null) return new Snapshot(false, 0, 0, Map.of());
                Map<String, String> map = new HashMap<>();
                long bytes = 0;
                for (int i = 0; i < array.length(); i++) {
                    JSONObject o = array.getJSONObject(i);
                    long size = o.getLong("size");
                    bytes += size;
                    map.put(o.getString("path"),
                            size + "|" + o.getLong("mtime") + "|" + o.getString("sha256"));
                }
                return new Snapshot(true, array.length(), bytes, map);
            } catch (JSONException | RuntimeException e) {
                return new Snapshot(false, 0, 0, Map.of());
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
