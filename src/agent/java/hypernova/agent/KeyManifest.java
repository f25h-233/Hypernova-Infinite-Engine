package hypernova.agent;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

public final class KeyManifest {
    public record Entry(String path, long size, long mtime, String sha256) {
    }

    private final Map<String, Entry> byPath = new HashMap<>();
    private long savedAt;
    /**
     * 写这份清单那个进程的 {@code java.version}；{@code null} = 旧版清单没有这个字段。
     *
     * <p>存在的理由：文件条目只覆盖"文件集"，无法证明工具与 agent 用的是同一个 JVM
     * 和同一条 classpath。这两者任一不同，key 就不同，但文件集可以完全一样。
     * 见 {@code CacheTool key --verify}。
     *
     * <p>为什么不直接存 canonical 的头三行：{@code KeyManifest} 拿不到
     * {@link RuntimeContext}，而 {@code classpath=} 那一行是
     * {@code ScriptCacheKey.classpathOrder} 按 {@code gameRoot} 过滤后的结果。所以这里
     * 存<b>原始</b> JVM 属性（写清单那个进程的真实值，游戏里就是 agent 的），
     * 由 {@link #scriptClasspath} 用与生产完全相同的规则还原。
     * {@code enabled=} 那一行由 {@code enabled_mods.json} 的字节 sha256 完全决定，
     * 已经包含在文件条目里，不需要单独记。
     */
    private String jvmJava;
    /** 写这份清单那个进程的原始 {@code java.class.path}；{@code null} = 旧版清单。 */
    private String jvmClasspath;

    public static KeyManifest load(Path file) {
        KeyManifest manifest = new KeyManifest();
        if (!Files.isRegularFile(file)) return manifest;
        try {
            String text = Files.readString(file);
            // 旧格式是顶层 JSONArray，没有 savedAt；当作 0 = 全部条目不可信、全量重算。
            if (text.stripLeading().startsWith("{")) {
                JSONObject root = new JSONObject(text);
                manifest.savedAt = root.optLong("savedAt", 0L);
                // 旧清单没有这两个字段；保留 null，让 --verify 能区分"没这个信息"和"不一致"。
                String j = root.optString("jvmJava", "");
                if (!j.isEmpty()) manifest.jvmJava = j;
                String c = root.optString("jvmClasspath", "");
                if (!c.isEmpty()) manifest.jvmClasspath = c;
                JSONArray array = root.optJSONArray("entries");
                if (array != null) manifest.addAll(array);
            } else {
                manifest.addAll(new JSONArray(text));
            }
        } catch (Throwable t) {
            // 半截清单不可信：清空并重置 savedAt，宁可全量重算。
            manifest.byPath.clear();
            manifest.savedAt = 0L;
            AgentLog.fail("key manifest load failed; rebuilding", t);
        }
        return manifest;
    }

    private void addAll(JSONArray array) throws JSONException {
        for (int i = 0; i < array.length(); i++) {
            JSONObject o = array.getJSONObject(i);
            Entry e = new Entry(o.getString("path"), o.getLong("size"),
                    o.getLong("mtime"), o.getString("sha256"));
            byPath.put(e.path(), e);
        }
    }

    public List<Entry> refresh(List<Path> files) {
        List<Entry> out = new ArrayList<>(files.size());
        for (Path p : files) {
            try {
                String path = p.toString();
                long size = Files.size(p);
                long mtime = Files.getLastModifiedTime(p).toMillis();
                Entry prev = byPath.get(path);
                // git 的 racy-clean 规则：清单写完之后才被改过的文件（mtime >= savedAt）
                // 时间戳不可信，必须重算 sha256；否则同尺寸 + mtime 被改回旧值就能骗过复用。
                String hash = (prev != null && prev.size() == size && prev.mtime() == mtime
                        && mtime < savedAt)
                        ? prev.sha256() : sha256(p);
                out.add(new Entry(path, size, mtime, hash));
            } catch (IOException e) {
                AgentLog.fail("stat failed: " + p, e);
            }
        }
        byPath.clear();
        for (Entry e : out) byPath.put(e.path(), e);
        return out;
    }

    /** 清单记录的 JVM 版本；旧清单或未设置时为 {@code null}。 */
    public String jvmJava() {
        return jvmJava;
    }

