package hypernova.agent;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Agent-side per-frame timer for the M4 A→B/stutter gate.
 *
 * <p>Injected into {@code org.lwjgl.opengl.Display.update(Z)V} only, the
 * per-frame buffer swap used by the title/campaign/combat loops.
 * {@code update()V} delegates to {@code update(Z)V} and is not patched, so
 * each frame is sampled once. Enabled only by
 * {@code -Dhypernova.frameProbe=true}; independent of lazy textures,
 * FR and the scripts cache.
 *
 * <p>Gaps &gt; 5 s are counted as {@code longGaps} and excluded from frames,
 * max and the histogram (pause/load/alt-tab). P99 is a 1 ms histogram
 * estimate. A line is logged every 600 valid frames.
 */
public final class FrameProbe {
    public static final String LINE_PREFIX = "HYPERNOVA_FRAME ";
    public static final long STUTTER_NANOS = 200_000_000L;
    public static final long MAX_GAP_NANOS = 5_000_000_000L;
    static final int MAX_BUCKET_MS = 1000;

    private static final int LOG_EVERY_FRAMES = 600;
    private static final State STATE = new State(LOG_EVERY_FRAMES);
    private static final Set<String> FIRST_SOURCES = ConcurrentHashMap.newKeySet();

    private FrameProbe() {
    }

    /** Called from the injected bytecode at the start of a frame. */
    public static void frame(String source) {
        if (FIRST_SOURCES.add(source)) {
            AgentLog.info("frame probe: samples started from " + source);
        }
        String line = STATE.sample(System.nanoTime());
        if (line != null) {
            AgentLog.info(line);
        }
    }

    static final class State {
        private final int logEveryFrames;
        private final long[] buckets = new long[MAX_BUCKET_MS + 1];
        private boolean hasLast;
        private long lastNanos;
        private long frames;
        private long over200;
        private long longGaps;
        private long maxNanos;
        private long lastDeltaNanos;
        private long framesAtLastLine = 0L;

        State(int logEveryFrames) {
            this.logEveryFrames = Math.max(1, logEveryFrames);
        }

        synchronized String sample(long nowNanos) {
            if (!hasLast) {
                hasLast = true;
                lastNanos = nowNanos;
                return null;
            }
            long delta = nowNanos - lastNanos;
            lastNanos = nowNanos;
            if (delta <= 0L) {
                return null;
            }
            if (delta > MAX_GAP_NANOS) {
                longGaps++;
                return null;
            }
            frames++;
            lastDeltaNanos = delta;
            if (delta > maxNanos) {
                maxNanos = delta;
            }
            if (delta > STUTTER_NANOS) {
                over200++;
            }
            long ms = (delta + 999_999L) / 1_000_000L;
            buckets[(int) Math.min(ms, MAX_BUCKET_MS)]++;
            if (frames - framesAtLastLine < logEveryFrames) {
                return null;
            }
            framesAtLastLine = frames;
            return line();
        }

        synchronized String line() {
            return LINE_PREFIX
                    + "frames=" + frames
                    + " over200=" + over200
                    + " maxMs=" + millisCeil(maxNanos)
                    + " p99Ms=" + p99Millis()
                    + " lastMs=" + millisCeil(lastDeltaNanos)
                    + " longGaps=" + longGaps;
        }

        private long p99Millis() {
            if (frames == 0) {
                return 0;
            }
            long need = (frames * 99L + 99L) / 100L;
            long seen = 0;
            for (int i = 0; i < buckets.length; i++) {
                seen += buckets[i];
                if (seen >= need) {
                    return i;
                }
            }
            return MAX_BUCKET_MS;
        }

        private static long millisCeil(long nanos) {
            return (nanos + 999_999L) / 1_000_000L;
        }
    }
}
