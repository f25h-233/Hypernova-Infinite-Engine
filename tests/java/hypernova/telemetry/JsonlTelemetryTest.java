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
        JSONObject parsed = new JSONObject(line);
        assertEquals(1024, parsed.getString("path").length());
    }

    @Test
    void hitIsRecordedEvenWhenNotVerbose() throws Exception {
        // 冒烟实测纠正：hit 曾被 verbose 过滤，导致「loaded=91 但缓冲为空」，
        // 命中率完全不可观测。hit 与 loaded 合计才等于本组件确保加载过的总量，
        // 所以过滤 hit 等于把 REQ-R1-06 的核心指标丢掉。
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, false);
        t.event("hit", "graphics/ui/a.png", 1L, "core");
        assertEquals(1, t.buffered());
        t.event("miss", "graphics/ui/b.png", 2L, "");
        assertEquals(2, t.buffered());
        t.flush();
        String content = sink.contents.get(0);
        assertTrue(content.contains("\"hit\""));
        assertTrue(content.contains("\"miss\""));
    }

    @Test
    void hitIsRecordedWhenVerbose() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, true);
        t.event("hit", "graphics/ui/a.png", 1L, "core");
        assertEquals(1, t.buffered());
        t.flush();
        JSONObject parsed = new JSONObject(sink.contents.get(0).trim());
        assertEquals("hit", parsed.getString("kind"));
    }

    @Test
    void eventCarriesThreadName() throws Exception {
        // REQ-R1-06 要求记录线程名（I5）
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, false);
        t.event("loaded", "a.png", 0L, "");
        t.flush();
        JSONObject parsed = new JSONObject(sink.contents.get(0).trim());
        assertEquals(Thread.currentThread().getName(), parsed.getString("thread"));
    }

    @Test
    void secondFlushKeepsEarlierLines() throws Exception {
        // I4：writeTextFileToCommon 是整文件覆盖写，flush 必须重写全量历史。
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100, false);
        t.event("loaded", "first.png", 0L, "");
        t.flush();
        t.event("loaded", "second.png", 0L, "");
        t.flush();
        String second = sink.contents.get(1);
        assertTrue(second.contains("first.png"), "第二次 flush 丢失了第一次的结果");
        assertTrue(second.contains("second.png"));
        assertEquals(2, t.writtenTotal());
    }

    @Test
    void writesAreCappedAndReportTruncation() throws Exception {
        // I4 上限：字符预算超限时丢弃最旧的一半，并留一条 telemetry-truncated。
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100_000, false);
        // 用超长 path 逼字符预算先于行数上限触发（每条 ~1000 字符）。
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 1000; i++) {
            sb.append('x');
        }
        for (int i = 0; i < 2000; i++) {
            t.event("loaded", i + sb.toString(), 0L, "");
        }
        t.flush();
        String content = sink.contents.get(0);
        assertTrue(content.length() <= JsonlTelemetry.MAX_WRITTEN_CHARS + 4096,
                "单次写入超过字符预算: " + content.length());
        assertTrue(content.contains("telemetry-truncated"), "截断后必须留说明行");
        assertTrue(t.droppedTotal() > 0);
        assertTrue(t.writtenTotal() <= JsonlTelemetry.MAX_WRITTEN_LINES);
    }

    @Test
    void truncationIsNotRepeatedForever() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 100_000, false);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 1000; i++) {
            sb.append('y');
        }
        for (int i = 0; i < 2000; i++) {
            t.event("loaded", i + sb.toString(), 0L, "");
        }
        t.flush();
        t.flush(); // 第二次没有新事件：buffer 为空，不写
        assertEquals(1, sink.contents.size());
    }

    @Test
    void maxLinesOneStillTrims() throws Exception {
        CaptureSink sink = new CaptureSink();
        JsonlTelemetry t = new JsonlTelemetry(sink, 1, false);
        t.event("loaded", "a", 0L, "");
        t.event("loaded", "b", 0L, "");
        t.event("loaded", "c", 0L, "");
        assertTrue(t.buffered() <= 1);
        t.flush();
        String content = sink.contents.get(0);
        assertTrue(content.contains("\"c\""));
        assertFalse(content.contains("\"a\""));
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
