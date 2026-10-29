package hypernova.agent;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedWriter;
import java.io.Closeable;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class AgentTelemetry implements Closeable {
    private final BufferedWriter out;

    public AgentTelemetry(Path file) {
        BufferedWriter w = null;
        try {
            Files.createDirectories(file.getParent());
            w = Files.newBufferedWriter(file, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            AgentLog.fail("telemetry open failed: " + file, e);
        }
        this.out = w;
    }

    public synchronized void event(String kind, String key, long entries, long bytes, long millis) {
        // 游戏自带 json.jar 是 2010 版 org.json：JSONException 为 checked，put 声明抛出。
        try {
            JSONObject o = new JSONObject();
            o.put("t", System.currentTimeMillis());
            o.put("kind", kind);
            o.put("key", key);
            o.put("entries", entries);
            o.put("bytes", bytes);
            o.put("millis", millis);
            write(o);
        } catch (JSONException e) {
            AgentLog.fail("telemetry event failed", e);
        }
    }

    public synchronized void summary(String key, long hits, long misses, long findCalls,
                                     long spanMillis, long entries) {
        try {
            JSONObject o = new JSONObject();
            o.put("t", System.currentTimeMillis());
            o.put("kind", "summary");
            o.put("key", key);
            o.put("hits", hits);
            o.put("misses", misses);
            o.put("find_calls", findCalls);
            o.put("span_millis", spanMillis);
            o.put("entries", entries);
            o.put("hit_rate", findCalls == 0 ? 0.0 : (double) hits / findCalls);
            write(o);
        } catch (JSONException e) {
            AgentLog.fail("telemetry summary failed", e);
        }
    }

    private void write(JSONObject o) {
        if (out == null) return;
        try {
            out.write(o.toString());
            out.write('\n');
            out.flush();
        } catch (IOException e) {
            AgentLog.fail("telemetry write failed", e);
        }
    }

    @Override
    public synchronized void close() {
        if (out == null) return;
        try {
            out.close();
        } catch (IOException ignored) {
        }
    }
}
