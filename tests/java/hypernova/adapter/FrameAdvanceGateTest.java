package hypernova.adapter;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameAdvanceGateTest {

    private static final long WINDOW = 5_000_000L;

    @Test
    void secondEntryInSameFrameIsSkipped() {
        // I1 的原始证据：两个实例同帧推进，ticks 从 195 变 196 后第二个入口又跑了一遍。
        FrameAdvanceGate gate = new FrameAdvanceGate(WINDOW);
        Object scheduler = new Object();
        assertTrue(gate.shouldRun(scheduler, 195L, 0L));
        gate.completed(scheduler, 196L, 100_000L);
        // 日志实测：两次 advance 相隔 44 ms（跨帧，因为同帧第二个入口当时不存在门闩）。
        // 门闩只需要覆盖「同一帧内」的重复调用，这里用 44 µs 代表同帧。
        assertFalse(gate.shouldRun(scheduler, 196L, 144_000L),
                "同帧第二个入口（看到同样的 196 ticks）必须被跳过");
    }

    @Test
    void nextFrameIsAllowedEvenWithSameTicks() {
        // 引擎推进一帧但调度器恰好没 tick（例如 backlog 为空仍会计 ticks，这里模拟极端情况）：
        // 超过时间窗后必须放行，否则管线被永久锁死。
        FrameAdvanceGate gate = new FrameAdvanceGate(WINDOW);
        Object scheduler = new Object();
        assertTrue(gate.shouldRun(scheduler, 10L, 0L));
        gate.completed(scheduler, 10L, 0L);
        assertTrue(gate.shouldRun(scheduler, 10L, WINDOW), "超过时间窗必须放行");
    }

    @Test
    void newTicksAlwaysAllowed() {
        FrameAdvanceGate gate = new FrameAdvanceGate(WINDOW);
        Object scheduler = new Object();
        assertTrue(gate.shouldRun(scheduler, 10L, 0L));
        gate.completed(scheduler, 11L, 1L);
        assertTrue(gate.shouldRun(scheduler, 12L, 2L));
    }

    @Test
    void differentSchedulerResetsGate() {
        // 重新装配（新调度器）时不应继承旧门闩状态。
        FrameAdvanceGate gate = new FrameAdvanceGate(WINDOW);
        Object first = new Object();
        assertTrue(gate.shouldRun(first, 5L, 0L));
        gate.completed(first, 6L, 0L);
        assertFalse(gate.shouldRun(first, 6L, 1L));
        Object second = new Object();
        assertTrue(gate.shouldRun(second, 6L, 2L));
    }

    @Test
    void zeroWindowFailsOpen() {
        // minInterval=0：同 ticks 且「距上次 < 0」恒假 → 永远放行，
        // 这是刻意的 fail-open（宁可多跑一次也不能锁死管线）。
        FrameAdvanceGate gate = new FrameAdvanceGate(0L);
        Object scheduler = new Object();
        assertTrue(gate.shouldRun(scheduler, 1L, 0L));
        gate.completed(scheduler, 1L, 0L);
        assertTrue(gate.shouldRun(scheduler, 1L, 1L));
    }
}
