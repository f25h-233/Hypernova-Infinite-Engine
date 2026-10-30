package hypernova.agent;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;

/**
 * 真实安装上的 key 分项基准。用法：
 *   KeyBench &lt;gameRoot&gt; &lt;modsRoot&gt; &lt;cacheRoot&gt; [iterations]
 *
 * <p>cacheRoot 必须是**清单的临时副本目录**，不能指向真实 scripts-cache：
 * 本工具会写 key-manifest.json。等价性与正确性由 KeyScannerTest/KeyManifestRefreshTest
 * 负责；这里只测真实 12k 文件树的阶段耗时。
 */
public final class KeyBench {
    private KeyBench() {
    }

    public static void main(String[] args) throws Exception {
        Path game = Path.of(args[0]).toAbsolutePath().normalize();
        Path mods = Path.of(args[1]).toAbsolutePath().normalize();
        Path cache = Path.of(args[2]).toAbsolutePath().normalize();
        int iters = args.length > 3 ? Integer.parseInt(args[3]) : 5;
        Path manifestFile = cache.resolve("key-manifest.json");

        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, game.resolve("saves"), cache,
                cache.resolve("agent.log"), cache.resolve("telemetry.jsonl"), cfg);

        long[] scan = new long[iters], load = new long[iters], refresh = new long[iters],
                canon = new long[iters], save = new long[iters], total = new long[iters];
        String key = "";
        int fileCount = 0;

        for (int i = 0; i < iters; i++) {
            long t = System.nanoTime();
            List<KeyScanner.FileInfo> files = KeyScanner.scan(ctx);
            scan[i] = ms(t);

            t = System.nanoTime();
            KeyManifest manifest = KeyManifest.load(manifestFile);
            load[i] = ms(t);

            t = System.nanoTime();
            List<KeyManifest.Entry> entries = manifest.refresh(files, false);
            refresh[i] = ms(t);

            t = System.nanoTime();
            List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
            sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
            StringBuilder sb = new StringBuilder(1 << 20);
            for (KeyManifest.Entry e : sorted) {
                sb.append(e.path()).append('|').append(e.size()).append('|')
                        .append(e.sha256()).append('\n');
            }
            key = sha256(sb.toString()).substring(0, 32);
            canon[i] = ms(t);

            t = System.nanoTime();
            if (manifest.saveNeeded()) manifest.save(manifestFile);
            save[i] = ms(t);

            fileCount = entries.size();
            total[i] = scan[i] + load[i] + refresh[i] + canon[i] + save[i];
            System.out.printf(Locale.ROOT,
                    "iter %d: files=%d key=%s scan=%d load=%d refresh=%d canon=%d save=%d total=%d%n",
                    i, fileCount, key, scan[i], load[i], refresh[i], canon[i], save[i], total[i]);
        }
        System.out.println("median: files=" + fileCount + " key=" + key
                + " scan=" + med(scan) + " load=" + med(load) + " refresh=" + med(refresh)
                + " canon=" + med(canon) + " save=" + med(save) + " total=" + med(total));
    }

    private static long ms(long t0) {
        return (System.nanoTime() - t0) / 1_000_000;
    }

    private static long med(long[] v) {
        long[] c = v.clone();
        Arrays.sort(c);
        return c[c.length / 2];
    }

    private static String sha256(String s) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
}
