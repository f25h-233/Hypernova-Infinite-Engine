package hypernova.adapter;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameTimeProbeTest {
    private static final long MS = 1_000_000L;
    private static final long T0 = 1_000L * MS;

    @Test
    void firstFrameOnlyStartsClock() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        assertTrue(p.line().contains("frames=0"));
        assertTrue(p.line().contains("over200=0"));
        assertTrue(p.line().contains("maxMs=0"));
    }

    @Test
    void countsNormalFramesAndP99() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        long now = T0;
        for (int i = 2; i <= 101; i++) {
            now += 16 * MS;
            p.frame(now, 0.016f + i * 0.001f);
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
        p.frame(T0, 0.016f);
        p.frame(T0 + 250 * MS, 0.017f);
        String line = p.line();
        assertTrue(line.contains("over200=1"), line);
        assertTrue(line.contains("maxMs=250"), line);
        assertTrue(line.contains("p99Ms=250"), line);
    }

    @Test
    void longGapIsExcludedFromFrames() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        p.frame(T0 + 6_001 * MS, 0.017f);
        String line = p.line();
        assertTrue(line.contains("frames=0"), line);
        assertTrue(line.contains("longGaps=1"), line);
        assertTrue(line.contains("maxMs=0"), line);
    }

    @Test
    void p99IsNotMax() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        long now = T0;
        for (int i = 0; i < 99; i++) {
            now += 10 * MS;
            p.frame(now, 0.017f + i * 0.001f);
        }
        now += 500 * MS;
        p.frame(now, 0.2f);
        String line = p.line();
        assertTrue(line.contains("frames=100"), line);
        assertTrue(line.contains("maxMs=500"), line);
        assertTrue(line.contains("p99Ms=10"), line);
    }

    @Test
    void duplicateAmountIsIgnored() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        p.frame(T0 + 250 * MS, 0.016f); // same engine frame, second entry
        p.frame(T0 + 251 * MS, 0.017f);
        String line = p.line();
        assertTrue(line.contains("frames=1"), line);
        assertTrue(line.contains("maxMs=251"), line);
        assertTrue(line.contains("over200=1"), line);
    }

    @Test
    void lineIsDueEveryConfiguredFrames() {
        FrameTimeProbe p = new FrameTimeProbe(2);
        p.frame(T0, 0.016f);
        p.frame(T0 + 16 * MS, 0.017f);
        assertNull(p.lineIfDue());
        p.frame(T0 + 32 * MS, 0.018f);
        String due = p.lineIfDue();
        assertNotNull(due);
        assertTrue(due.startsWith(FrameTimeProbe.LINE_PREFIX));
        assertTrue(due.contains("frames=2"));
        p.frame(T0 + 48 * MS, 0.019f);
        assertNull(p.lineIfDue());
    }

    @Test
    void nonPositiveDeltaIsIgnored() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        p.frame(T0, 0.017f);
        p.frame(T0 - 5 * MS, 0.018f);
        assertTrue(p.line().contains("frames=0"));
    }

    @Test
    void exactly200MsIsNotStutter() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        p.frame(T0 + 200 * MS, 0.017f);
        String line = p.line();
        assertTrue(line.contains("over200=0"), line);
        assertTrue(line.contains("maxMs=200"), line);
    }

    @Test
    void exactly5sIsStillAFrame() {
        FrameTimeProbe p = new FrameTimeProbe(600);
        p.frame(T0, 0.016f);
        p.frame(T0 + 5_000 * MS, 0.017f);
        String line = p.line();
        assertTrue(line.contains("frames=1"), line);
        assertTrue(line.contains("longGaps=0"), line);
        assertTrue(line.contains("maxMs=5000"), line);
    }
}
