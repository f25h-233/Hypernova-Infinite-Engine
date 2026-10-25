package hypernova.telemetry;

import org.json.JSONObject;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JsonlTelemetryTest {

    static final class CaptureSink implements TelemetrySink {
        final List<String> names = new ArrayList<>();
        final List<String> contents = new ArrayList<>();

        @Override
        public void write(String name, String content) {
            names.add(name);
            contents.add(content);
        }
    }

    @Test
    void bufferThenFlushWritesOneLinePerEvent() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, false);
        t.event("loaded", "graphics/ui/a.png", 1234L, "core");
        t.event("miss", "graphics/ui/b.png", 2L, "not-in-manifest");
        assertEquals(2, t.buffered());
        t.flush();
        assertEquals(0, t.buffered());
        assertEquals(List.of("hypernova/telemetry.jsonl"), sink.names);
        String[] lines = sink.contents.get(0).split("\n");
        assertEquals(2, lines.length);
        JSONObject first = new JSONObject(lines[0]);
        assertEquals("loaded", first.getString("kind"));
        assertEquals("graphics/ui/a.png", first.getString("path"));
        assertEquals(1234L, first.getLong("nanos"));
        assertEquals("core", first.getString("detail"));
    }

    @Test
    void dropsOldestHalfWhenFull() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 4, false);
        for (int i = 0; i < 6; i++) {
            t.event("loaded", "p" + i, 0L, "");
        }
        assertTrue(t.buffered() <= 4);
        t.flush();
        String content = sink.contents.get(0);
        assertTrue(content.contains("p5"));
        assertFalse(content.contains("\"p0\""));
    }

    @Test
    void longPathIsTruncated() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, false);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 5000; i++) {
            sb.append('x');
        }
        t.event("loaded", sb.toString(), 0L, "");
        t.flush();
        String line = sink.contents.get(0).trim();
        assertTrue(line.length() < 12000);
    }

    @Test
    void sinkFailureIsSwallowed() throws Exception {
        TelemetrySink failing = (name, content) -> {
            throw new java.io.IOException("disk full");
        };
        JsonlTelemetry t = new JsonlTelemetry(failing, 100, false);
        t.event("loaded", "a", 0L, "");
        assertDoesNotThrow(t::flush);
    }
}
