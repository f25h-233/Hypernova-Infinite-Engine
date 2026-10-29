package hypernova.agent;

import java.nio.file.Files;
import java.nio.file.Path;

public final class RuntimeContext {
    private final Path gameRoot;
    private final Path modsRoot;
    private final Path savesRoot;
    private final Path cacheRoot;
    private final Path logFile;
    private final Path telemetryFile;
    private final ScriptCacheConfig config;
    private final AgentTelemetry telemetry;

    public RuntimeContext(Path gameRoot, Path modsRoot, Path savesRoot, Path cacheRoot,
                          Path logFile, Path telemetryFile, ScriptCacheConfig config) {
        this.gameRoot = gameRoot;
        this.modsRoot = modsRoot;
        this.savesRoot = savesRoot;
        this.cacheRoot = cacheRoot;
        this.logFile = logFile;
        this.telemetryFile = telemetryFile;
        this.config = config;
        this.telemetry = new AgentTelemetry(telemetryFile);
    }

    public static RuntimeContext fromEnvironment() {
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path mods = resolve("com.fs.starfarer.settings.paths.mods", cwd, gameRoot.resolve("mods"));
        Path saves = resolve("com.fs.starfarer.settings.paths.saves", cwd, gameRoot.resolve("saves"));
        ScriptCacheConfig config = ScriptCacheConfig.load(locateConfig(gameRoot));
        Path hypernova = saves.resolve("hypernova");
        return new RuntimeContext(gameRoot, mods, saves,
                hypernova.resolve("scripts-cache"),
                hypernova.resolve("scripts-agent.log"),
                hypernova.resolve("scripts-telemetry.jsonl"),
                config);
    }

    private static Path resolve(String prop, Path cwd, Path fallback) {
        String v = System.getProperty(prop);
        Path p = (v == null || v.isBlank()) ? fallback : Path.of(v);
        if (!p.isAbsolute()) p = cwd.resolve(p);
        return p.normalize();
    }

    private static Path locateConfig(Path gameRoot) {
        try {
            var src = HypernovaAgent.class.getProtectionDomain().getCodeSource();
            if (src != null && src.getLocation() != null) {
                Path jar = Path.of(src.getLocation().toURI());
                Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
                if (modRoot != null) {
                    Path f = modRoot.resolve("data/config/hypernova/hypernova.json");
                    if (Files.isRegularFile(f)) return f;
                }
            }
        } catch (Throwable ignored) {
        }
        Path f = gameRoot.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        return Files.isRegularFile(f) ? f : null;
    }

    public Path gameRoot() { return gameRoot; }
    public Path modsRoot() { return modsRoot; }
    public Path savesRoot() { return savesRoot; }
    public Path cacheRoot() { return cacheRoot; }
    public Path logFile() { return logFile; }
    public Path telemetryFile() { return telemetryFile; }
    public ScriptCacheConfig config() { return config; }
    public AgentTelemetry telemetry() { return telemetry; }
}