    /** 清单记录的原始 {@code java.class.path}；旧清单或未设置时为 {@code null}。 */
    public String jvmClasspath() {
        return jvmClasspath;
    }

    /**
     * 用与 {@code ScriptCacheKey.classpathOrder} <b>完全相同</b>的规则，把原始
     * {@code java.class.path} 过滤成 canonical 里 {@code classpath=} 行的内容。
     *
     * <p>规则（必须与生产逐字一致，否则这里会误报不一致）：
     * 按 {@link java.io.File#pathSeparator} 切分 → 去空 → {@code toAbsolutePath().normalize()}
     * → 保留"是普通文件、位于 {@code gameRoot} 下、文件名不是 hypernova.agent.jar"
     * → 用 {@code File.pathSeparator} 重新拼接。
     */
    public static String scriptClasspath(String rawClasspath, Path gameRoot) {
        if (rawClasspath == null) return null;
        Path root = gameRoot.toAbsolutePath().normalize();
        List<String> out = new ArrayList<>();
        for (String cp : rawClasspath.split(java.util.regex.Pattern.quote(
                java.io.File.pathSeparator))) {
            if (cp.isBlank()) continue;
            Path p = Path.of(cp).toAbsolutePath().normalize();
            if (Files.isRegularFile(p) && p.startsWith(root)
                    && !p.getFileName().toString().equals("hypernova.agent.jar")) {
                out.add(p.toString());
            }
        }
        return String.join(java.io.File.pathSeparator, out);
    }

    /**
     * 文件条目行形如 {@code <path>|<size>|<sha256>}（R12 起；R12 之前是 4 段），
     * 第二段必须是纯数字。头部行 {@code java=} / {@code classpath=} / {@code enabled=}
     * 都不含 {@code |}（Windows 路径不可能含），所以不会误判。
     */
    public static boolean isFileEntryLine(String line) {
        String[] f = line.split("\\|", 4);
        if (f.length < 3 || f[1].isEmpty()) return false;
        for (int i = 0; i < f[1].length(); i++) {
            if (!Character.isDigit(f[1].charAt(i))) return false;
        }
        return true;
    }

    /**
     * 头不一致时打印用的差异行：{@code java=} 与 {@code classpath=} 两项。
     * 任一为 {@code null} 表示清单里没有这个信息（旧格式）。
     */
    public static List<String> headerDiff(String agentJava, String agentClasspath,
                                          String currentJava, String currentClasspath) {
        List<String> out = new ArrayList<>();
        if (agentJava == null || !agentJava.equals(currentJava)) {
            out.add("-java=" + (agentJava == null ? "<missing>" : agentJava));
            out.add("+java=" + currentJava);
        }
        if (agentClasspath == null || !agentClasspath.equals(currentClasspath)) {
            out.add("-classpath=" + (agentClasspath == null ? "<missing>" : agentClasspath));
            out.add("+classpath=" + currentClasspath);
        }
        return out;
    }

    public void save(Path file) throws IOException {
        JSONArray array = new JSONArray();
        long now = System.currentTimeMillis();
        JSONObject root = new JSONObject();
        // 自捕获而不是由调用方传入：save() 与 ScriptCacheKey 读 System.getProperty 发生在
        // 同一进程、同一时刻，两者不可能不一致；这样也不必改 ScriptCacheKey 的签名。
        String java = System.getProperty("java.version", "");
        String cp = System.getProperty("java.class.path", "");
        try {
            if (!java.isEmpty()) {
                root.put("jvmJava", java);
                jvmJava = java;
            }
            if (!cp.isEmpty()) {
                root.put("jvmClasspath", cp);
                jvmClasspath = cp;
            }
            for (Entry e : byPath.values()) {
                JSONObject o = new JSONObject();
                o.put("path", e.path());
                o.put("size", e.size());
                o.put("mtime", e.mtime());
                o.put("sha256", e.sha256());
                array.put(o);
            }
            root.put("savedAt", now);
            root.put("entries", array);
        } catch (JSONException e) {
            // 游戏自带 json.jar 是 2010 版 org.json：JSONException 为 checked。
            throw new IOException("key manifest encode failed", e);
        }
        Files.createDirectories(file.getParent());
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        Files.writeString(tmp, root.toString(), StandardCharsets.UTF_8);
        Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
        savedAt = now;
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream in = Files.newInputStream(path)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            return HexFormat.of().formatHex(md.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }
}
