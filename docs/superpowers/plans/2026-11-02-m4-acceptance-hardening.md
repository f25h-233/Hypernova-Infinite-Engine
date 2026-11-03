# M4 验收 & 发布硬化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变任何默认开关的前提下，给 Hypernova 补上可复核的帧时间观测、会话报告工具、A/B/发行工具修复，以及 A→B/stutter 用户验收清单。

**Architecture:** 主 mod 侧新增一个默认关闭的 `FrameTimeProbe`，只在 `HypernovaCombatPlugin.advance` 通过 `FrameAdvanceGate` 后采样，按引擎帧 `amount` 去重，输出可被日志工具解析的 `HYPERNOVA_FRAME` 行。Python 侧新增 `tools/m4_session_report.py`，把帧探针行、agent 的 `lazy probe: summary`、五类纹理错误和可选 GPU CSV 合并成一份 JSON。其余是工具修复：`m26_ab.py` 的 stats 捕获时点/timeout/rounds、`smoke_run.py` 的 pid 文件、`release_check.py` 的主 jar 门禁、`build-mod.sh` 的失败清 zip。

**Tech Stack:** Java 17（game API classpath，JUnit 5）、Python 3（pytest，`python -I`）、Bash（Git Bash/MSYS）。

**Spec:** `技术笔记-纹理按需加载.md` §7（2026-11-02 裁决的 M4 行）与 `C:\Users\qwe13\.claude\projects\D--github-Hypernova-Infinite-Engine\memory\hn-m4-kickoff.md`。

## Global Constraints

- **不默认开启**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`、`textures.lazy.eviction.scene_unload.enabled=false`；frame-time probe 默认 off；不改 `data/config/hypernova/hypernova.json` 的发行默认值。
- 实现与提交不得改 `enabled_mods.json`/vmparams/用户配置。**用户 A→B gate 例外**：可按 `docs/m4-manual-acceptance.md` §1 备份、临时启用 `enabled_mods.json` 并在验收后恢复；vmparams 仍不改，probe 只用临时副本（如 `Miko_Lite_m4_probe.txt`），不覆盖 `Miko_Lite.txt`。
- frame-time probe 关闭时零采样成本：不创建探针实例，调用点只允许一次 null 检查。
- 探针必须在 `FrameAdvanceGate.completed(...)` 之后；同一引擎帧 `amount` 只采样一次（双入口/长帧 >5 ms 的二次入口都不得重复计数）。
- 探针口径：`frames` = 有效帧间隔数；`over200` = 严格 `> 200 ms` 的次数；`maxMs` = 向上取整的毫秒最大值；`p99Ms` = 1 ms 桶估算；`longGaps` = `> 5 s` 的间隔数，不计入 frames/直方图。
- `HYPERNOVA_FRAME ` 行格式固定为：`frames=<int> over200=<int> maxMs=<int> p99Ms=<int> lastMs=<int> longGaps=<int>`。
- 所有 Python 工具必须 fail-closed：缺日志/缺锚点/缺 summary 时返回非零并 stderr 一行说明，不输出全零假报告。
- 目标机是 Windows 11 中国区；禁止 `taskkill //F //IM node.exe`。只能按 PID 杀目标游戏进程。
- 不手工抄数字：A→B/stutter 的数字必须由 `m4_session_report.py` 从文件生成。
- 未确认不 push；本地提交按任务独立。
- **Escape hatch**：若断言数字/测试顺序与实现不符，按实际修正并在报告中说明，无需请示。**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**

## Review Focus

1. **长帧双入口重复采样**：`FrameAdvanceGate` 的 5 ms 时间窗在 >5 ms 的帧里会放行第二个入口；探针必须按引擎帧 `amount` 去重，否则 200 ms 卡顿会被拆成 200 ms + 小间隔。测试：`FrameTimeProbeTest.duplicateAmountIsIgnored`。
2. **关闭时仍然计时/分配**：探针关闭时不得构造对象、不得调用 `System.nanoTime()` 额外次数；测试：`AssemblyWiringTest.frameProbeRunsAfterGateAndOnlyWhenPresent`。
3. **会话切片串档**：旧的 `HYPERNOVA_FRAME` 行或旧的 `lazy probe: summary` 不能被当成本次会话；测试：`test_m4_session_report.py` 的多 anchor 用例。
4. **A/B treatment stats 被后续 control 覆盖**：T→C 轮里，treatment 跑完后 control 会写入新的 premain；stats 必须在 treatment 结束时立即抓。测试：`test_stats_captured_before_later_control_session`。
5. **timeout 后残留游戏进程污染下一轮**：`smoke_run` 写 pid 文件，`m26_ab` 超时后只杀该 PID；测试：`test_timeout_kills_recorded_game_pid`。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `src/main/java/hypernova/adapter/FrameTimeProbe.java`（新建） | 纯帧间隔统计：直方图、P99、>200 ms、长间隔排除、日志行格式化 |
| `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java` | 在门闩后按引擎帧 `amount` 采样，按需写 `HYPERNOVA_FRAME` |
| `src/main/java/hypernova/HypernovaPlugin.java` | 读 `-Dhypernova.frameProbe`，构造/注入探针 |
| `tests/java/hypernova/adapter/FrameTimeProbeTest.java`（新建） | 探针纯函数与 amount 去重测试 |
| `tests/java/hypernova/AssemblyWiringTest.java` | 静态接线守护：门闩顺序、默认关闭、日志行 |
| `tools/m4_session_report.py`（新建） | 合并帧探针/agent summary/纹理错误/GPU CSV |
| `tests/tools/test_m4_session_report.py`（新建） | 报告解析、会话切片、strict 门禁 |
| `tools/smoke_run.py` | 新增 `--pid-file`，正常退出清理 |
| `tools/m26_ab.py` | treatment stats 即时抓取、`--rounds>=1`、timeout 按 PID 清理 |
| `tools/release_check.py` | 要求 `jars/hypernova.jar` + 主 jar marker/entry 校验 |
| `tools/java/build-mod.sh` | 任意失败清 zip；把主 jar 传给 release_check |
| `docs/m4-manual-acceptance.md`（新建） | A→B/stutter 手工协议与判定 |
| `docs/m4-results.md`（新建） | 实际验证结果与未完成 user gate 的记录 |
| `技术笔记-纹理按需加载.md` | §7 M4 行回写 |

---

### Task 1: 帧时间探针（默认 off）

> **实现偏差（2026-11-03 review M-4）**：已交付代码使用
> `frame(long nowNanos, float amount)` 和
> `FrameTimeProbeTest.duplicateAmountIsIgnored`，按引擎帧 `amount` 去重
> （相邻真实帧可能共享同一 `amount`，因此会少计；两个入口 amount 不同会重复
> 计数）。下面 Step 1/3/5 的 `tick` 签名与代码片段是**初始计划**，未按原样
> 实现；以实际源码、测试与 `docs/m4-manual-acceptance.md` 为准。

**Files:**
- Create: `src/main/java/hypernova/adapter/FrameTimeProbe.java`
- Modify: `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java`
- Modify: `src/main/java/hypernova/HypernovaPlugin.java`
- Test: `tests/java/hypernova/adapter/FrameTimeProbeTest.java`（新建）
- Test: `tests/java/hypernova/AssemblyWiringTest.java`

**Interfaces:**
- Consumes: `FrameAdvanceGate.completed(Object owner, long ticksAfter, long nowNanos)`；`PrefetchScheduler.stats().ticks()`。
- Produces:
  - `public final class FrameTimeProbe`
  - `public FrameTimeProbe(int logEveryFrames)`
  - `public void frame(long nowNanos, long tick)`
  - `public String lineIfDue()`
  - `public String line()`
  - `public static final String LINE_PREFIX = "HYPERNOVA_FRAME "`
  - `public static final long STUTTER_NANOS = 200_000_000L`
  - `public static final long MAX_GAP_NANOS = 5_000_000_000L`
  - `HypernovaPlugin.frameProbeEnabled()`（package-private static）

**Dependencies:** 无
**Touches:** `src/main/java/hypernova/adapter/FrameTimeProbe.java`, `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java`, `src/main/java/hypernova/HypernovaPlugin.java`, `tests/java/hypernova/adapter/FrameTimeProbeTest.java`, `tests/java/hypernova/AssemblyWiringTest.java`

