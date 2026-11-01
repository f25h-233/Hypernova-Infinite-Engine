package hypernova.agent.textures;

import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/** Immutable path -> (w,h) index generated from the runtime manifest. */
public final class LazySkipIndex {
    public record Dim(int w, int h) {
    }

    private final Map<String, Dim> byPath;
    private final int invalid;
    private final long loadMillis;
    private final String generation;

    private LazySkipIndex(Map<String, Dim> byPath, int invalid, long loadMillis,
                          String generation) {
        this.byPath = byPath;
        this.invalid = invalid;
        this.loadMillis = loadMillis;
        this.generation = generation;
    }

    public static LazySkipIndex load(Path file) throws Exception {
        long t0 = System.nanoTime();
        Map<String, Dim> map = new HashMap<>(1 << 17);
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
                int t1 = line.indexOf('\t');
                int t2 = t1 < 0 ? -1 : line.indexOf('\t', t1 + 1);
                if (t1 <= 0 || t2 <= t1) {
                    invalid++;
                    continue;
                }
                try {
                    int w = Integer.parseInt(line.substring(t1 + 1, t2));
                    int h = Integer.parseInt(line.substring(t2 + 1));
                    if (w <= 0 || h <= 0) {
                        invalid++;
                        continue;
                    }
                    map.put(line.substring(0, t1), new Dim(w, h));
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

    public Dim get(String path) {
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
