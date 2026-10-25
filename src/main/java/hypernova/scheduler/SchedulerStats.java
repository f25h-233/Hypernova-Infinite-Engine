package hypernova.scheduler;

public record SchedulerStats(long queued, long loaded, long failed, long ticks, long nanosLastTick, int backlog) {
}
