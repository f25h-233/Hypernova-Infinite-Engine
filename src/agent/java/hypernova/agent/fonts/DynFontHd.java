package hypernova.agent.fonts;

import hypernova.agent.AgentLog;
import hypernova.agent.RuntimeContext;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * 远星汉化优化测试版（startup-optimization）的高清字体桥。
 *
 * <h3>为什么需要它</h3>
 *
 * <p>优化版把高清矢量字体生成到
 * {@code starsector-core/graphics/fonts/dyn_font/cache/s<比例>-<哈希>/}，
 * 再由 {@code DynFontOverrides.openStream} 把 {@code graphics/fonts/*.fnt}
 * 重定向到这些文件。Fast Rendering 覆写的
 * {@code TextureLoader -> FileLoader -> FileLoaderFast} 不经过
 * {@code com.fs.util.C}，所以 {@code openStream} 不会执行，缓存也就不会生成；
 * 结果是优化版的高清字体在 FR 下静默退回 2048 宽的低清位图。</p>
 *
 * <h3>本类怎么做</h3>
 *
 * <ol>
 *   <li>在 agent premain（游戏加载字体之前）反射调用
 *       {@code DynFontOverrides.initialize()}，让优化版自己的原生库把缓存生成出来。
 *       首次约 2–3 秒，之后复用缓存约 0.2 秒。</li>
 *   <li>扫缓存目录，把 {@code *.fnt} 与它自己声明的 page 图配对，校验
 *       {@code common scaleW/scaleH} 与 PNG IHDR 尺寸一致；{@code _exact}
 *       是优化版渲染器专用的 26.6 定点布局，不碰。</li>
 *   <li>把配对好的 {@code .fnt} / {@code _0.png} 复制到
 *       {@code graphics/fonts/}，原文件首次备份为
 *       {@code *.bak-hypernova-hd}。FR 之后按原路径读到的就是高清图集，
 *       不需要改 FR 的任何字节码，因此对 0.9.7rc2 / 0.9.7 / 0.9.8 / 1.0.0
 *       都不挑版本。</li>
 * </ol>
 *
 * <h3>安全边界</h3>
 *
 * <ul>
 *   <li>只在优化版的三件套存在时才动作：{@code dyn_font/typefaces.dat}、
 *       {@code dyn_font/chars.txt}、{@code native/windows/ss_dyn_font.dll}；</li>
 *   <li>只在 {@code DynFontOverrides} 可加载且初始化成功后动作；</li>
 *   <li>只替换成对命中的字体；目标 {@code graphics/fonts/<name>.fnt} 或
 *       page 图不存在时跳过，不新增字体；</li>
 *   <li>每份被替换的原文件只备份一次；重复启动按内容哈希跳过；</li>
 *   <li>任何异常 fail-open：日志记录后继续启动，游戏退回原版位图。</li>
 * </ul>
 *
 * <p>关闭：{@code -Dhypernova.fontHd=false}；只观察不写盘：
 * {@code -Dhypernova.fontHd.dryRun=true}。</p>
 */
public final class DynFontHd {

    public static final String ENABLED_PROP = "hypernova.fontHd";
    public static final String DRY_RUN_PROP = "hypernova.fontHd.dryRun";

    /** 优化版 DynFont 的入口类；不在 classpath 上说明不是优化版。 */
    private static final String DYN_FONT_CLASS =
            "org.fossic.starsector.dynfont.DynFontOverrides";

    private static final String BACKUP_SUFFIX = ".bak-hypernova-hd";

    /** 只读 4 KiB 头部；fnt 的 common/page 行都在最前面。 */
    private static final int FNT_HEAD_BYTES = 4096;

    private static final Log AGENT_LOG = new Log() {
        @Override
        public void info(String msg) {
            AgentLog.info(msg);
        }

        @Override
        public void fail(String msg, Throwable t) {
            AgentLog.fail(msg, t);
        }
    };

    private DynFontHd() {
    }

    /** 便于单元测试注入的日志口。 */
    interface Log {
        void info(String msg);

        void fail(String msg, Throwable t);
    }

    /** 一对同源高清字体：源缓存里的 fnt/page，与游戏 graphics/fonts 下的目标。 */
    static final class Pair {
        final Path sourceFnt;
        final Path sourcePage;
        final Path targetFnt;
        final Path targetPage;

        Pair(Path sourceFnt, Path sourcePage, Path targetFnt, Path targetPage) {
            this.sourceFnt = sourceFnt;
            this.sourcePage = sourcePage;
            this.targetFnt = targetFnt;
            this.targetPage = targetPage;
        }
    }

    static final class Counter {
        int applied;
        int already;
        int failed;
    }

    static final class FntHead {
        final int scaleW;
        final int scaleH;
        final int pages;
        final String page;

        FntHead(int scaleW, int scaleH, int pages, String page) {
            this.scaleW = scaleW;
            this.scaleH = scaleH;
            this.pages = pages;
            this.page = page;
        }
    }

    /**
     * premain 入口：生成缓存并应用高清字体。所有异常都在内部吞掉并记日志，
     * 绝不阻断启动。
     */
    public static void ensureApplied(RuntimeContext ctx) {
        boolean enabled = !"false".equalsIgnoreCase(
                System.getProperty(ENABLED_PROP, "true"));
        if (!enabled) {
            AGENT_LOG.info("fontHd: disabled by -D" + ENABLED_PROP + "=false");
            return;
        }
        long started = System.nanoTime();
        try {
            Path core = resolveCore(ctx);
            Path dynFont = core.resolve("graphics/fonts/dyn_font");
            if (!Files.isRegularFile(dynFont.resolve("typefaces.dat"))
                    || !Files.isRegularFile(dynFont.resolve("chars.txt"))
                    || !Files.isRegularFile(core.resolve(
                    "native/windows/ss_dyn_font.dll"))) {
                AGENT_LOG.info("fontHd: optimized DynFont files not present; skipped");
                return;
            }

            ClassLoader loader = Thread.currentThread().getContextClassLoader();
            if (loader == null) {
                loader = ClassLoader.getSystemClassLoader();
            }
            Class<?> dynFontClass;
            try {
                dynFontClass = Class.forName(DYN_FONT_CLASS, false, loader);
            } catch (ClassNotFoundException e) {
                AGENT_LOG.info("fontHd: DynFontOverrides not present; skipped");
                return;
            }

            // 优化版自己初始化：加载 ss_dyn_font.dll、探测缩放、生成/复用缓存。
            // 这是普通玩家跑优化版时本来就会做的事，只是 FR 把它绕过了。
            // Mikihime 的启动档有时只写 ..\mikohime/windows；把游戏 native 目录补进去，
            // 让 System.loadLibrary("ss_dyn_font") 能找到优化版自带的 DLL。
            ensureLibraryPath(core, AGENT_LOG);
            long initStart = System.nanoTime();
            java.lang.reflect.Method initialize =
                    dynFontClass.getDeclaredMethod("initialize");
            initialize.setAccessible(true);
            initialize.invoke(null);
            long initMs = (System.nanoTime() - initStart) / 1_000_000L;

            java.lang.reflect.Method isEnabled =
                    dynFontClass.getDeclaredMethod("isEnabled");
            isEnabled.setAccessible(true);
            if (!Boolean.TRUE.equals(isEnabled.invoke(null))) {
                AGENT_LOG.info("fontHd: DynFont initialize returned disabled after "
                        + initMs + " ms; skipped");
                return;
            }

            Path cacheRoot = dynFont.resolve("cache");
            Path cache = latestCompleteCache(cacheRoot);
            if (cache == null) {
                AGENT_LOG.info("fontHd: no complete dyn_font cache under "
                        + cacheRoot + "; skipped");
                return;
            }

            Path fonts = core.resolve("graphics/fonts");
            List<Pair> pairs = scanCache(cache, fonts, AGENT_LOG);
            if (pairs.isEmpty()) {
                AGENT_LOG.info("fontHd: no usable HD font pairs in "
                        + cache.getFileName() + "; skipped");
                return;
            }
            boolean dryRun = "true".equalsIgnoreCase(
                    System.getProperty(DRY_RUN_PROP, "false"));
            Counter counter = applyPairs(fonts, pairs, dryRun, AGENT_LOG);
            AGENT_LOG.info("fontHd: cache=" + cache.getFileName()
                    + " init=" + initMs + "ms fonts=" + pairs.size()
                    + " applied=" + counter.applied
                    + " already=" + counter.already
                    + " failed=" + counter.failed
                    + (dryRun ? " dryRun=true" : "")
                    + " time=" + ((System.nanoTime() - started) / 1_000_000L) + "ms");
        } catch (Throwable t) {
            AGENT_LOG.fail("fontHd: bridge failed; continuing with original fonts", t);
        }
    }

    /** CWD 是 starsector-core 时直接用；不是时退回 RuntimeContext 推导。 */
    static Path resolveCore(RuntimeContext ctx) {
        Path cwd = Path.of(System.getProperty("user.dir", "."))
                .toAbsolutePath().normalize();
        if (Files.isDirectory(cwd.resolve("graphics/fonts"))) {
            return cwd;
        }
        if (ctx != null) {
            Path candidate = ctx.gameRoot().resolve("starsector-core");
            if (Files.isDirectory(candidate.resolve("graphics/fonts"))) {
                return candidate;
            }
        }
        return cwd;
    }

    /**
     * 确保 {@code java.library.path} 里有游戏的 {@code native/windows}。
     *
     * <p>Mikihime 生成的启动档有时只写 {@code ..\mikohime/windows}；优化版的
     * {@code DynFontNatives.load()} 用 {@code System.loadLibrary("ss_dyn_font")}，
     * 找不到就不会生成缓存。若 JVM 还没缓存 library path，补上即可；已经缓存
     * 时补属性也无害，日志会留一行。</p>
     */
    static void ensureLibraryPath(Path core, Log log) {
        try {
            Path nativeDir = core.resolve("native/windows").toAbsolutePath().normalize();
            String current = System.getProperty("java.library.path", "");
            String normalized = current.replace('/', '\\').toLowerCase(Locale.ROOT);
            String nativeText = nativeDir.toString().replace('/', '\\')
                    .toLowerCase(Locale.ROOT);
            if (normalized.contains(nativeText) || normalized.contains("native\\windows")) {
                return;
            }
            String updated = current.isEmpty()
                    ? nativeDir.toString()
                    : current + java.io.File.pathSeparator + nativeDir;
            System.setProperty("java.library.path", updated);
            log.info("fontHd: appended " + nativeDir + " to java.library.path");
        } catch (Throwable t) {
            log.fail("fontHd: cannot adjust java.library.path", t);
        }
    }

    /** 取最新一个带 .complete 标记的 s* 缓存目录。 */
    static Path latestCompleteCache(Path cacheRoot) {
        if (!Files.isDirectory(cacheRoot)) {
            return null;
        }
        Path best = null;
        long bestTime = Long.MIN_VALUE;
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(cacheRoot)) {
            for (Path dir : ds) {
                try {
                    if (!Files.isDirectory(dir)
                            || dir.getFileName() == null
                            || !dir.getFileName().toString().startsWith("s")
                            || !Files.isRegularFile(dir.resolve(".complete"))) {
                        continue;
                    }
                    long time = Files.getLastModifiedTime(dir).toMillis();
                    if (time > bestTime) {
                        bestTime = time;
                        best = dir;
                    }
                } catch (IOException ignored) {
                    // 单个目录读不到就跳过
                }
            }
        } catch (IOException e) {
            return null;
        }
        return best;
    }

    /**
     * 扫描缓存目录，产出「fnt + 自己声明的 page」配对。
     *
     * <p>只接受同时满足以下条件的字体：{@code common scaleW/scaleH} 与 PNG
     * IHDR 完全一致、单 page、目标 {@code graphics/fonts/<name>.fnt} 与目标
     * page 都存在。这样不会出现 fnt 走高清、png 走原版导致的竖条。</p>
     */
    static List<Pair> scanCache(Path cacheDir, Path fontsDir, Log log) {
        List<Pair> out = new ArrayList<>();
        if (!Files.isDirectory(cacheDir) || !Files.isDirectory(fontsDir)) {
            return out;
        }
        List<Path> fnts = new ArrayList<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(cacheDir, "*.fnt")) {
            for (Path fnt : ds) {
                fnts.add(fnt);
            }
        } catch (IOException e) {
            log.fail("fontHd: cache scan failed: " + cacheDir, e);
            return out;
        }
        fnts.sort(Comparator.comparing(p -> p.getFileName().toString()));
        for (Path fnt : fnts) {
            String name = fnt.getFileName().toString();
            if (name.toLowerCase(Locale.ROOT).contains("_exact")) {
                continue;
            }
            try {
                FntHead head = readFntHead(fnt);
                if (head == null) {
                    log.info("fontHd: reject " + name + " (no common/page)");
                    continue;
                }
                if (head.pages != 1) {
                    log.info("fontHd: reject " + name + " (pages=" + head.pages + ")");
                    continue;
                }
                Path sourcePage = cacheDir.resolve(head.page);
                int[] actual = pngSize(sourcePage);
                if (actual == null || actual[0] != head.scaleW || actual[1] != head.scaleH) {
                    log.info("fontHd: reject " + name + " (layout fnt="
                            + head.scaleW + "x" + head.scaleH + " png="
                            + (actual == null ? "?" : actual[0] + "x" + actual[1]) + ")");
                    continue;
                }
                Path targetFnt = fontsDir.resolve(name);
                Path targetPage = fontsDir.resolve(head.page);
                if (!Files.isRegularFile(targetFnt)
                        || !Files.isRegularFile(targetPage)) {
                    log.info("fontHd: reject " + name + " (target font/page missing)");
                    continue;
                }
                out.add(new Pair(fnt, sourcePage, targetFnt, targetPage));
            } catch (Throwable t) {
                log.fail("fontHd: reject " + name, t);
            }
        }
        return out;
    }

    /**
     * 把配对复制到 {@code graphics/fonts/}；目标已与源同哈希则跳过。
     * 原文件首次写入前备份为 {@code *.bak-hypernova-hd}。
     */
    static Counter applyPairs(Path fontsDir, List<Pair> pairs, boolean dryRun,
                              Log log) {
        Counter counter = new Counter();
        for (Pair pair : pairs) {
            try {
                boolean fntSame = sameContent(pair.sourceFnt, pair.targetFnt);
                boolean pageSame = sameContent(pair.sourcePage, pair.targetPage);
                if (fntSame && pageSame) {
                    counter.already++;
                    continue;
                }
                if (dryRun) {
                    log.info("fontHd: would apply " + pair.targetFnt.getFileName()
                            + " + " + pair.targetPage.getFileName());
                    counter.applied++;
                    continue;
                }
                if (!fntSame) {
                    backupOnce(pair.targetFnt, log);
                    copy(pair.sourceFnt, pair.targetFnt);
                }
                if (!pageSame) {
                    backupOnce(pair.targetPage, log);
                    copy(pair.sourcePage, pair.targetPage);
                }
                counter.applied++;
            } catch (Throwable t) {
                counter.failed++;
                log.fail("fontHd: apply failed for "
                        + pair.targetFnt.getFileName(), t);
            }
        }
        return counter;
    }

    private static void backupOnce(Path target, Log log) throws IOException {
        Path backup = target.resolveSibling(
                target.getFileName().toString() + BACKUP_SUFFIX);
        if (Files.exists(backup)) {
            return;
        }
        Files.copy(target, backup);
        log.info("fontHd: backup " + backup.getFileName());
    }

    private static void copy(Path source, Path target) throws IOException {
        try {
            Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES);
        } catch (IOException e) {
            // 某些文件系统不支持 COPY_ATTRIBUTES；内容仍可复制。
            Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static boolean sameContent(Path a, Path b) {
        try {
            if (!Files.isRegularFile(a) || !Files.isRegularFile(b)
                    || Files.size(a) != Files.size(b)) {
                return false;
            }
            return MessageDigest.isEqual(sha256(a), sha256(b));
        } catch (IOException e) {
            return false;
        }
    }

    private static byte[] sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (java.io.InputStream in = Files.newInputStream(path)) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) {
                    digest.update(buf, 0, n);
                }
            }
            return digest.digest();
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException("SHA-256 unavailable", e);
        }
    }

    /** 读 fnt 头部：common 的 scaleW/scaleH/pages 与第一行 page 的 file。 */
    static FntHead readFntHead(Path fnt) {
        byte[] buf = new byte[FNT_HEAD_BYTES];
        int n;
        try (java.io.InputStream in = Files.newInputStream(fnt)) {
            n = in.read(buf);
        } catch (IOException e) {
            return null;
        }
        if (n <= 0) {
            return null;
        }
        String text = new String(buf, 0, n, StandardCharsets.ISO_8859_1);
        int scaleW = -1;
        int scaleH = -1;
        int pages = -1;
        String page = null;
        for (String raw : text.split("\n")) {
            String line = raw.trim();
            if (line.startsWith("common")) {
                scaleW = intField(line, "scaleW=");
                scaleH = intField(line, "scaleH=");
                pages = intField(line, "pages=");
            } else if (line.startsWith("page") && page == null) {
                int q0 = line.indexOf('"');
                int q1 = q0 >= 0 ? line.indexOf('"', q0 + 1) : -1;
                if (q0 >= 0 && q1 > q0) {
                    page = leafName(line.substring(q0 + 1, q1));
                }
            }
        }
        if (scaleW <= 0 || scaleH <= 0 || pages < 0 || page == null || page.isEmpty()) {
            return null;
        }
        return new FntHead(scaleW, scaleH, pages, page);
    }

    private static int intField(String line, String key) {
        int i = line.indexOf(key);
        if (i < 0) {
            return -1;
        }
        int j = i + key.length();
        int value = 0;
        boolean any = false;
        while (j < line.length()) {
            char c = line.charAt(j);
            if (c < '0' || c > '9') {
                break;
            }
            value = value * 10 + (c - '0');
            any = true;
            j++;
        }
        return any ? value : -1;
    }

    private static String leafName(String path) {
        int slash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        return slash >= 0 ? path.substring(slash + 1) : path;
    }

    /** 只读 PNG IHDR 的宽高（不解码像素）。 */
    static int[] pngSize(Path png) {
        try (java.io.DataInputStream in = new java.io.DataInputStream(
                Files.newInputStream(png))) {
            byte[] sig = new byte[8];
            in.readFully(sig);
            if ((sig[0] & 0xFF) != 0x89 || sig[1] != 'P' || sig[2] != 'N'
                    || sig[3] != 'G') {
                return null;
            }
            in.readInt();
            in.readFully(new byte[4]);
            int w = in.readInt();
            int h = in.readInt();
            return (w > 0 && h > 0) ? new int[]{w, h} : null;
        } catch (IOException e) {
            return null;
        }
    }
}