- [ ] **Step 1: 写失败测试 `tests/java/hypernova/adapter/FrameTimeProbeTest.java`**

```java
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `bash tools/java/run-tests.sh FrameTimeProbeTest`
Expected: 编译失败（`FrameTimeProbe` 不存在）。

- [ ] **Step 3: 新建 `src/main/java/hypernova/adapter/FrameTimeProbe.java`**

```java
package hypernova.adapter;

/**
 * 主线程帧时间探针（默认关闭，M4 验收用）。
 *
 * <p>只在 {@code HypernovaCombatPlugin.advance} 通过 {@link FrameAdvanceGate}
 * 之后调用，并按 scheduler tick 去重：同一帧的第二个入口（以及长帧超过门闩
 * 5 ms 时间窗后放行的第二个入口）不会重复采样。关闭时不创建实例，调用点只做
 * 一次 null 检查，没有额外计时/分配。
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
    private long lastTick = Long.MIN_VALUE;
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
     * 记录一帧。{@code tick} 必须来自 {@code scheduler.stats().ticks()}；
     * 同一 tick 的重复调用直接忽略。{@code nowNanos} 必须是单调时钟。
     */
    public void frame(long nowNanos, long tick) {
        if (tick == lastTick) {
            return;
        }
        lastTick = tick;
        long last = lastNanos;
        lastNanos = nowNanos;
        if (last == 0L) {
            return;
        }
        long delta = nowNanos - last;
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
```

- [ ] **Step 4: 运行探针测试确认通过**

Run: `bash tools/java/run-tests.sh FrameTimeProbeTest`
Expected: 8 tests passed。

- [ ] **Step 5: 接线 `HypernovaCombatPlugin`**

在 `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java` 做以下修改：

1. 静态槽位与实例字段：

```java
    /** M4 frame-time probe；null = 关闭（零采样成本）。 */
    private static volatile FrameTimeProbe sharedFrameProbe;
```

```java
    private FrameTimeProbe frameProbe;
```

2. `install(...)` 增加最后一个参数 `FrameTimeProbe frameProbe`，并赋值：

```java
    public static void install(TriggerPoller poller, PostLoadWarmupHook warmupHook,
                               SaveLoadGuard saveLoadGuard, PrefetchScheduler scheduler,
                               Telemetry telemetry, TextureService service,
                               Runnable startupSelfCheck, int heartbeatFrames,
                               FrameTimeProbe frameProbe) {
        ...
        sharedHeartbeatFrames = heartbeatFrames;
        sharedFrameProbe = frameProbe;
    }
```

3. `resolve()` 里补 `frameProbe = sharedFrameProbe;`。

4. 把原来的尾部：

```java
        poller.tick();
        warmupHook.tick();
        saveLoadGuard.tick();
        scheduler.tick();
        GATE.completed(scheduler, scheduler.stats().ticks(), System.nanoTime());
        tickCount++;
```

改成：

```java
        poller.tick();
        warmupHook.tick();
        saveLoadGuard.tick();
        scheduler.tick();
        long now = System.nanoTime();
        long ticks = scheduler.stats().ticks();
        GATE.completed(scheduler, ticks, now);
        tickCount++;
        // M4：探针在门闩之后，并带 tick 去重；关闭时只做一次 null 检查。
        FrameTimeProbe probe = frameProbe;
        if (probe != null) {
            probe.frame(now, amount);
            String frameLine = probe.lineIfDue();
            if (frameLine != null) {
                com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class)
                        .info(frameLine);
            }
        }
```

- [ ] **Step 6: 接线 `HypernovaPlugin`**

1. 增加常量与属性读取：

```java
    private static final int FRAME_PROBE_LOG_FRAMES = 600;

    static boolean frameProbeEnabled() {
        return Boolean.getBoolean("hypernova.frameProbe");
    }
```

2. 在 `HypernovaCombatPlugin.install(...)` 之前构造探针：

```java
            FrameTimeProbe frameProbe = frameProbeEnabled()
                    ? new FrameTimeProbe(FRAME_PROBE_LOG_FRAMES) : null;
            if (frameProbe != null) {
                Global.getLogger(HypernovaPlugin.class).info(
                        "Hypernova frame probe enabled: log every "
                                + FRAME_PROBE_LOG_FRAMES + " frames");
            }
```

3. `install(...)` 调用末尾加 `frameProbe`；catch 回滚调用改成：

```java
            HypernovaCombatPlugin.install(null, null, null, null, null, null, null, 0, null);
```

4. 文件顶部 import `hypernova.adapter.FrameTimeProbe`。

- [ ] **Step 7: 补静态接线测试 `tests/java/hypernova/AssemblyWiringTest.java`**

追加：

```java
    @Test
    void frameProbeRunsAfterGateAndOnlyWhenPresent() throws Exception {
        String src = read(COMBAT);
        int completed = src.indexOf("GATE.completed(");
        int probe = src.indexOf("probe.frame(");
        assertTrue(completed > 0 && probe > completed,
                "frame probe 必须在 GATE.completed 之后采样");
        assertTrue(src.contains("FrameTimeProbe probe = frameProbe;"),
                "关闭时必须只做一次 null 检查");
        assertTrue(src.contains(".info(frameLine)"),
                "探针行必须写入游戏日志");
        assertTrue(read(PLUGIN).contains("Boolean.getBoolean(\"hypernova.frameProbe\")"),
                "frame probe 必须默认关闭、用 -Dhypernova.frameProbe=true 开启");
        assertTrue(read(PLUGIN).contains("new FrameTimeProbe(FRAME_PROBE_LOG_FRAMES)"),
                "探针构造必须只在属性开启时发生");
    }

    @Test
    void frameProbePropertyDefaultsOff() {
        String old = System.getProperty("hypernova.frameProbe");
        try {
            System.clearProperty("hypernova.frameProbe");
            assertFalse(HypernovaPlugin.frameProbeEnabled());
            System.setProperty("hypernova.frameProbe", "true");
            assertTrue(HypernovaPlugin.frameProbeEnabled());
        } finally {
            if (old == null) {
                System.clearProperty("hypernova.frameProbe");
            } else {
                System.setProperty("hypernova.frameProbe", old);
            }
        }
    }
```

- [ ] **Step 8: 运行主测试全量**

Run: `bash tools/java/run-tests.sh`
Expected: 全部 passed（无 fail）。

- [ ] **Step 9: 提交**

```bash
git add src/main/java/hypernova/adapter/FrameTimeProbe.java \
        src/main/java/hypernova/adapter/HypernovaCombatPlugin.java \
        src/main/java/hypernova/HypernovaPlugin.java \
        tests/java/hypernova/adapter/FrameTimeProbeTest.java \
        tests/java/hypernova/AssemblyWiringTest.java
git commit -m "feat(m4): add opt-in main-thread frame time probe"
```

---

### Task 2: 会话报告工具

**Files:**
- Create: `tools/m4_session_report.py`
- Test: `tests/tools/test_m4_session_report.py`

**Interfaces:**
- Consumes: Task 1 的 `HYPERNOVA_FRAME frames=<int> over200=<int> maxMs=<int> p99Ms=<int> lastMs=<int> longGaps=<int>`；`tools/m28_scene_gate.py` 的 `last_session(text)`、`count_texture_errors(text)`、`read_gpu_csv(path)`、`summarize_gpu(rows)`。
- Produces:
  - `find_frame_probe(text: str) -> dict`
  - `find_lazy_summary(text: str) -> dict`
  - `build_report(agent_text: str, starsector_text: str, gpu_rows=None) -> dict`
  - CLI `python tools/m4_session_report.py --agent-log ... --starsector-log ... [--gpu-csv ...] [--out ...] [--require-frame] [--strict] [--text]`

**Dependencies:** Task 1
**Touches:** `tools/m4_session_report.py`, `tests/tools/test_m4_session_report.py`

- [ ] **Step 1: 写失败测试 `tests/tools/test_m4_session_report.py`**

```python
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
_spec = importlib.util.spec_from_file_location(
    "m4_session_report", TOOLS / "m4_session_report.py")
report_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_mod)

FRAME = ("HYPERNOVA_FRAME frames=600 over200=2 maxMs=250 p99Ms=16 "
         "lastMs=12 longGaps=1")
