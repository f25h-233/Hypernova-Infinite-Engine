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
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class ScriptCacheKey {
    public record Result(String id, String canonical, int fileCount, long bytes,
                         long elapsedMillis) {
    }

    private ScriptCacheKey() {
    }

    public static Result compute(RuntimeContext ctx) {
        long t0 = System.nanoTime();
        List<Path> files = collectFiles(ctx);
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        KeyManifest manifest = KeyManifest.load(manifestFile);
        List<KeyManifest.Entry> entries = manifest.refresh(files);

        List<String> classpathOrder = classpathOrder(ctx);
        StringBuilder sb = new StringBuilder(1 << 20);
        sb.append("java=").append(System.getProperty("java.version", "")).append('\n');
        sb.append("classpath=").append(String.join(File.pathSeparator, classpathOrder)).append('\n');
        List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
        for (KeyManifest.Entry e : sorted) {
            sb.append(e.path()).append('|').append(e.size()).append('|')
                    .append(e.mtime()).append('|').append(e.sha256()).append('\n');
        }
        String canonical = sb.toString();
        String id = sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0, 32);
        try {
            manifest.save(manifestFile);
        } catch (IOException e) {
            AgentLog.fail("key manifest save failed", e);
        }
        long bytes = entries.stream().mapToLong(KeyManifest.Entry::size).sum();
        return new Result(id, canonical, entries.size(), bytes,
                (System.nanoTime() - t0) / 1_000_000);
    }

    static List<Path> collectFiles(RuntimeContext ctx) {
        TreeSet<Path> files = new TreeSet<>();
        Path mods = ctx.modsRoot();
        Set<String> enabled = readEnabledIds(mods.resolve("enabled_mods.json"));
        Map<String, Path> folders = scanModFolders(mods);
        if (enabled == null) enabled = folders.keySet();
        for (String id : enabled) {
            Path folder = folders.get(id);
            if (folder == null) continue;
            addTree(folder.resolve("src"), files);
            addTree(folder.resolve("jars"), files);
            addTree(folder.resolve("data/scripts"), files);
            addFile(folder.resolve("mod_info.json"), files);
            try (Stream<Path> s = Files.list(folder)) {
                s.filter(p -> p.getFileName().toString().toLowerCase(Locale.ROOT)
                                .endsWith(".jar"))
                        .forEach(p -> addFile(p, files));
            } catch (IOException ignored) {
            }
        }
        addFile(mods.resolve("enabled_mods.json"), files);
        addTree(ctx.gameRoot().resolve("starsector-core/data/scripts"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.jar"), files);
        for (String cp : classpathOrder(ctx)) addFile(Path.of(cp), files);
        return new ArrayList<>(files);
    }

    private static List<String> classpathOrder(RuntimeContext ctx) {
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

    private static void addTree(Path root, Set<Path> out) {
        if (!Files.isDirectory(root)) return;
        try (Stream<Path> s = Files.walk(root)) {
            s.filter(Files::isRegularFile)
                    .filter(p -> {
                        String n = p.getFileName().toString().toLowerCase(Locale.ROOT);
                        return n.endsWith(".java") || n.endsWith(".jar")
                                || n.equals("mod_info.json");
                    })
                    .forEach(p -> addFile(p, out));
        } catch (IOException e) {
            AgentLog.fail("walk failed: " + root, e);
        }
    }

    private static void addFile(Path p, Set<Path> out) {
        if (p != null && Files.isRegularFile(p)) out.add(p.toAbsolutePath().normalize());
    }

    private static Set<String> readEnabledIds(Path file) {
        if (!Files.isRegularFile(file)) return null;
        Set<String> ids = new TreeSet<>();
        try {
            JSONObject o = new JSONObject(Files.readString(file));
            JSONArray a = o.optJSONArray("enabledMods");
            if (a != null) {
                for (int i = 0; i < a.length(); i++) ids.add(a.getString(i));
            }
        } catch (Throwable t) {
            AgentLog.fail("enabled_mods parse failed: " + file, t);
            return null;
        }
        return ids;
    }

    private static Map<String, Path> scanModFolders(Path mods) {
        Map<String, Path> map = new TreeMap<>();
        if (!Files.isDirectory(mods)) return map;
        try (Stream<Path> s = Files.list(mods)) {
            s.filter(Files::isDirectory).forEach(dir -> {
                Path info = dir.resolve("mod_info.json");
                if (!Files.isRegularFile(info)) return;
                try {
                    JSONObject o = new JSONObject(Files.readString(info));
                    String id = o.optString("id", "");
                    if (!id.isBlank()) map.put(id, dir);
                } catch (Throwable ignored) {
                }
            });
        } catch (IOException e) {
            AgentLog.fail("mod scan failed", e);
        }
        return map;
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
