package hypernova.config;

import org.json.JSONObject;

public record HypernovaConfig(
        boolean enabled,
        boolean eviction,
        int frameBudgetMicros,
        int telemetryBufferLines,
        int heartbeatFrames,
        int startupProbePaths) {

    public static HypernovaConfig fromJson(JSONObject o) {
        return new HypernovaConfig(
                o.optBoolean("enabled", true),
                o.optBoolean("eviction", false),
                o.optInt("frame_budget_micros", 2000),
                o.optInt("telemetry_buffer_lines", 4096),
                // 原 verbose 开关只影响「是否记 hit」，而 hit 是命中率的核心指标，
                // 被它过滤会让 telemetry 失去意义（88a752d 已判定 hit 无条件记录）。
                // 该配置项因此改名为 heartbeat_frames：控制心跳日志频率（0 = 关闭）。
                o.optInt("heartbeat_frames", 3000),
                o.optInt("startup_probe_paths", 0));
    }
}
