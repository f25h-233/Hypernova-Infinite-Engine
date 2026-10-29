package hypernova.agent;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

public record ScriptCacheConfig(boolean scriptsEnabled, long cacheMaxBytes, int cacheGenerations,
                                long preloadMaxMillis, boolean verbose) {

    public static ScriptCacheConfig load(Path file) {
        if (file == null || !Files.isRegularFile(file)) return disabled();
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject s = root.optJSONObject("scripts");
            if (s == null) {
                // agent 已安装但配置没有 scripts 段：默认开启；显式 enabled=false 才关闭
                return new ScriptCacheConfig(true, 2L << 30, 2, 3000, false);
            }
            return new ScriptCacheConfig(
                    s.optBoolean("enabled", true),
                    Math.max(0, s.optLong("cache_max_bytes", 2L << 30)),
                    Math.max(1, s.optInt("cache_generations", 2)),
                    Math.max(250, s.optLong("preload_max_millis", 3000)),
                    s.optBoolean("verbose", false));
        } catch (Throwable t) {
            AgentLog.fail("scripts config parse failed: " + file, t);
            return disabled();
        }
    }

    public static ScriptCacheConfig disabled() {
        return new ScriptCacheConfig(false, 0, 1, 250, false);
    }
}
