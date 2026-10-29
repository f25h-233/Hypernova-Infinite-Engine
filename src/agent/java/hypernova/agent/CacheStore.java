package hypernova.agent;

import java.io.IOException;
import java.nio.file.attribute.FileTime;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public final class CacheStore {
    private final Path root;
    private final int maxGenerations;
    private final long maxBytes;

    public CacheStore(Path root, int maxGenerations, long maxBytes) {
        this.root = root;
        this.maxGenerations = Math.max(1, maxGenerations);
        this.maxBytes = Math.max(0, maxBytes);
    }

    public CachePack.Pack load(String key) {
        Path pack = root.resolve(key).resolve("classes.pack");
        if (!Files.isRegularFile(pack)) return null;
        CachePack.Pack p = CachePack.read(pack);
        if (p == null) {
            AgentLog.info("corrupt scripts cache ignored: " + pack);
            return null;
        }
        touch(key);
        return p;
    }

    public void save(String key, Map<String, byte[]> entries) throws IOException {
        Path dir = root.resolve(key);
        Files.createDirectories(dir);
        CachePack.write(dir.resolve("classes.pack"), entries);
        long bytes = entries.values().stream().mapToLong(a -> a.length).sum();
        String json = "{\"key\":\"" + key + "\",\"saved_at\":" + System.currentTimeMillis()
                + ",\"entries\":" + entries.size() + ",\"bytes\":" + bytes + "}\n";
        Files.writeString(dir.resolve("generation.json"), json);
        cleanup(key);
    }

    public List<String> generations() {
        List<String> out = new ArrayList<>();
        if (!Files.isDirectory(root)) return out;
        try (Stream<Path> s = Files.list(root)) {
            s.filter(Files::isDirectory).forEach(p -> out.add(p.getFileName().toString()));
        } catch (IOException e) {
            AgentLog.fail("cache list failed", e);
        }
        Collections.sort(out);
        return out;
    }

    private void touch(String key) {
        try {
            Path g = root.resolve(key).resolve("generation.json");
            if (Files.isRegularFile(g)) {
                Files.setLastModifiedTime(g, FileTime.fromMillis(System.currentTimeMillis()));
            }
        } catch (IOException ignored) {
        }
    }

    private void cleanup(String current) {
        try (Stream<Path> s = Files.list(root)) {
            List<Path> gens = s.filter(Files::isDirectory)
                    .filter(p -> !p.getFileName().toString().equals(current))
                    .sorted(Comparator.comparingLong(this::lastUsed).reversed())
                    .toList();
            int keep = maxGenerations - 1;
            for (int i = keep; i < gens.size(); i++) deleteTree(gens.get(i));
        } catch (IOException e) {
            AgentLog.fail("cache cleanup failed", e);
        }
        enforceSize(current);
    }

    private void enforceSize(String current) {
        if (maxBytes <= 0) return;
        try (Stream<Path> s = Files.list(root)) {
            List<Path> gens = s.filter(Files::isDirectory)
                    .filter(p -> !p.getFileName().toString().equals(current))
                    .sorted(Comparator.comparingLong(this::lastUsed))
                    .toList();
            long total = sizeOf(root);
            for (Path gen : gens) {
                if (total <= maxBytes) break;
                total -= sizeOf(gen);
                deleteTree(gen);
            }
        } catch (IOException e) {
            AgentLog.fail("cache size cleanup failed", e);
        }
    }

    private long lastUsed(Path dir) {
        try {
            return Files.getLastModifiedTime(dir.resolve("generation.json")).toMillis();
        } catch (IOException e) {
            return 0L;
        }
    }

    private static long sizeOf(Path dir) {
        try (Stream<Path> s = Files.walk(dir)) {
            return s.filter(Files::isRegularFile).mapToLong(p -> {
                try {
                    return Files.size(p);
                } catch (IOException e) {
                    return 0L;
                }
            }).sum();
        } catch (IOException e) {
            return 0L;
        }
    }

    private static void deleteTree(Path dir) {
        try (Stream<Path> s = Files.walk(dir)) {
            s.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                }
            });
        } catch (IOException ignored) {
        }
    }
}
