package hypernova.agent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;

public final class ScriptCacheKey {
    public record Result(String id, String canonical, int fileCount, long bytes,
                         long elapsedMillis) {
    }

    private ScriptCacheKey() {
    }

    public static Result compute(RuntimeContext ctx) {
        long t0 = System.nanoTime();

        long t = System.nanoTime();
        List<KeyScanner.FileInfo> files = KeyScanner.scan(ctx);
        long scanMs = millis(t);

        t = System.nanoTime();
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        KeyManifest manifest = KeyManifest.load(manifestFile);
        long loadMs = millis(t);

        t = System.nanoTime();
        boolean forceRehash = Boolean.getBoolean("hypernova.rehash");
        List<KeyManifest.Entry> entries = manifest.refresh(files, forceRehash);
        long refreshMs = millis(t);

        t = System.nanoTime();
        List<String> classpathOrder = classpathOrder(ctx);
        StringBuilder sb = new StringBuilder(1 << 20);
        sb.append("java=").append(System.getProperty("java.version", "")).append('\n');
        sb.append("classpath=").append(String.join(File.pathSeparator, classpathOrder)).append('\n');
        // 启用清单进 canonical：enabledMods 的「集合」变化会改变 classpath 装载/编译优先级
        // 与游戏实际加载的 mod（ModManager.loadEnabledModList 按 id 匹配）。
        // 这里排序后写入，所以【本行】只表达集合、不表达顺序；但【整体 key】对顺序仍敏感：
        // enabled_mods.json 自身的字节 sha256 在下面的文件清单里，顺序一变该文件的 sha256
        // 就变，key 随之变（顺序确实影响 classpath 优先级，必须敏感）。实测见 R12 报告。
        sb.append("enabled=").append(String.join(",", enabledIds(ctx.modsRoot()))).append('\n');
        List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
        for (KeyManifest.Entry e : sorted) {
            // 只写 path|size|sha256，不写 mtime：sha256 已完整覆盖内容，mtime 进 canonical
            // 只会额外制造 miss —— git checkout / 解压 / 备份还原 / 复制粘贴等「内容不变、
            // 时间变」的操作都会让整份缓存失效，代价是一次完整冷编译。
            // mtime 仍保留在 KeyManifest 内部，仅用于 size+mtime 短路省重算 sha 的性能
            // （由 racy-clean 守卫兜底），该决策不传播到 key 本身。
            sb.append(e.path()).append('|').append(e.size()).append('|')
                    .append(e.sha256()).append('\n');
        }
        String canonical = sb.toString();
        String id = sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0, 32);
        long canonicalMs = millis(t);

        t = System.nanoTime();
        if (manifest.saveNeeded()) {
            try {
                manifest.save(manifestFile);
            } catch (IOException e) {
                AgentLog.fail("key manifest save failed", e);
            }
        }
        long saveMs = millis(t);

