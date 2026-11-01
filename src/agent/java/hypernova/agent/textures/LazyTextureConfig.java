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
 * <mod>/data/config/hypernova/lazy-skip-v1.txt.
 */
public record LazyTextureConfig(boolean enabled, boolean probe, Path skipFile) {

    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy"),
                System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                locateConfig());
    }

    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, Path configFile) {
        boolean enabled = enabledProp != null && !enabledProp.isBlank()
                ? Boolean.parseBoolean(enabledProp) : configEnabled(configFile);
        boolean probe = probeProp != null && Boolean.parseBoolean(probeProp);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null) {
            Path modRoot = modRoot(configFile);
            if (modRoot != null) {
                skip = modRoot.resolve("data/config/hypernova/lazy-skip-v1.txt");
            }
        }
        return new LazyTextureConfig(enabled, probe, skip);
    }

    private static boolean configEnabled(Path file) {
        if (file == null || !Files.isRegularFile(file)) return false;
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject textures = root.optJSONObject("textures");
            JSONObject lazy = textures == null ? null : textures.optJSONObject("lazy");
            return lazy != null && lazy.optBoolean("enabled", false);
        } catch (Throwable t) {
            return false; // bad config must not enable lazy loading
        }
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
