package hypernova.agent.textures;

import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/**
 * Immutable path -> (w,h[,absPath,ddsPath,baked]) index.
 *
 * <p>v1: 3 tab-separated columns. v2: 6 columns
 * (path, w, h, absPath, ddsPath, baked). The optional generation header
 * "# generation=<sha256>" is the runtime manifest hash (Task 0 checks it).
 */
public final class LazySkipIndex {
    public record Entry(int w, int h, String absPath, String ddsPath, boolean baked) {
        public boolean hasDds() {
            return ddsPath != null && !ddsPath.isBlank();
        }
    }

    private final Map<String, Entry> byPath;
    private final int invalid;
    private final long loadMillis;
    private final String generation;

    private LazySkipIndex(Map<String, Entry> byPath, int invalid, long loadMillis,
                          String generation) {
        this.byPath = byPath;
        this.invalid = invalid;
        this.loadMillis = loadMillis;
        this.generation = generation;
    }

    public static LazySkipIndex load(Path file) throws Exception {
        long t0 = System.nanoTime();
        Map<String, Entry> map = new HashMap<>(1 << 17);
        int invalid = 0;
        String generation = null;
        try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) continue;
                if (line.charAt(0) == '#') {
                    if (line.startsWith("# generation=")) {
                        generation = line.substring("# generation=".length()).trim();
                    }
                    continue;
                }
                String[] parts = line.split("\t", -1);
                if (parts.length < 3 || parts[0].isEmpty()) {
                    invalid++;
                    continue;
                }
                try {
                    int w = Integer.parseInt(parts[1]);
                    int h = Integer.parseInt(parts[2]);
                    if (w <= 0 || h <= 0) {
                        invalid++;
                        continue;
                    }
                    String abs = parts.length >= 4 && !parts[3].isEmpty() ? parts[3] : null;
                    String dds = parts.length >= 5 && !parts[4].isEmpty() ? parts[4] : null;
                    boolean baked = parts.length >= 6
                            && ("1".equals(parts[5]) || "true".equalsIgnoreCase(parts[5]));
                    map.put(parts[0], new Entry(w, h, abs, dds, baked));
                } catch (NumberFormatException e) {
                    invalid++;
                }
            }
        }
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        return new LazySkipIndex(map, invalid, ms, generation);
    }

    public boolean contains(String path) {
        return path != null && byPath.containsKey(path);
    }

    public Entry get(String path) {
        return byPath.get(path);
    }

    public int size() {
        return byPath.size();
    }

    public int invalid() {
        return invalid;
    }

    public long loadMillis() {
        return loadMillis;
    }

    public String generation() {
        return generation;
    }
}