SUMMARY = ("lazy probe: summary queue=1 wouldSkip=0 lookups=5 demand=1 "
           "index=10 types={} queuedSkip=0 demandQueued=0 hits=1 misses=0 "
           "degraded=0 skipped=0 proxies=1 materialized=1 deferred=0 pending=0 "
           "drained=1 reregistered=0 failed=0 disabled=0 main=main loading=none "
           "lateRegistered=0 lateLoaded=0 dimMismatch=0 dds=1 ddsHit=1 "
           "ddsFallback=0 ddsDisabled=0 ddsDimMismatch=0 eviction=1 evicted=0 "
           "rematerialized=0 evictPasses=0 liveBytes=100 startupBytes=10 "
           "foreignBytes=20 evictableBytes=70 budgetBytes=1024 "
           "emptyEvictPasses=0 evictPassMsTotal=0 evictPassMsMax=0 "
           "placeholder=1 oldIdDeleted=0 evictSkipped=0 deferredDeletes=0 "
           "selftest=0 failedParked=0 sceneUnload=0 scenePasses=0 "
           "sceneEvictions=0 sceneEvictMsTotal=0 sceneEvictMsMax=0 scenePending=0")


def test_frame_probe_uses_last_line():
    text = FRAME + "\n" + FRAME.replace("over200=2", "over200=9") + "\n"
    parsed = report_mod.find_frame_probe(text)
    assert parsed["present"] is True
    assert parsed["over200"] == 9
    assert parsed["line"] == 2
    assert parsed["missing_keys"] == []


def test_frame_probe_absent():
    parsed = report_mod.find_frame_probe("no probe here\n")
    assert parsed["present"] is False
    assert "frames" in parsed["missing_keys"]


def test_lazy_summary_only_after_last_anchor():
    text = ("hypernova agent premain\n" + SUMMARY + "\n"
            "hypernova agent premain\n"
            + SUMMARY.replace("disabled=0", "disabled=1") + "\n")
    parsed = report_mod.find_lazy_summary(text)
    assert parsed["present"] is True
    assert parsed["summary"]["disabled"] == 1
    assert parsed["anchor_count"] == 2


def test_lazy_summary_missing_anchor_fails_closed():
    parsed = report_mod.find_lazy_summary(SUMMARY + "\n")
    assert parsed["present"] is False
    assert "anchor" in parsed["reason"]


def test_build_report_combines_sections():
    starsector = ("Fast Rendering: v0.9.7rc2\n" + FRAME + "\n"
                  "Failed to load texture x\n")
    report = report_mod.build_report(
        "hypernova agent premain\n" + SUMMARY + "\n", starsector)
    assert report["frame_probe"]["present"] is True
    assert report["lazy"]["present"] is True
    assert report["texture_errors_total"] == 1
    assert report["health"]["texture_errors_zero"] is False
    assert report["health"]["lazy_failed_zero"] is True


def test_texture_errors_before_last_session_anchor_are_ignored():
    starsector = ("Failed to load texture old\n"
                  "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    report = report_mod.build_report(
        "hypernova agent premain\n" + SUMMARY + "\n", starsector)
    assert report["texture_errors_total"] == 0


def _write_session(tmp_path, starsector):
    agent = tmp_path / "agent.log"
    agent.write_text("hypernova agent premain\n" + SUMMARY + "\n", encoding="utf-8")
    log = tmp_path / "starsector.log"
    log.write_text(starsector, encoding="utf-8")
    return agent, log


def test_strict_requires_frame_probe(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\nno frame\n")
    out = tmp_path / "report.json"
    rc = report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                          "--out", str(out), "--strict"])
    assert rc == 1
    assert json.loads(out.read_text(encoding="utf-8"))["frame_probe"]["present"] is False


def test_require_frame_pass(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    out = tmp_path / "report.json"
    assert report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                            "--out", str(out), "--require-frame"]) == 0


def test_gpu_csv_without_samples_is_rc2(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    gpu = tmp_path / "gpu.csv"
    gpu.write_text("timestamp,dedicated_mb,shared_mb\n", encoding="utf-8")
    assert report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                            "--gpu-csv", str(gpu)]) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `python -I -m pytest tests/tools/test_m4_session_report.py -q`
Expected: 收集/导入失败（文件不存在）。

- [ ] **Step 3: 新建 `tools/m4_session_report.py`**

```python
#!/usr/bin/env python3
"""M4 手动会话报告：frame probe + lazy summary + 纹理错误 + GPU CSV。

读取最后一个 Starsector 会话切片里的 `HYPERNOVA_FRAME` 行和五类纹理错误，
读取最后一个 agent session 的 `lazy probe: summary`，可选合并 GPU CSV。
输出一份 JSON，避免手工抄数字。

用法：
    python tools/m4_session_report.py \
      --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
      --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
      --gpu-csv build/m4/gpu-a.csv \
      --out build/m4/session.json --strict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import m28_scene_gate as gate

FRAME_MARKER = "HYPERNOVA_FRAME "
AGENT_SESSION_ANCHOR = "hypernova agent premain"
REQUIRED_FRAME_KEYS = (
    "frames", "over200", "maxMs", "p99Ms", "lastMs", "longGaps",
)
REQUIRED_LAZY_KEYS = ("queue", "failed", "disabled", "dimMismatch", "main")
_KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")


def parse_pairs(text: str) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for key, value in _KEY_VALUE.findall(text):
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = value
    return out


def find_frame_probe(text: str) -> dict:
    """返回给定会话切片里最后一条 HYPERNOVA_FRAME 行。"""
    found: dict[str, int | str] | None = None
    found_line = None
    for lineno, line in enumerate(text.splitlines(), 1):
        pos = line.find(FRAME_MARKER)
        if pos < 0:
            continue
        found = parse_pairs(line[pos + len(FRAME_MARKER):])
        found_line = lineno
    if found is None:
        return {"present": False, "missing_keys": list(REQUIRED_FRAME_KEYS)}
    missing = [key for key in REQUIRED_FRAME_KEYS if key not in found]
    return {"present": True, "line": found_line,
            "missing_keys": missing, **found}


def find_lazy_summary(text: str) -> dict:
    """只认最后一个 `hypernova agent premain` 之后的有效 summary。"""
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines)
               if AGENT_SESSION_ANCHOR in line]
    if not anchors:
        return {"present": False, "reason": "no agent session anchor",
                "anchor_line": None, "anchor_count": 0, "missing_keys": []}
    anchor = anchors[-1]
    session = "".join(lines[anchor + 1:])
    found = None
    found_line = None
    missing = list(REQUIRED_LAZY_KEYS)
    for offset, line in enumerate(session.splitlines()):
        if "lazy probe: summary" not in line or "summary failed" in line:
            continue
        parsed = parse_pairs(line)
        missing = [key for key in REQUIRED_LAZY_KEYS if key not in parsed]
        if missing:
            continue
        found = parsed
        found_line = anchor + offset + 2
    if found is None:
        return {"present": False, "reason": "no valid summary after anchor",
                "anchor_line": anchor + 1, "anchor_count": len(anchors),
                "missing_keys": missing}
    return {"present": True, "summary": found, "line": found_line,
            "anchor_line": anchor + 1, "anchor_count": len(anchors),
            "missing_keys": []}


def _zero(summary: dict, key: str):
    value = summary.get(key)
    if not isinstance(value, int):
        return None
    return value == 0


def build_report(agent_text: str, starsector_text: str,
                 gpu_rows=None) -> dict:
    session, anchor_found, anchor_line, anchor_count = gate.last_session(
        starsector_text)
    errors = gate.count_texture_errors(session)
    frame = find_frame_probe(session)
    lazy = find_lazy_summary(agent_text)
    summary = lazy.get("summary", {})
    health = {
        "session_anchor_found": anchor_found,
        "frame_probe_present": frame["present"],
        "frame_probe_complete": frame["present"] and not frame["missing_keys"],
        "lazy_present": lazy["present"],
        "lazy_failed_zero": _zero(summary, "failed"),
        "lazy_disabled_zero": _zero(summary, "disabled"),
        "lazy_dim_mismatch_zero": _zero(summary, "dimMismatch"),
        "lazy_failed_parked_zero": _zero(summary, "failedParked"),
        "lazy_main_bound": summary.get("main") not in (None, "none"),
        "texture_errors_zero": sum(errors.values()) == 0,
    }
    report = {
        "starsector_session": {
            "anchor_found": anchor_found,
            "anchor_line": anchor_line,
            "anchor_count": anchor_count,
        },
        "frame_probe": frame,
        "lazy": lazy,
        "texture_errors": errors,
        "texture_errors_total": sum(errors.values()),
        "health": health,
    }
    if gpu_rows is not None:
        report["gpu"] = gate.summarize_gpu(gpu_rows)
    return report


def human_text(report: dict) -> str:
    frame = report["frame_probe"]
    lazy = report["lazy"]
    lines = []
    if frame["present"]:
        lines.append("frame: frames={frames} over200={over200} "
                     "max={maxMs}ms p99={p99Ms}ms last={lastMs}ms "
                     "longGaps={longGaps}".format(**frame))
    else:
        lines.append("frame: absent")
    if lazy["present"]:
        summary = lazy["summary"]
        lines.append("lazy: failed={} disabled={} dimMismatch={} "
                     "failedParked={} main={} live={} evictable={}".format(
                         summary.get("failed"), summary.get("disabled"),
                         summary.get("dimMismatch"),
                         summary.get("failedParked"), summary.get("main"),
                         summary.get("liveBytes"),
                         summary.get("evictableBytes")))
    else:
        lines.append("lazy: absent ({})".format(lazy.get("reason")))
    lines.append("texture errors: total={}".format(
        report["texture_errors_total"]))
    gpu = report.get("gpu")
    if gpu:
        lines.append("gpu dedicated MB: {}".format(gpu.get("dedicated_mb")))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-log", type=Path, required=True)
    parser.add_argument("--starsector-log", type=Path, required=True)
    parser.add_argument("--gpu-csv", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-frame", action="store_true",
                        help="fail unless a complete HYPERNOVA_FRAME line "
                             "exists in the current session")
    parser.add_argument("--strict", action="store_true",
                        help="also require a healthy lazy summary and zero "
                             "texture errors")
    parser.add_argument("--text", action="store_true",
                        help="also print a human summary to stderr")
    args = parser.parse_args(argv)

    try:
        agent_text = args.agent_log.read_text(
            encoding="utf-8", errors="replace")
        starsector_text = args.starsector_log.read_text(
            encoding="utf-8", errors="replace")
        gpu_rows = None
        gpu_bad_rows = 0
        if args.gpu_csv is not None:
            gpu_rows, gpu_bad_rows = gate.read_gpu_csv(args.gpu_csv)
            if not gpu_rows:
                print("m4_session_report: no valid GPU samples in "
                      f"{args.gpu_csv} (bad_rows={gpu_bad_rows})",
                      file=sys.stderr)
                return 2
        report = build_report(agent_text, starsector_text, gpu_rows)
        if gpu_bad_rows:
            report["gpu_bad_rows"] = gpu_bad_rows
        text = json.dumps(report, ensure_ascii=False, indent=2,
                          allow_nan=False)
    except (OSError, ValueError) as exc:
        print(f"m4_session_report: {exc}", file=sys.stderr)
        return 1

    print(text)
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"m4_session_report: {exc}", file=sys.stderr)
            return 1
    if args.text:
        print(human_text(report), file=sys.stderr)

    problems: list[str] = []
    health = report["health"]
    if args.require_frame or args.strict:
        if not health["session_anchor_found"]:
            problems.append("no Fast Rendering session anchor")
        if not health["frame_probe_present"]:
            problems.append("no HYPERNOVA_FRAME line (frame probe off?)")
        elif not health["frame_probe_complete"]:
            problems.append("frame probe line missing keys: "
                            + ", ".join(report["frame_probe"]["missing_keys"]))
        if health["texture_errors_zero"] is False:
            problems.append("texture errors > 0")
    if args.strict:
        if not health["lazy_present"]:
            problems.append("no valid lazy probe summary")
        for key, label in (
                ("lazy_failed_zero", "failed != 0"),
                ("lazy_disabled_zero", "disabled != 0"),
                ("lazy_dim_mismatch_zero", "dimMismatch != 0"),
                ("lazy_failed_parked_zero", "failedParked != 0"),
                ("lazy_main_bound", "main not bound")):
            if health[key] is False:
                problems.append(label)
            elif health[key] is None:
                problems.append(label + " (missing key)")
    if problems:
        for problem in problems:
            print(f"m4_session_report: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -I -m pytest tests/tools/test_m4_session_report.py -q`