        long bytes = entries.stream().mapToLong(KeyManifest.Entry::size).sum();
        long totalMs = millis(t0);
        AgentLog.info("cache key breakdown: files=" + entries.size()
                + ", scan=" + scanMs + " ms, load=" + loadMs + " ms, refresh=" + refreshMs
                + " ms, canonical=" + canonicalMs + " ms, save=" + saveMs + " ms, total="
                + totalMs + " ms, rehash=" + forceRehash);
        return new Result(id, canonical, entries.size(), bytes, totalMs);
    }

    private static long millis(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }

    static List<Path> collectFiles(RuntimeContext ctx) {
        List<Path> out = new ArrayList<>();
        for (KeyScanner.FileInfo f : KeyScanner.scan(ctx)) out.add(f.path());
        return out;
    }

    /**
     * 读 {@code modsRoot/enabled_mods.json} 的 {@code enabledMods} 数组，排序后返回。
     *
     * <p>与启动器同语义：{@code ModManager.loadEnabledModList()} 调
     * {@code LoadingUtils.f00000(String filename)}，它内部走
     * {@code LoadingUtils.ô00000(String, String)}——即「先剥 {@code #} 注释再交给 org.json」，
     * 所以这里走 {@link #stripComments} 而不是直接 {@code new JSONObject(text)}。
     *
     * <p><b>任何失败都退化为空列表并记日志，绝不外抛</b>：agent 跑在游戏进程里，
     * 一个坏掉的 enabled_mods.json 不能让游戏启动失败。空列表会让 key 少一行信息，
     * 但 {@code enabled_mods.json} 自身的字节仍进文件清单，内容一变 key 照样变。
     */
    private static List<String> enabledIds(Path mods) {
        List<String> out = new ArrayList<>();
        Path file = mods.resolve("enabled_mods.json");
        if (!Files.isRegularFile(file)) return out;
        try {
            String text = Files.readString(file, StandardCharsets.UTF_8);
            JSONObject root = new JSONObject(stripComments(text));
            JSONArray array = root.optJSONArray("enabledMods");
            if (array == null) return out;
            for (int i = 0; i < array.length(); i++) {
                Object v = array.opt(i);
                if (v instanceof String s && !s.isEmpty()) out.add(s);
            }
            out.sort(Comparator.naturalOrder());
        } catch (Throwable t) {
            AgentLog.fail("enabled_mods.json parse failed, treating as empty: " + file, t);
            out.clear();
        }
        return out;
    }

    /**
     * 逐字对应 {@code com.fs.starfarer.loading.LoadingUtils}（反编译
     * {@code LoadingUtils.ô00000(String filename, String json)}，见
     * {@code .research/decomp/src/com/fs/starfarer/loading/LoadingUtils.java} 第 72–104 行）
     * 的注释剥离循环。那份代码是启动器实际解析 mod_info.json / enabled_mods.json 的路径，
     * 语义必须完全一致：
     *
     * <ul>
     *   <li>{@code "} 无条件翻转 inString（包括出现在行尾的那一次）；</li>
     *   <li>{@code \r} 或 {@code \n} 一律重置 inComment/inString，且只有 {@code \n}
     *       被写入（{@code \r} 被丢弃，故 CRLF 会变 LF）；</li>
     *   <li>{@code #} 仅在 <b>字符串外</b>（{@code !inString}）才开启注释；</li>
     *   <li>注释中的字符全部丢弃，注释外的字符原样保留（含 {@code "} 本身）。</li>
     * </ul>
     *
     * 原文（反编译变量名）：{@code if (c == '"') inString = !inString;
     * if (c == '\n' || c == '\r') { inComment = false; inString = false;
     * if (c == '\n') sb.append('\n'); } else if (c == '#' && !inString) {
     * inComment = true; } else if (!inComment) { sb.append(c); }}
     */
    static String stripComments(String text) {
        StringBuilder sb = new StringBuilder(text.length());
        boolean inComment = false;
        boolean inString = false;
        for (int n = 0; n < text.length(); n++) {
            char c = text.charAt(n);
            if (c == '"') {
                inString = !inString;
            }
            if (c == '\n' || c == '\r') {
                inComment = false;
                inString = false;
                if (c == '\n') sb.append('\n');
            } else if (c == '#' && !inString) {
                inComment = true;
            } else if (!inComment) {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    static List<String> classpathOrder(RuntimeContext ctx) {
        Path root = ctx.gameRoot().toAbsolutePath().normalize();
        List<String> out = new ArrayList<>();
        for (String cp : System.getProperty("java.class.path", "").split(File.pathSeparator)) {
            if (cp.isBlank()) continue;
            Path p = Path.of(cp).toAbsolutePath().normalize();
            if (Files.isRegularFile(p) && p.startsWith(root)
                    && !p.getFileName().toString().equals("hypernova.agent.jar")) {
                out.add(p.toString());
            }
        }
        return out;
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
