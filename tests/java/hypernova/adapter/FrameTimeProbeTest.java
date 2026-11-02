package hypernova.adapter;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameTimeProbeTest {
    private static final long MS = 1_000_000L;
    private static final long T0 = 1_000L * MS;

    @Test
    void firstFrameOnlyStartsClock() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        assertTrue(p.line().contains("frames=0"));
        assertTrue(p.line().contains("over200=0"));
        assertTrue(p.line().contains("maxMs=0"));
    }

    @Test
    void countsNormalFramesAndP99() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        long now = T0;
        for (int i = 2; i <= 101; i++) {
            now += 16 * MS;
            p.frame(now, i);
        }
        String line = p.line();
        assertTrue(line.contains("frames=100"), line);
        assertTrue(line.contains("over200=0"), line);
        assertTrue(line.contains("maxMs=16"), line);
        assertTrue(line.contains("p99Ms=16"), line);
    }

    @Test
    void stutterOver200IsCounted() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        p.frame(T0 + 250 * MS, 2);
        String line = p.line();
        assertTrue(line.contains("over200=1"), line);
        assertTrue(line.contains("maxMs=250"), line);
        assertTrue(line.contains("p99Ms=250"), line);
    }

    @Test
    void longGapIsExcludedFromFrames() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        p.frame(T0 + 6_000 * MS, 2);
        String line = p.line();
        assertTrue(line.contains("frames=0"), line);
        assertTrue(line.contains("longGaps=1"), line);
        assertTrue(line.contains("maxMs=0"), line);
    }

    @Test
    void p99IsNotMax() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        long now = T0;
        for (int i = 0; i < 98; i++) {
            now += 10 * MS;
            p.frame(now, i + 2);
        }
        for (int i = 0; i < 2; i++) {
            now += 500 * MS;
            p.frame(now, i + 100);
        }
        String line = p.line();
        assertTrue(line.contains("frames=100"), line);
        assertTrue(line.contains("maxMs=500"), line);
        assertTrue(line.contains("p99Ms=500"), line);
    }

    @Test
    void duplicateTickIsIgnored() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 7);
        p.frame(T0 + 250 * MS, 7); // 长帧后同 tick 的第二入口
        p.frame(T0 + 251 * MS, 8);
        String line = p.line();
        assertTrue(line.contains("frames=1"), line);
        assertTrue(line.contains("maxMs=251"), line);
        assertTrue(line.contains("over200=1"), line);
    }

    @Test
    void lineIsDueEveryConfiguredFrames() {
        FrameTimeProbe p = new FrameTimeProbe(2);
        p.frame(T0, 1);
        p.frame(T0 + 16 * MS, 2);
        assertNull(p.lineIfDue());
        p.frame(T0 + 32 * MS, 3);
        String due = p.lineIfDue();
        assertNotNull(due);
        assertTrue(due.startsWith(FrameTimeProbe.LINE_PREFIX));
        assertTrue(due.contains("frames=2"));
        p.frame(T0 + 48 * MS, 4);
        assertNull(p.lineIfDue());
    }

    @Test
    void nonPositiveDeltaIsIgnored() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 1);
        p.frame(T0, 2);
        p.frame(T0 - 5 * MS, 3);
        assertTrue(p.line().contains("frames=0"));
    }
}
