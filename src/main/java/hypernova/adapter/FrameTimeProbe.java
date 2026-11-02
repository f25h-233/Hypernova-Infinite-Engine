package hypernova.adapter;

/**
 * 主线程帧时间探针（默认关闭，M4 验收用）。
 *
 * <p>只在 {@code HypernovaCombatPlugin.advance} 通过 {@link FrameAdvanceGate}
 * 之后调用，并按引擎帧标识去重：{@code advance(float amount)} 的 {@code amount}
 * 是引擎帧身份，同一引擎帧的两个入口拿到相同的 amount，因此长帧超过门闩 5 ms
 * 时间窗后放行的第二个入口不会重复采样。固定步长引擎可能因相邻帧 amount 相同
 * 而跳过一帧，但不影响 &gt;200 ms 卡顿计数。关闭时不创建实例，调用点只做一次
 * null 检查，没有额外计时/分配。
 *
 * <p>口径：
 * <ul>
 *   <li>{@code frames}：有效帧间隔数（第一次调用只记起点）；</li>
 *   <li>{@code over200}：严格大于 200 ms 的间隔数；</li>
 *   <li>{@code maxMs}：最大有效间隔，毫秒向上取整；</li>
 *   <li>{@code p99Ms}：1 ms 直方图估算的 P99，&gt;= 1000 ms 归入溢出桶；</li>
 *   <li>{@code longGaps}：大于 5 s 的间隔数，不计入 frames/直方图
 *       （暂停、读档、alt-tab 等非帧事件）。</li>
 * </ul>
 */
public final class FrameTimeProbe {
    public static final String LINE_PREFIX = "HYPERNOVA_FRAME ";
    public static final long STUTTER_NANOS = 200_000_000L;
    public static final long MAX_GAP_NANOS = 5_000_000_000L;
    static final int MAX_BUCKET_MS = 1000;

    private final int logEveryFrames;
    private final long[] buckets = new long[MAX_BUCKET_MS + 1];
    private float lastAmount = Float.NaN;
    private boolean hasLast;
    private long lastNanos;
    private long frames;
    private long over200;
    private long longGaps;
    private long maxNanos;
    private long lastDeltaNanos;
    private long framesAtLastLine;

    public FrameTimeProbe(int logEveryFrames) {
        this.logEveryFrames = Math.max(1, logEveryFrames);
    }

    /**
     * 记录一帧。{@code amount} 是引擎帧标识（{@code advance(float amount)} 的参数），
     * 同一引擎帧的两个入口拿到相同的 amount，重复调用直接忽略。
     * {@code nowNanos} 必须是单调时钟。
     */
    public void frame(long nowNanos, float amount) {
        if (!Float.isFinite(amount) || amount <= 0f) {
            return;
        }
        if (Float.compare(amount, lastAmount) == 0) {
            return;
        }
        lastAmount = amount;
        if (!hasLast) {
            hasLast = true;
            lastNanos = nowNanos;
            return;
        }
        long delta = nowNanos - lastNanos;
        lastNanos = nowNanos;
        if (delta <= 0L) {
            return;
        }
        if (delta > MAX_GAP_NANOS) {
            longGaps++;
            return;
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
        int bucket = (int) Math.min(ms, MAX_BUCKET_MS);
        buckets[bucket]++;
    }

    /** @return 到达日志间隔时返回一行日志，否则 null。 */
    public String lineIfDue() {
        if (frames - framesAtLastLine < logEveryFrames) {
            return null;
        }
        framesAtLastLine = frames;
        return line();
    }

    public String line() {
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
        long need = (frames * 99L + 99L) / 100L; // ceil(0.99 * frames)
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
