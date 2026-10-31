package hypernova.agent;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Near-zero-overhead phase marks for the 0-50 s bucket.
 *
 * <p>Log line format is stable because tools/m3_phase.py parses it:
 * {@code timeline: <name> rel_ms=<n> epoch_ms=<n>}.
 *
 * <p>This class must never throw into the game. Marks are used for measurement
 * only; losing one must not change startup behavior.
 */
public final class StartupTimeline {
    private static final AtomicLong START_NANOS = new AtomicLong();
    private static final AtomicLong START_EPOCH = new AtomicLong();
    private static final List<String> MARKS =
            Collections.synchronizedList(new ArrayList<>());

    private StartupTimeline() {
    }

    /** Called once from premain, after AgentLog.init(). */
    public static void start() {
        START_EPOCH.compareAndSet(0, System.currentTimeMillis());
        START_NANOS.compareAndSet(0, System.nanoTime());
    }

    public static void mark(String name) {
        try {
            long startN = START_NANOS.get();
            if (startN == 0) return;
            long relMs = (System.nanoTime() - startN) / 1_000_000;
            MARKS.add(name);
            AgentLog.info("timeline: " + name + " rel_ms=" + relMs
                    + " epoch_ms=" + System.currentTimeMillis());
        } catch (Throwable ignored) {
            // measurement must never affect startup
        }
    }

    static List<String> marksForTest() {
        synchronized (MARKS) {
            return new ArrayList<>(MARKS);
        }
    }

    static void resetForTest() {
        MARKS.clear();
        START_NANOS.set(0);
        START_EPOCH.set(0);
    }
}
