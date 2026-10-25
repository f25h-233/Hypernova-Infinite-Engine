package hypernova.config;

import org.json.JSONObject;

public record HypernovaConfig(
        boolean enabled,
        boolean eviction,
        int frameBudgetMicros,
        int telemetryBufferLines,
        boolean verbose) {

    public static HypernovaConfig fromJson(JSONObject o) {
        return new HypernovaConfig(
                o.optBoolean("enabled", true),
                o.optBoolean("eviction", false),
                o.optInt("frame_budget_micros", 2000),
                o.optInt("telemetry_buffer_lines", 4096),
                o.optBoolean("verbose", false));
    }
}
