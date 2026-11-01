package hypernova.agent.textures;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Lazy-texture configuration.
 *
 * <p>enabled: textures.lazy.enabled in hypernova.json (default false) or
 * -Dhypernova.textures.lazy=true. probe: -Dhypernova.textures.lazy.probe=true
 * (debug only; never skips). skipFile: -Dhypernova.textures.lazy.skipFile, or
 * the installed lazy-skip-v2.txt / lazy-skip-v1.txt. manifestFile: the runtime
 * manifest whose sha256 the skip generation header must match.
 *
 * <p>M2.6 knobs default off/on as follows: dds=true (only when lazy is on),
 * eviction=false, budget=256 MB, grace=10 s, scene delay=2 s, max=64/pass.
 */
public record LazyTextureConfig(
        boolean enabled,
        boolean probe,
        Path skipFile,
        Path manifestFile,
        boolean dds,
        boolean eviction,
        int evictionBudgetMb,
        int evictionGraceMs,
        int evictionSceneDelayMs,
        int evictionMaxPerPass,
        boolean selftest) {

    private static final int DEFAULT_BUDGET_MB = 256;
    private static final int DEFAULT_GRACE_MS = 10_000;
    private static final int DEFAULT_SCENE_DELAY_MS = 2_000;
    private static final int DEFAULT_MAX_PER_PASS = 64;

    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy"),
                System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                System.getProperty("hypernova.textures.lazy.manifestFile"),
                System.getProperty("hypernova.textures.lazy.dds"),
                System.getProperty("hypernova.textures.lazy.eviction"),
                System.getProperty("hypernova.textures.lazy.eviction.budgetMb"),
                System.getProperty("hypernova.textures.lazy.eviction.graceMs"),
                System.getProperty("hypernova.textures.lazy.eviction.sceneDelayMs"),
                System.getProperty("hypernova.textures.lazy.eviction.maxPerPass"),
                System.getProperty("hypernova.textures.lazy.selftest"),
                locateConfig());
    }

    /** M2.5 four-argument seam; new knobs keep their defaults. */
    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, Path configFile) {
        return load(enabledProp, probeProp, skipProp, null, null, null,
                null, null, null, null, null, configFile);
    }

    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, String manifestProp,
                                         String ddsProp, String evictionProp,
                                         String budgetProp, String graceProp,
                                         String delayProp, String maxProp,
                                         String selftestProp, Path configFile) {
        JSONObject lazy = lazyJson(configFile);
        JSONObject eviction = lazy == null ? null : lazy.optJSONObject("eviction");
        Path modRoot = modRoot(configFile);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null && modRoot != null) {
            Path dir = modRoot.resolve("data/config/hypernova");
            Path v2 = dir.resolve("lazy-skip-v2.txt");
            skip = Files.isRegularFile(v2) ? v2 : dir.resolve("lazy-skip-v1.txt");
        }
        Path manifest;
        if (manifestProp != null && !manifestProp.isBlank()) {
            manifest = Path.of(manifestProp);
        } else {
            manifest = skip == null || skip.getParent() == null
                    ? null : skip.getParent().resolve("manifest-v1.json");
        }
        return new LazyTextureConfig(
                bool(enabledProp, lazy, "enabled", false),
                bool(probeProp, lazy, "probe", false),
                skip,
                manifest,
                bool(ddsProp, lazy, "dds", true),
                bool(evictionProp, eviction, "enabled", false),
                integer(budgetProp, eviction, "budget_mb", DEFAULT_BUDGET_MB),
                integer(graceProp, eviction, "grace_ms", DEFAULT_GRACE_MS),
                integer(delayProp, eviction, "scene_delay_ms", DEFAULT_SCENE_DELAY_MS),
                integer(maxProp, eviction, "max_per_pass", DEFAULT_MAX_PER_PASS),
                bool(selftestProp, lazy, "selftest", false));
    }

    private static JSONObject lazyJson(Path file) {
        if (file == null || !Files.isRegularFile(file)) return null;
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject textures = root.optJSONObject("textures");
            return textures == null ? null : textures.optJSONObject("lazy");
        } catch (Throwable t) {
            return null; // bad config must not enable lazy loading
        }
    }

    private static boolean bool(String prop, JSONObject o, String key, boolean def) {
        if (prop != null && !prop.isBlank()) return Boolean.parseBoolean(prop);
        return o == null ? def : o.optBoolean(key, def);
    }

    private static int integer(String prop, JSONObject o, String key, int def) {
        if (prop != null && !prop.isBlank()) {
            try {
                return Integer.parseInt(prop.trim());
            } catch (NumberFormatException e) {
                return def;
            }
        }
        return o == null ? def : o.optInt(key, def);
    }

    private static Path locateConfig() {
        try {
            var src = LazyTextureConfig.class.getProtectionDomain().getCodeSource();
            if (src != null && src.getLocation() != null) {
                Path jar = Path.of(src.getLocation().toURI());
                Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
                if (modRoot != null) {
                    Path f = modRoot.resolve("data/config/hypernova/hypernova.json");
                    if (Files.isRegularFile(f)) return f;
                }
            }
        } catch (Throwable ignored) {
            // fall through to game-root lookup
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path f = gameRoot.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        return Files.isRegularFile(f) ? f : null;
    }

    private static Path modRoot(Path configFile) {
        if (configFile != null) {
            Path p = configFile.getParent(); // hypernova
            for (int i = 0; i < 3 && p != null; i++) p = p.getParent(); // config, data, mod root
            if (p != null) return p;
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path mod = gameRoot.resolve("mods/hypernova_infinite_engine");
        return Files.isDirectory(mod) ? mod : null;
    }
}
