package hypernova.hooks;

import hypernova.texture.TextureService;

import java.util.List;
import java.util.function.BooleanSupplier;
import java.util.function.LongSupplier;

/**
 * 读档窗口守卫 + 有预算的 pending 排空。
 *
 * <p>窗口打开时一条都不加载（REQ-R1-09）；窗口关闭后逐条 ensureLoaded，
 * 每加载一张检查一次耗时，超过 {@code budgetNanos} 立即停手（I3 / REQ-R1-03）。
 * 剩余的 pending 留在队列里，下一帧继续——这才是「每帧有界」，而不是「每帧最多 32 张」。
 */
public final class SaveLoadGuard {
    private static final int MAX_PER_TICK = 32;

    private final BooleanSupplier loadingSave;
    private final TextureService service;
    private final LongSupplier clock;
    private final long budgetNanos;

    public SaveLoadGuard(BooleanSupplier loadingSave, TextureService service) {
        // 无预算构造器保留给历史调用点：默认预算与调度器一致的 2 ms。
        this(loadingSave, service, System::nanoTime, 2_000_000L);
    }

    public SaveLoadGuard(BooleanSupplier loadingSave, TextureService service,
                         LongSupplier clock, long budgetNanos) {
        this.loadingSave = loadingSave;
        this.service = service;
        this.clock = clock;
        this.budgetNanos = Math.max(0L, budgetNanos);
    }

    /** @return 本次实际加载成功的张数（预算耗尽时小于 pending 数）。 */
    public int tick() {
        if (loadingSave.getAsBoolean()) {
            return 0;
        }
        long start = clock.getAsLong();
        int loaded = 0;
        for (int i = 0; i < MAX_PER_TICK; i++) {
            // 每次只取 1 条：预算中途停手时，未取出的路径仍留在 pending 里，
            // 下一帧继续（若一次 drain 32 条再 break，剩下的 31 条会被无声丢弃）。
            List<String> one = service.drainPending(1);
            if (one.isEmpty()) {
                break;
            }
            if (service.ensureLoaded(one.get(0)).ok()) {
                loaded++;
            }
            // 预算判定与 FrameBudgetScheduler 一致：>= budget 即停手（边界含等于）。
            if (clock.getAsLong() - start >= budgetNanos) {
                break;
            }
        }
        return loaded;
    }
}