Expected: 9 passed。

- [ ] **Step 5: 运行全量 pytest**

Run: `python -I -m pytest tests/tools -q`
Expected: 原有测试 + 新测试全部 passed。

- [ ] **Step 6: 提交**

```bash
git add tools/m4_session_report.py tests/tools/test_m4_session_report.py
git commit -m "feat(m4): add session report tool for frame probe and lazy summary"
```

---

### Task 3: A/B stats 时点、rounds 校验、timeout 清理

**Files:**
- Modify: `tools/m26_ab.py`
- Modify: `tools/smoke_run.py`
- Test: `tests/tools/test_m26_ab.py`
- Test: `tests/tools/test_smoke_run.py`

**Interfaces:**
- Consumes: `tools/smoke_run.py` 的 `kill_pid(pid, force)`、`wait_dead(pid, timeout_s)`。
- Produces:
  - `tools/m26_ab.py` 新增 `cleanup_timed_out_game(pid_file: Path) -> bool`；`run_round(...)` 会向 smoke_run 传 `--pid-file`。
  - `tools/smoke_run.py` 新增 CLI `--pid-file` 与 `clear_pid_file(path: str) -> None`。

**Dependencies:** 无
**Touches:** `tools/m26_ab.py`, `tools/smoke_run.py`, `tests/tools/test_m26_ab.py`, `tests/tools/test_smoke_run.py`

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_m26_ab.py` 追加：

```python
import time


