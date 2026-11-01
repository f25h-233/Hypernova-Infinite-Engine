package hypernova.agent.textures;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Task 1 probe configuration. Production skip mode is added by the M2.5
 * addendum (textures.lazy.enabled, default false); the probe is debug-only.
 */
public record LazyTextureConfig(boolean probe, Path skipFile) {

    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                locateConfig());
    }

    public static LazyTextureConfig load(String probeProp, String skipProp, Path configFile) {
        boolean probe = probeProp != null && Boolean.parseBoolean(probeProp);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null) {
            Path modRoot = modRoot(configFile);
            if (modRoot != null) {
                skip = modRoot.resolve("data/config/hypernova/lazy-skip-v1.txt");
            }
        }
        return new LazyTextureConfig(probe, skip);
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
