package hypernova.telemetry;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public final class JsonlTelemetry implements Telemetry {
    public static final String NAME = "hypernova/telemetry.jsonl";
    private static final int MAX_PATH_CHARS = 1024;

    private final TelemetrySink sink;
    private final int maxLines;
    private final boolean verbose;
    private final Deque<String> lines = new ArrayDeque<>();

    public JsonlTelemetry(TelemetrySink sink, int maxLines, boolean verbose) {
        this.sink = sink;
        this.maxLines = Math.max(1, maxLines);
        this.verbose = verbose;
    }

    @Override
    public void event(String kind, String path, long nanos, String detail) {
        if (!verbose && "hit".equals(kind)) {
            return;
        }
        JSONObject o = new JSONObject();
        try {
            o.put("t", System.currentTimeMillis());
            o.put("kind", kind);
            o.put("path", truncate(path));
            o.put("nanos", nanos);
            o.put("detail", detail == null ? "" : truncate(detail));
        } catch (JSONException ignored) {
            return; // 遥测失败绝不打断游戏（INV-05 的失败方向：静默）
        }
        synchronized (lines) {
            if (lines.size() >= maxLines) {
                int drop = maxLines / 2;
                for (int i = 0; i < drop && !lines.isEmpty(); i++) {
                    lines.pollFirst();
                }
            }
            lines.addLast(o.toString());
        }
    }

    private static String truncate(String s) {
        if (s == null) {
            return "";
        }
        return s.length() <= MAX_PATH_CHARS ? s : s.substring(0, MAX_PATH_CHARS);
    }

    @Override
    public void flush() {
        List<String> snapshot;
        synchronized (lines) {
            if (lines.isEmpty()) {
                return;
            }
            snapshot = new ArrayList<>(lines);
            lines.clear();
        }
        try {
            sink.write(NAME, String.join("\n", snapshot) + "\n");
        } catch (Exception ignored) {
            // 遥测失败绝不打断游戏（INV-05 的失败方向：静默）
        }
    }

    @Override
    public int buffered() {
        synchronized (lines) {
            return lines.size();
        }
    }
}