def test_rounds_must_be_positive(tmp_path):
    out = tmp_path / "ab.json"
    try:
        ab.main(["--rounds", "0", "--out", str(out)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("--rounds 0 should exit 2")


def test_stats_captured_before_later_control_session(tmp_path, monkeypatch):
    """T→C 轮：treatment 的 summary 不能被后续 control 的 premain 冲掉。"""
    monkeypatch.setattr(ab, "run_round", lambda *a, **k: _row(50.0))
    monkeypatch.setattr(ab, "archive_round", lambda *a, **k: {
        "log": None, "log_present": True, "failed": 0, "verify": 0,
        "class_errors": 0, "async_errors": 0, "corrupted": 0})
    monkeypatch.setattr(ab, "free_physical_mb", lambda: 20_000.0)
    monkeypatch.setattr(ab, "stats_from_text", ab.stats_from_text)
    agent = tmp_path / "agent.log"
    agent.write_text("hypernova agent premain\n", encoding="utf-8")

    def fake_run(profile, lazy, dds, eviction, selftest, out, wait, linger):
        with agent.open("a", encoding="utf-8") as fh:
            if lazy:
                fh.write("hypernova agent premain\n"
                         "lazy probe: summary queue=7 failed=0 disabled=0 "
                         "dimMismatch=0 main=main ddsHit=1 ddsDisabled=0\n")
            else:
                fh.write("hypernova agent premain\n")
        return _row(50.0)

    monkeypatch.setattr(ab, "run_round", fake_run)
    out = tmp_path / "ab.json"
    assert ab.main(["--rounds", "2", "--counterbalance",
                    "--agent-log", str(agent), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["lazy_rows"] == 2
    assert result["lazy_median"]["queue"] == 7
    assert result["gates"]["treatment_stats_present"] is True


def test_timeout_kills_recorded_game_pid(tmp_path, monkeypatch):
    out = tmp_path / "round.json"
    pid_file = tmp_path / "round.json.pid"
    pid_file.write_text("424242", encoding="utf-8")
    calls = []
    monkeypatch.setattr(ab, "kill_pid", lambda pid, force: calls.append((pid, force)))
    monkeypatch.setattr(ab, "wait_dead", lambda pid, timeout: True)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="smoke", timeout=1)
    monkeypatch.setattr(ab.subprocess, "run", boom)
    row = ab.run_round("miko-lite", True, True, False, False,
                       out, 1, 1)
    assert row["ok"] is False
    assert row["reason"] == "timeout"
    assert calls == [(424242, True)]
    assert not pid_file.exists()
```

在 `tests/tools/test_smoke_run.py` 追加：

```python
def test_one_round_writes_and_clears_pid_file(tmp_path, monkeypatch):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    cfg = {"java": "jre/java", "vmparams": "vm.txt", "cwd": "starsector-core"}
    pid_file = tmp_path / "round.pid"
    seen = {}

    class FakeProc:
        pid = 424242

    def fake_stop(proc):
        seen["pid"] = pid_file.read_text(encoding="utf-8")
        return "forced"

    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(smoke, "wait_for_menu", lambda *a, **k: 12.5)
    monkeypatch.setattr(smoke, "io_read_bytes", lambda pid: 7)
    monkeypatch.setattr(smoke, "process_memory_mb", lambda pid: 1234.56)
    monkeypatch.setattr(smoke, "process_private_mb", lambda pid: 2345.67)
    monkeypatch.setattr(smoke, "gpu_memory_mb", lambda: 4096.0)
    monkeypatch.setattr(smoke, "process_gpu_memory_mb", lambda pid: (3500.0, 100.0))
    monkeypatch.setattr(smoke, "free_physical_mb", lambda: 15000.0)
    monkeypatch.setattr(smoke, "graceful_stop", fake_stop)
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: None)

    args = argparse.Namespace(start_res="1707x1067", fullscreen=False,
                              jvm_arg=[], wait_menu=1, linger=0,
                              pid_file=str(pid_file))
    row = smoke.one_round(cfg, game, args)
    assert row["ok"] is True
    assert seen["pid"] == "424242"
    assert not pid_file.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -I -m pytest tests/tools/test_m26_ab.py tests/tools/test_smoke_run.py -q`
Expected: 新用例失败（无 `--pid-file` / 无 `lazy_rows` / `--rounds 0` 仍运行）。

- [ ] **Step 3: 修改 `tools/smoke_run.py`**

1. `main()` 的 argparse 增加：

```python
    ap.add_argument("--pid-file", default="",
                    help="write the launched game PID here; removed on normal exit")
```

2. 在 `log_path_for` 附近增加：

```python
def clear_pid_file(path: str) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
```

3. `one_round` 在 `Popen` 之后写入 PID：

```python
    proc = subprocess.Popen(cmd, cwd=str(cwd),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_file = getattr(args, "pid_file", "")
    if pid_file:
        p = Path(pid_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(proc.pid), encoding="utf-8")
```

4. `menu_s is None` 分支里，`kill_pid` 后加 `clear_pid_file(pid_file)`：

```python
    if menu_s is None:
        kill_pid(proc.pid, True)
        clear_pid_file(pid_file)
        return {"ok": False, "reason": "menu-timeout", "elapsed": time.time() - t0}
```

5. 正常退出路径（`time.sleep(1.0)` 之前或之后）加：

```python
    clear_pid_file(pid_file)
```

- [ ] **Step 4: 修改 `tools/m26_ab.py`**

1. import 与常量：

```python
import time
...
from smoke_run import PROFILES, free_physical_mb, kill_pid, wait_dead
...
PID_FILE_MAX_AGE_S = 300
```

2. 新增函数：

```python
def cleanup_timed_out_game(pid_file: Path) -> bool:
    """只杀 smoke_run 记录的这一个游戏 PID，避免残留进程污染下一轮。"""
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        age = time.time() - pid_file.stat().st_mtime
    except (OSError, ValueError):
        return False
    try:
        if age > PID_FILE_MAX_AGE_S:
            return False
        kill_pid(pid, True)
        wait_dead(pid, 20)
        return True
    finally:
        try:
            pid_file.unlink()
        except OSError:
            pass
```

3. `run_round` 增加 pid 文件、timeout 清理、非零退出清理：

```python
def run_round(profile: str, lazy: bool, dds: bool, eviction: bool,
              selftest: bool, out: Path, wait: float, linger: float) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    pid_file = out.with_name(out.name + ".pid")
    cmd = [sys.executable, "-I", str(TOOLS / "smoke_run.py"),
           "--profile", profile, "--rounds", "1", "--wait-menu", str(wait),
           "--linger", str(linger), "--json-out", str(out.resolve()),
           "--pid-file", str(pid_file.resolve())]
    for arg in _flags(lazy, dds, eviction, selftest):
        cmd.append("--jvm-arg=" + arg)
    try:
        proc = subprocess.run(cmd, check=False, cwd=str(ROOT), timeout=SMOKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "returncode": None,
                "game_cleanup": cleanup_timed_out_game(pid_file)}
    try:
        row = json.loads(out.read_text(encoding="utf-8"))[0]
    except Exception as exc:
        row = {"ok": False, "reason": f"json: {exc}"}
    row["returncode"] = proc.returncode
    if proc.returncode != 0 or not row.get("ok", False):
        row["ok"] = False
        row["game_cleanup"] = cleanup_timed_out_game(pid_file)
    return row
```

4. `main()` 在 `parse_args` 后加：

```python
    if args.rounds < 1:
        ap.error("--rounds must be >= 1")
```

5. 主循环改为在 treatment 跑完立即抓 stats：

```python
        side_rows = {}
        treatment_lazy: dict = {}
        for side, treatment in order:
            ...
            row = run_round(...)
            row.update(archive_round(...))
            if treatment:
                treatment_lazy = stats_from_text(
                    agent.read_text(encoding="utf-8", errors="replace")) \
                    if agent.is_file() else {}
                row["lazy_captured"] = bool(treatment_lazy)
            side_rows[side] = row
            ...
        rows.append({"control": c, "treatment": t, "lazy": treatment_lazy,
                     "order": [side for side, _ in order]})
```

6. `lazy_median` 改为按可用行计算；新增 gate 与 `lazy_rows`：

```python
    lazy_rows = [r["lazy"] for r in rows if r["lazy"]]
    lazy_median = {}
    if lazy_rows:
        keys = set().union(*(r.keys() for r in lazy_rows))
        for key in sorted(keys):
            values = [r.get(key) for r in lazy_rows
                      if isinstance(r.get(key), int)]
            lazy_median[key] = median(values)
```

```python
        "treatment_stats_present": bool(rows) and all(
            bool(r["lazy"]) for r in rows),
```

```python
        "lazy_rows": len(lazy_rows),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -I -m pytest tests/tools/test_m26_ab.py tests/tools/test_smoke_run.py -q`
Expected: 全部 passed。

- [ ] **Step 6: 提交**

```bash
git add tools/m26_ab.py tools/smoke_run.py \
        tests/tools/test_m26_ab.py tests/tools/test_smoke_run.py
git commit -m "fix(m4): capture A/B treatment stats per run and clean timed-out games"
```

---

### Task 4: 发行门禁主 jar 与失败清 zip

**Files:**
- Modify: `tools/release_check.py`
- Modify: `tools/java/build-mod.sh`
- Test: `tests/tools/test_release_check.py`

**Interfaces:**
- Consumes: `build/java/hypernova.jar` 的 entry 列表（`hypernova/HypernovaPlugin.class`、`hypernova/adapter/HypernovaCombatPlugin.class`）。
- Produces:
  - `release_check.check_zip(zip_path, agent_jar=None, main_jar=None)`
  - CLI `--main-jar PATH`
  - 发行 zip 必须含非空 `jars/hypernova.jar`

**Dependencies:** 无
**Touches:** `tools/release_check.py`, `tools/java/build-mod.sh`, `tests/tools/test_release_check.py`

- [ ] **Step 1: 更新失败测试**

把 `tests/tools/test_release_check.py` 的 `_release_zip` 改成同时写入主 jar：

```python
MAIN = ("hypernova/HypernovaPlugin.class",
        "hypernova/adapter/HypernovaCombatPlugin.class")


def _main_jar(path, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        for name in MAIN:
            zf.writestr(name, b"x")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def _release_zip(tmp_path, drop=(), overrides=None):
    jar = _agent_jar(tmp_path / "agent.jar")
    main = _main_jar(tmp_path / "hypernova.jar")
    files = {
        "mod_info.json": b"{}",
        "README-install.txt": b"note",
        "data/config/hypernova/manifest-v1.json": MANIFEST,
        "data/config/hypernova/lazy-skip-v1.txt":
            b"# generation=" + GEN.encode() + b"\npath\t1\t1\n",
        "jars/hypernova.agent.jar": jar.read_bytes(),
        "jars/hypernova.jar": main.read_bytes(),
        "graphics/hypernova/blank.png": b"png",
    }
    ...
```

追加用例：

```python
def test_missing_main_jar_fails(tmp_path):
    zip_path, _ = _release_zip(tmp_path, drop=("jars/hypernova.jar",))
    assert any("missing jars/hypernova.jar" in f
               for f in rc.check_zip(zip_path))


def test_main_jar_missing_marker_fails(tmp_path):
    bad = tmp_path / "bad-main.jar"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("unrelated/Thing.class", b"x")
    zip_path, _ = _release_zip(
        tmp_path, overrides={"jars/hypernova.jar": bad.read_bytes()})
    assert any("packaged main jar missing" in f
               for f in rc.check_zip(zip_path))


def test_main_jar_entries_must_match_built(tmp_path):
    zip_path, _ = _release_zip(tmp_path)
    built = _main_jar(tmp_path / "built.jar",
                      extra={"extra/Thing.class": b"x"})
    assert any("packaged main jar entries differ" in f
               for f in rc.check_zip(zip_path, main_jar=built))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -I -m pytest tests/tools/test_release_check.py -q`
Expected: 主 jar 相关用例失败。

- [ ] **Step 3: 修改 `tools/release_check.py`**

1. 常量：

```python
REQUIRED = (
    "mod_info.json",
    "README-install.txt",
    "data/config/hypernova/manifest-v1.json",
    "data/config/hypernova/lazy-skip-v1.txt",
    "graphics/hypernova/blank.png",
    "jars/hypernova.agent.jar",
    "jars/hypernova.jar",
)
...
MAIN_MARKERS = (
    "hypernova/HypernovaPlugin.class",
    "hypernova/adapter/HypernovaCombatPlugin.class",
)
```

2. `check_zip` 签名改为 `def check_zip(zip_path: Path, agent_jar: Path | None = None, main_jar: Path | None = None)`，并在 `with zf:` 内、agent 校验之前加入：

```python
        main_name = "jars/hypernova.jar"
        if main_name in names:
            entries = jar_entries(zf.read(main_name))
            for marker in MAIN_MARKERS:
                if marker not in entries:
                    failures.append(f"packaged main jar missing {marker}")
            if main_jar is not None:
                if not main_jar.is_file():
                    failures.append(f"main jar missing: {main_jar}")
                else:
                    built = jar_entries(main_jar.read_bytes())
                    for marker in MAIN_MARKERS:
                        if marker not in built:
                            failures.append(f"built main jar missing {marker}")
                    if entries and entries != built:
                        failures.append(
                            "packaged main jar entries differ from "
                            f"{main_jar}")
```

3. `main()` 增加 `--main-jar` 并传参：

```python
    ap.add_argument("--main-jar", type=Path)
...
    failures = check_zip(args.zip, args.agent_jar, args.main_jar)
```

- [ ] **Step 4: 修改 `tools/java/build-mod.sh`**

1. 在 `OUT="$ROOT_W/build/java"` 之后加失败清理 trap：

```bash
# 任意失败（含显式 exit 1）都清掉本轮 zip，避免失败路径留下可发布的包。
cleanup_failed_zip() {
  status=$?
  if [ "$status" -ne 0 ]; then
    rm -f "$OUT/hypernova-0.1.0.zip"
  fi
}
trap cleanup_failed_zip EXIT
```

2. `release_check.py` 调用加 `--main-jar "$OUT/hypernova.jar"`：

```bash
python -I "$ROOT_W/tools/release_check.py" --zip "$OUT/hypernova-0.1.0.zip" \
  --agent-jar "$AGENT_JAR" --main-jar "$OUT/hypernova.jar" \
  --sources "$ROOT_W/src/agent/java"
```

- [ ] **Step 5: 运行 pytest 与构建**

Run:
```bash
python -I -m pytest tests/tools/test_release_check.py -q
bash tools/java/build-mod.sh
```
Expected: pytest 全部 passed；build 输出 `OK: ...hypernova-0.1.0.zip`。

- [ ] **Step 6: 验证失败清 zip**

Run（故意把 release_check 指向不存在的主 jar 目录以触发失败，不要动源码）:
```bash
python -I tools/release_check.py --zip build/java/hypernova-0.1.0.zip \
  --agent-jar build/agent/hypernova.agent.jar \
  --main-jar build/java/does-not-exist.jar
```
Expected: `FAIL: main jar missing`，rc=1。该命令不经过 build-mod，不验证 trap；trap 由 build-mod 下次真实失败时生效，记录在报告里即可。

- [ ] **Step 7: 提交**

```bash
git add tools/release_check.py tools/java/build-mod.sh tests/tools/test_release_check.py
git commit -m "fix(m4): require main jar in release checks and clear failed zips"
```

---

### Task 5: 手工验收文档 + 端到端验证 + 结果收口

**Files:**
- Create: `docs/m4-manual-acceptance.md`
- Create: `docs/m4-results.md`
- Modify: `技术笔记-纹理按需加载.md:913`（M4 行）

**Interfaces:**
- Consumes: Task 1–4 的探针行、报告工具、A/B 工具、release_check。
- Produces: 可复跑的 A→B/stutter 协议；M4 结果文档；spec 里程碑回写。

**Dependencies:** Task 1, Task 2, Task 3, Task 4
**Touches:** `docs/m4-manual-acceptance.md`, `docs/m4-results.md`, `技术笔记-纹理按需加载.md`

- [ ] **Step 1: 新建 `docs/m4-manual-acceptance.md`**

```markdown
# M4 手动验收：A→B 长会话与 >200 ms stutter

> 本文件只写步骤与判定，不预填结果。frame-time probe 默认关闭，只有
> 显式加 `-Dhypernova.frameProbe=true` 才采样。A→B 与 stutter 必须由
> 真实游戏进程 + 真实存档完成；菜单快照、单轮 smoke、`sceneEvictMsMax`
> 都不能替代。

## 1. 前置

1. **先确认主 mod（textures 模块）已启用**。`HYPERNOVA_FRAME` 由主 mod 的
   `HypernovaPlugin` 构造 `FrameTimeProbe` 后产生；只加载 agent 不会产生帧行。
   `Starsector-098-260mods/mods/enabled_mods.json` 默认**不启用**
   `hypernova_infinite_engine`，先备份再临时追加：

   ```bash
   cp Starsector-098-260mods/mods/enabled_mods.json \
      Starsector-098-260mods/mods/enabled_mods.json.bak-m4
   python -I - <<'PY'
   import json
   from pathlib import Path
   p = Path("Starsector-098-260mods/mods/enabled_mods.json")
   data = json.loads(p.read_text(encoding="utf-8"))
   ids = data["enabledMods"]
   if "hypernova_infinite_engine" not in ids:
       ids.append("hypernova_infinite_engine")
   p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
   PY
   ```

   验收结束后恢复原配置：

   ```bash
   cp Starsector-098-260mods/mods/enabled_mods.json.bak-m4 \
      Starsector-098-260mods/mods/enabled_mods.json
   ```

   > **口径**：启用主 mod 会同时激活 `HypernovaPlugin` 的 manifest/prefetch
   > 路径，所以本验收测的是“**textures 模块 + agent**”，不是 agent-only。
   > 若必须保留 agent-only 数据，probe 无法运行；此时只能用外部帧时间工具
   > （如 RTSS / MSI Afterburner）观察 stutter，**不能**填
   > `frame_probe.present=true`，也不能替代 Hypernova probe。
   >
   > **替代环境（高级）**：`Starsector-098-Base` 已启用该模块，但它使用
   > `starsector-core/fr.vmparams` 作为启动参数文件，且该文件**没有** lazy
   > flags。必须：
   > 1. `bash tools/java/install-manifest.sh Starsector-098-Base` 刷新主 jar；
   > 2. `python tools/install_agent.py --game Starsector-098-Base --env base`
   >    刷新 agent（`--env base` 对应 `starsector-core/fr.vmparams`）；
   > 3. 用下面的脚本把 `fr.vmparams` 派生成
   >    `Starsector-098-Base/starsector-core/fr_m4_probe.vmparams`；
   > 4. 报告命令改用 Base 路径：
   >    `Starsector-098-Base/saves/hypernova/scripts-agent.log` 与
   >    `Starsector-098-Base/starsector-core/starsector.log`。
   > 缺点：Base 的 mod 数远少于 260mods。

   Base 派生脚本（必须在主类之前插入全部五行；`fr.vmparams` 没有 lazy flags）：

   ```bash
   python -I - <<'PY'
   from pathlib import Path
   src = Path("Starsector-098-Base/starsector-core/fr.vmparams")
   dst = Path("Starsector-098-Base/starsector-core/fr_m4_probe.vmparams")
   flags = [
       "-Dhypernova.textures.lazy=true",
       "-Dhypernova.textures.lazy.dds=true",
       "-Dhypernova.textures.lazy.eviction=true",
       "-Dhypernova.textures.lazy.eviction.sceneUnload=false",
       "-Dhypernova.frameProbe=true",
   ]
   lines = src.read_text(encoding="utf-8").splitlines()
   out = []
   inserted = False
   for line in lines:
       s = line.strip()
       if s == "com.fs.starfarer.StarfarerLauncher":
           out.extend(flags)
           out.append(line)
           inserted = True
       elif s.startswith("-Dhypernova.textures.lazy.") or s == "-Dhypernova.frameProbe=true":
           continue
       else:
           out.append(line)
   if not inserted:
       raise SystemExit("main class not found")
   dst.write_text("\n".join(out) + "\n", encoding="utf-8")
   PY
   ```

2. 构建并安装（主 jar + agent jar 都要刷新，否则 probe 仍是旧 class）：
   `bash tools/java/build-mod.sh` →
   `bash tools/java/install-manifest.sh Starsector-098-260mods` →
   `python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite`
3. 确认 `Starsector-098-260mods/starsector-core/graphics/hypernova/blank.png` 非空。
4. 每组开始前清空或改名：
   - `Starsector-098-260mods/saves/hypernova/scripts-agent.log`
   - `Starsector-098-260mods/starsector-core/starsector.log`
5. 使用干净存档 / 小舰队；不要用 260mods 生涯大地图、Star Wars 新开局、
   超大舰队或 Exotica 改装 UI（这些是已知 mod 环境问题，不归因 Hypernova）。
6. 默认开关不动；本验收只用启动参数临时开启。

## 2. 启动参数（probe + 当前 LRU）

**`-D` 必须写在 `com.fs.starfarer.StarfarerLauncher` 之前。** argfile 里主类
之后的 token 会被 JVM 当作应用参数，不再是 JVM 选项；在文件末尾追加 `-D`
不会生效。不要手工往 `Miko_Lite.txt` 末尾追加。

以 `Miko_Lite_m28_treatment.txt` 为模板（它的 lazy flags 已在主类之前），
用下面的脚本生成 `Miko_Lite_m4_probe.txt`：

```bash
python -I - <<'PY'
from pathlib import Path
src = Path("Starsector-098-260mods/Miko_Lite_m28_treatment.txt")
dst = Path("Starsector-098-260mods/Miko_Lite_m4_probe.txt")
lines = src.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    s = line.strip()
    if s.startswith("-Dhypernova.textures.lazy.eviction.sceneUnload="):
        out.append("-Dhypernova.textures.lazy.eviction.sceneUnload=false")
    elif s == "com.fs.starfarer.StarfarerLauncher":
        if "-Dhypernova.frameProbe=true" not in out:
            out.append("-Dhypernova.frameProbe=true")
        out.append(line)
    else:
        out.append(line)
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
```

脚本保证 `-Dhypernova.frameProbe=true` 在主类之前，并把
`textures.lazy.eviction.sceneUnload` 设为 `false`；template 里已有
`lazy=true` / `dds=true` / `eviction=true`。

启动（把下面保存为 `Starsector-098-260mods\run_m4.bat` 后双击/执行；
`%~dp0` 只在 .bat 中展开，直接粘进 PowerShell/cmd 会解析错路径。
PowerShell 内联可用 `$PSScriptRoot`）：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\LaunchMiko.ps1" "jdk-28+13" "..\Miko_Lite_m4_probe.txt"
```

不要改 `hypernova.json`，不要设置 `budgetBytes`。

## 3. GPU 曲线（A/B 各自独立采样）

**不要用同一个累计 CSV 生成 A/B 两份报告。** 如果从进程启动一直写到 B 结束，
B 的 `gpu.dedicated_mb.median` 会包含“启动 + 菜单 + A + B”，把 A→B 差值稀释。

A 场景开始时取游戏 PID，另开一个 shell 采样到 `build/m4/gpu-a.csv`：

```bash
mkdir -p build/m4
GPU_OUT=build/m4/gpu-a.csv   # B 场景改为 build/m4/gpu-b.csv
python -I - "$PID" > "$GPU_OUT" <<'PY'
import sys
import time

sys.path.insert(0, "tools")
import smoke_run

print("timestamp,dedicated_mb,shared_mb")
start = time.monotonic()
while True:
    dedicated, shared = smoke_run.process_gpu_memory_mb(int(sys.argv[1]))
    stamp = f"{time.monotonic() - start:.1f}"
    print(f"{stamp},{'' if dedicated is None else dedicated},"
          f"{'' if shared is None else shared}", flush=True)
    time.sleep(2)
PY
```

A 结束立即 Ctrl-C 停止采样。进入 B 场景后，**不要重启游戏**：用**同一个游戏
进程 PID** 重新启动同一个采样器，只把 `GPU_OUT` 改为 `build/m4/gpu-b.csv`；
B 结束再 Ctrl-C。重启游戏会使 `frames`/`over200`/`longGaps` 的 B−A 累计差值
和 A→B 场景对比失效。
采样期间不要最小化窗口或长时间暂停。

## 4. A→B 会话

1. **加载存档后先做启动检查**：在 `starsector.log` 里搜索
   `Hypernova frame probe enabled`：
   ```bash
   grep -c "Hypernova frame probe enabled" \
     Starsector-098-260mods/starsector-core/starsector.log
   ```
   输出必须 ≥1。若为 0，**停止**：主 mod 没加载或主 jar 是旧的，继续采样
   只会得到空帧报告。
   `HYPERNOVA_FRAME` 行只在**读档后**、主线程 `advance` 开始后才出现；
   主菜单没有 `Global.getSector()`，transient script 不挂载，菜单里 0 帧行
   是预期，不能据此判定 probe 失败。
2. **A 场景 10 min**：同一星系内正常活动（移动、开舰队/改装、接触对话），
   不进战斗或只打一场短战斗；不要暂停。
3. A 结束立即生成报告（此时 agent summary 是 A 的最后一轮）：
   ```bash
   python -I tools/m4_session_report.py \
     --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
     --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
     --gpu-csv build/m4/gpu-a.csv \
     --out build/m4/session-a.json --require-frame --text
   ```
4. **B 场景 10 min**：跳跃到另一个星系，重复类似活动。
5. B 结束再跑一次同命令（`--gpu-csv build/m4/gpu-b.csv`），
   `--out build/m4/session-b.json`。
6. 对比 A/B 的 `gpu.dedicated_mb.median`、`liveBytes`、`evictableBytes`；
   记录差值，不把单点当净 VRAM。
7. **帧计数是累计值**：`session-a.json` 覆盖启动+A，`session-b.json` 覆盖
   启动+A+B。要得到 B-only 计数，必须做差：
   `B.frames - A.frames`、`B.over200 - A.over200`、`B.longGaps - A.longGaps`。
   `maxMs` / `p99Ms` 是累计会话统计，**不能相减**；两份都报，并把 B 的
   标为 cumulative，不能当作 B-only P99。GPU 同理必须用 §3 的独立 CSV。

## 5. >200 ms stutter 判定

> `HYPERNOVA_FRAME` 行只在加载存档后出现；主菜单里没有帧行是预期
> （菜单没有 `Global.getSector()`，transient script 不挂载）。

报告里的 `frame_probe`：

- `over200`：严格大于 200 ms 的帧数；
- `maxMs`：最大帧时间；
- `p99Ms`：1 ms 直方图估算的 P99；
- `longGaps`：大于 5 s 的间隔（暂停/读档/alt-tab），不计入帧统计。

判定：

- **帧行合理性**：`frames` 应接近“会话时长 × 帧率”（例如 10 min × 60 fps ≈ 36,000）。
  如果明显只有一半，先怀疑**相邻真实帧拿到相同的 `amount`**：`amount` 不是唯一
  帧身份，按 amount 去重会误丢帧。反过来，两个入口收到**不同** amount 会导致
  重复计数，而不是丢帧。这是首次实机必须确认的假设。
- `frames`/`over200`/`longGaps` 是探针启动以来的**累计值**；B 的读数包含 A，
  必须按 §4 第 7 步做差。`maxMs`/`p99Ms` 是累计统计，不能相减；B 的 P99
  不是 B-only。
- `longGaps` 应接近 0；若 >0，先说明是暂停/读档/alt-tab，还是真实冻结。
- `over200 > 0` 时必须结合时间点和场景说明；不能只报数字。
- 短于 5 s 的暂停仍会被计为一次大帧；验收期间不要暂停。

## 6. 判定表

| 项 | 通过条件 | 结果 |
|---|---|---|
| frame probe 存在 | `session.json` 中 `frame_probe.present=true` | 待填 |
| 纹理错误 | 五类总数 = 0 | 待填 |
| lazy 健康 | `failed/disabled/dimMismatch/failedParked=0`、`main != none` | 待填 |
| A→B GPU dedicated | 记录 A/B 中位与差；不宣称净收益除非有重复证据 | 待填 |
| A→B live/evictable | 记录漂移；`evictable` 恒等式成立 | 待填 |
| stutter | `over200`/`maxMs`/`p99Ms` 有数；异常需场景解释 | 待填 |
| 外部帧工具（仅 stutter 兜底） | 提供外部 `over200`/`maxMs` 读数；**不能**填 `frame_probe.present=true`，也不能替代 Hypernova probe | 待填 |
| 崩溃/白块/错位 | 无 | 待填 |

任一项失败：记录日志与读数，关闭临时参数，回退到默认 off；不要修改发行默认值。
```

- [ ] **Step 2: 跑全量自动化验证**

Run:
```bash
bash tools/java/run-tests.sh
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
bash tools/java/build-mod.sh
bash tools/java/install-manifest.sh Starsector-098-260mods
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
```
Expected: 主测试全绿；agent `found/pass` 与 M2.8 基线一致（1 个 Windows symlink abort 可接受）；pytest 全部 passed；build OK；`install-manifest.sh` 输出 `verified: installed jar matches build output`；`install_agent.py` 输出 installed 且不改 vmparams。安装后核对
`build/java/hypernova.jar` 与 `Starsector-098-260mods/mods/hypernova_infinite_engine/jars/hypernova.jar` 的 SHA256 一致。

- [ ] **Step 3: 实机 smoke（probe 开启不崩、菜单不产帧行的口径）**

Run:
```bash
mkdir -p build/m4
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 20 \
  --jvm-arg=-Dhypernova.frameProbe=true \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --json-out build/m4/smoke-probe.json
```
Expected: 到达主菜单、正常退出。**菜单没有 `Global.getSector()`，transient script 不挂载，
因此这里不应期待 `HYPERNOVA_FRAME` 行**；本步骤只证明 probe 开启不崩、菜单启动不受影响。
真正的帧行证据属于 A→B 用户 gate（加载存档后才有 advance）。

- [ ] **Step 4: 用报告工具解析 smoke（非帧部分）**

Run:
```bash
python -I tools/m4_session_report.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m4/smoke-report.json --text
```
Expected: rc=0；`lazy.present=true`（菜单会话有 summary）；`frame_probe.present=false`
是预期（未加载存档）；纹理错误总数 0。帧探针行的解析由 `test_m4_session_report.py`
的合成用例覆盖；实机帧行留给 A→B gate。

- [ ] **Step 5: A/B 工具修好后的实跑**

Run:
```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 1 \
  --out build/m4/ab-fix.json
```
Expected: rc=0；`gates.treatment_stats_present=true`；`lazy_median` 非 null；
`gates.treatment_dds_hit_positive=true`。若 rc=1，按 gate 名记录，不掩盖。

- [ ] **Step 6: 写 `docs/m4-results.md`**

```markdown
# M4 结果：验收 & 发布硬化

- **日期**：2026-11-02
- **状态**：代码/工具侧完成；A→B/stutter 用户 gate 待执行/已完成（按实际写）。
- **默认**：未改任何默认开关；frame probe 默认 off。

## 1. 结论

1. frame-time probe 默认 off，`-Dhypernova.frameProbe=true` 开启；关闭时只做一次
   null 检查；按引擎帧 `amount` 去重，门闩后采样。
2. 会话报告工具把 frame probe、lazy summary、五类纹理错误、GPU CSV 合并为一份 JSON。
3. A/B 工具修复：treatment stats 立即抓取、`--rounds>=1`、timeout 按 pid 文件清理。
4. release_check 要求主 jar；build-mod 任意失败清 zip。
5. A→B/stutter：见第 5 节（未执行时明确写“未执行，user gate 待跑”）。

## 2. 验证

（填实际数字：主测试数、agent found/pass/abort、pytest 数、build hash、安装 hash。）

## 3. 实机 smoke

（填 `build/m4/smoke-probe.json` 的 menu_s、`build/m4/smoke-report.json` 的
frame_probe/lazy/texture_errors。）

## 4. A/B 工具实跑

（填 `build/m4/ab-fix.json` 的 control/treatment median、gates、lazy_median。）

## 5. A→B / stutter user gate

（按 `docs/m4-manual-acceptance.md` 执行后填；未执行就写未执行及原因。）

## 6. 限制

- summary 每 10 s 一条，最后一条最多旧 10 s；
- `p99Ms` 是 1 ms 桶估算，不是逐帧原始值；
- `longGaps` 只排除 >5 s，短暂停仍会算作大帧；
- 260mods 大地图/mod 环境问题不归因 Hypernova；
- 本轮不默认开启、不宣称显存收益。

## 7. 下一步

M6（汉化/中文输入兼容审计）→ M5（默认开启 canary + 发行）。
```

- [ ] **Step 7: 回写 spec §7 M4 行**

把 `技术笔记-纹理按需加载.md` 里程碑表里的 M4 行改为
`**M4（验收 & 发布硬化）✔（代码/工具侧，2026-11-02；frame probe 默认 off；A→B/stutter
见 docs/m4-results.md）**`，并在里程碑链里同步。

- [ ] **Step 8: 提交**

```bash
git add docs/m4-manual-acceptance.md docs/m4-results.md 技术笔记-纹理按需加载.md \
        docs/superpowers/plans/2026-11-02-m4-acceptance-hardening.md
git commit -m "docs(m4): record acceptance tooling and user gate"
```

---

## Self-Review

### Spec coverage

| 需求 | 任务 |
|---|---|
| frame-time probe（默认 off、零成本、双入口门闩后） | Task 1 |
| 手动会话报告工具（frame/lazy/GPU/纹理错误） | Task 2 |
| `m26_ab.py` stats 捕获时点 | Task 3 |
| `m26_ab.py` `--rounds>=1` | Task 3 |
| `m26_ab.py` timeout 子进程 | Task 3 |
| `lazy_median=null` 假阴性 | Task 3 |
| `release_check.py` 要求主 jar | Task 4 |
| `build-mod.sh` 失败清 zip | Task 4 |
| A→B 长会话 + >200 ms stutter 用户验收 | Task 5 |
| 全量测试/release_check 绿 | Task 5 |
| 不默认开启 | Global Constraints + Task 1/5 |

### Placeholder scan

计划内无 TBD/TODO/悬空 stub；所有新增函数都有签名、行为与测试。唯一“待填”是
`docs/m4-results.md` 的实机数字，必须由 Task 5 的运行结果填写，不得预填。

### Type consistency

- Java：`FrameTimeProbe(int)`、`frame(long nowNanos, float amount)`、`lineIfDue()`、`line()` 在 Task 1
  定义，Task 2 的 Python 只解析其文本行，不依赖 Java 类型。
- Python：`cleanup_timed_out_game(Path)->bool` 在 Task 3 定义并在 `run_round` 使用；
  `clear_pid_file(str)->None` 在 smoke_run 定义并被 `one_round` 使用。
- `release_check.check_zip` 的三参签名与 `main()` 调用一致；测试同时覆盖两参与三参。

### Review Focus coverage

1. 长帧双入口 → `FrameTimeProbeTest.duplicateAmountIsIgnored`。
2. 关闭时零成本 → `AssemblyWiringTest.frameProbeRunsAfterGateAndOnlyWhenPresent`。
3. 会话切片串档 → `test_m4_session_report.py` 的两个 anchor 用例。
4. A/B stats 被覆盖 → `test_stats_captured_before_later_control_session`。
5. timeout 残留进程 → `test_timeout_kills_recorded_game_pid` + `test_one_round_writes_and_clears_pid_file`。
