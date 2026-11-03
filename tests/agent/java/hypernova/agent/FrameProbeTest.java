package hypernova.agent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeTest {
    private static final long MS = 1_000_000L;
    private static final long T0 = 1_000L * MS;

    @Test
    void firstCallStartsClock() {
        FrameProbe.State s = new FrameProbe.State(600);
        assertNull(s.sample(T0));
        assertTrue(s.line().contains("frames=0"));
    }

    @Test
    void countsFramesAndP99() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        long now = T0;
        for (int i = 0; i < 100; i++) {
            now += 16 * MS;
            s.sample(now);
        }
        String line = s.line();
        assertTrue(line.contains("frames=100"), line);
        assertTrue(line.contains("over200=0"), line);
        assertTrue(line.contains("maxMs=16"), line);
        assertTrue(line.contains("p99Ms=16"), line);
    }

    @Test
    void countsStutterAndExactBoundaries() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        s.sample(T0 + 200 * MS);
        assertTrue(s.line().contains("over200=0"));
        s.sample(T0 + 450 * MS);
        assertTrue(s.line().contains("over200=1"));
        assertTrue(s.line().contains("maxMs=250"));
    }

    @Test
    void longGapIsExcluded() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        s.sample(T0 + 5_000 * MS);
        assertTrue(s.line().contains("frames=1"));
        assertTrue(s.line().contains("longGaps=0"));
        s.sample(T0 + 5_000 * MS + 6_000 * MS);
        assertTrue(s.line().contains("longGaps=1"));
    }

    @Test
    void lineIsDueEveryConfiguredFrames() {
        FrameProbe.State s = new FrameProbe.State(2);
        s.sample(T0);
        s.sample(T0 + 16 * MS);
        assertNull(s.sample(T0 + 32 * MS));
        String due = s.sample(T0 + 48 * MS);
        assertNotNull(due);
        assertTrue(due.startsWith(FrameProbe.LINE_PREFIX));
        assertTrue(due.contains("frames=3"));
    }
}
