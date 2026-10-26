package hypernova.adapter;

/**
 * 双入口幂等门闩（I1）：战役态 transient script 与战斗态 combat plugin 共享同一份
 * 调度器；两个实例各自 advance 会让同一帧的管线跑两遍（预算当场翻倍）。
 *
 * <p>用法是「进门前问、跑完后记」：
 * <pre>
 *   if (!gate.shouldRun(scheduler, scheduler.stats().ticks(), now)) return;
 *   ... tick pipeline ...
 *   gate.completed(scheduler, scheduler.stats().ticks(), now);
 * </pre>
 * 第二个入口进门时看到的 ticks 正好等于第一个入口跑完记下的 ticks，于是被判为同帧重复。
 * 时间窗（默认 5 ms）是兜底：引擎若在两帧之间超过该间隔，即使计数没变也放行，
 * 避免暂停/读档等场景把管线永久锁死。
 *
 * <p>状态按 {@code owner} 身份隔离：测试或热重载换一个调度器实例不会继承旧门闩状态。
 */
public final class FrameAdvanceGate {
    private final long minIntervalNanos;
    private Object owner;
    private long completedTicks = Long.MIN_VALUE;
    private long completedNanos = Long.MIN_VALUE;

    public FrameAdvanceGate(long minIntervalNanos) {
        this.minIntervalNanos = Math.max(0L, minIntervalNanos);
    }

    /** @return true 表示本次调用应推进管线；false 表示同帧重复入口，应直接返回。 */
    public synchronized boolean shouldRun(Object owner, long ticksAtEntry, long nowNanos) {
        if (owner != this.owner) {
            return true; // 换了调度器/新装配：门闩状态不延续
        }
        return !(ticksAtEntry == completedTicks && nowNanos - completedNanos < minIntervalNanos);
    }

    /** 管线跑完后登记，供同帧后续入口比对。 */
    public synchronized void completed(Object owner, long ticksAfter, long nowNanos) {
        this.owner = owner;
        completedTicks = ticksAfter;
        completedNanos = nowNanos;
    }
}
