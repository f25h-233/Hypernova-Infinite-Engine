# M2.6 default-on gates fix（I-1 自动淘汰 + I-2 owned）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 M2.6 的自动淘汰从“同名 BaseGameState 重入才可达”改成**确定性主线程触发**（真实的 `Global.getCurrentState()==COMBAT` 门禁、预算/场景 arm、部分 pass 重 arm），并让淘汰**只删本组件 owned 的 GL id**；用 budget=1 的真实进程 smoke 证明 `evictPasses>0`，再重跑 A/B/selftest，然后 push experimental/default-off。

**Architecture:** 不新增 transformer。`LazyTextures` 的 `lookup` / `onProxyUse`（已经是主线程热路径，和 `maybeRunSelfTest` 同模式）调用 `maybeRunEviction(now)`；`noteGameState` 只负责状态切换 arm；`evictPass` 结束时按 `nextDueAfterPass` 重 arm。战斗门禁通过反射 `com.fs.starfarer.api.Global.getCurrentState()`（`COMBAT`），不可用时保守地不淘汰。`selectVictims`/`evictOne` 增加 `owned` 门；`materializePng` 的 id 也是本组件创建的，改 `owned=true`；引擎 `onRegister`/`noteEngineHit` 保持 `owned=false`。

**Tech Stack:** Java 17（major 61）、ASM 9.1、Python 3.14 stdlib（`python -I`）、pytest 9、JUnit 5、`tools/smoke_run.py`、`tools/m26_ab.py`、Git Bash。

**Spec:** `docs/m26-results.md`（M2.6 current results）、`.superpowers/sdd/2026-11-01-m26-dds-lru/final-review.md`（I-1/I-2/§5/§7）、`技术笔记-纹理按需加载.md` §5.7/§6.1/§7、REQ-R1-10、INV-08/10。

---

## Global Constraints

- **默认 off 不变**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`（本 fix 不为默认开启）。
- **线程红线**：淘汰/GL 删除/`maybeRunEviction` 只在 `runtimeMain`；loading/worker 路径直接返回。`drainPendingDeletes` 也只在主线程。
- **战斗门禁**：`com.fs.starfarer.api.Global.getCurrentState()` 反射；`COMBAT` 时不下淘汰；反射不可用 → 保守地**不淘汰**（返回 true），记录一次。
- **owned-only**：`selectVictims`/`evictOne` 只处理 `owned=true`；`materializePng`/`materializeDds` 的 id 都是本组件创建，`owned=true`；`onRegister`/`noteEngineHit` 的引擎真实对象 `owned=false`，永不被删。
- **无新 transformer/无新依赖**；agent 不 import 游戏/FR 类（反射）。
- **测试**：每个 Task TDD；纯函数覆盖 arm/换名/到点/未到点/预算/重 arm；`isInCombat` 用 fixture `com.fs.starfarer.api.Global` 覆盖 COMBAT/CAMPAIGN/null。
- **真实门禁**：budget=1/grace=0 smoke 必须 `evictPasses>=1`；selftest 必须 `1/1/1`；修后 A/B n=3 记录 `ddsHit/failed/disabled/dimMismatch/0 errors`。
- **不 push 前**：Task 1/2 + scoped review + docs 完成后，才按用户选项 3 push；不默认开启。
- **Escape hatch**：若实现与计划不符按实际修正并报告；若需求自相矛盾/无法同时满足 → 停下报告。

## Review Focus

1. **自动触发可达性**：`lookup`/`onProxyUse` 不论 selftest 开关都调用 `maybeRunEviction`；`noteGameState` 换名只 arm，不再“当次立即检查”；`evictPass` 部分成功后重 arm；`drainPendingDeletes` 同点。
2. **战斗保护真实**：`Global.getCurrentState()` 的 `COMBAT`；不可用保守不淘汰；不能用 `lastStateName` 的 `isCombatState`（空转）。
3. **owned 语义**：PNG syncLoad id 属于本组件；引擎真实对象 id 永不被删；selftest pick 的 DDS owned；engine-owned 单测排除。
4. **热路径开销**：`maybeRunEviction` 在 `lookup`/`onProxyUse` 每 bind 调用；先 `Thread.currentThread()!=runtimeMain` 返回，再只有 `eviction` 开才做 due/战斗检查；A/B 需复核无菜单回退。
5. **不重开 M2.6 的已闭合 gates**：generation/I2/I3/m4/DDS/占位/id 卫生不变。

---

## Pre-flight（controller）

- Mode: `pipeline`（I-1/I-2 同文件，顺序）。
- BASE: `6bf0ecb`（M2.6 final fix）。
- Workspace: `.superpowers/sdd/2026-11-02-m26-default-on-gates/`。
- Rulings:
  - **R-M26-15**：PNG `syncLoad` 的 GL id 是本组件创建，`owned=true`；`onRegister`/`noteEngineHit` 的引擎真实对象仍 `owned=false`。
  - **R-M26-16**：战斗信号用 `Global.getCurrentState()`；不可用保守 `true`（不淘汰），日志一次。
  - **R-M26-17**：用户选 3；fix + scoped review + 回归全绿后 push `origin/main`；任何 gate 失败停下报告。
- Dependencies/Touches:
  - Task 1: `src/agent/.../LazyTextures.java`；`tests/agent/.../LazyEvictionTest.java`；新增 `tests/agent/fixtures/com/fs/starfarer/api/Global.java`。
  - Task 2: `docs/m26-results.md`；`技术笔记`/`大饼`（状态/gates）；运行 `build/m26/*`；不改代码。

---

## Task 1: I-1 确定性自动淘汰 + I-2 owned-only（代码 + 单测）

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`
- Create: `tests/agent/fixtures/com/fs/starfarer/api/Global.java`

**Interfaces:**
- Consumes: 现有 `evictDueNanos`/`eviction*`/`evictPass`/`selectVictims`/`evictOne`/`drainPendingDeletes`/`PENDING_DELETE`/`materializePng`/`noteMaterialized`。
- Produces:
  - `LazyTextures.maybeRunEviction(long now)`；`shouldRunEviction(boolean,boolean,long,long,boolean)`；`shouldArmOnTransition(String,String)`；`shouldArmOnBudget(long,long,long)`；`nextDueAfterPass(long,long,long,long,int)`。
  - `LazyTextures.isInCombat()`；`GameState` fixture `com.fs.starfarer.api.Global.getCurrentState()`。
  - `evictPass(long now)`（签名变化）；`evictDueNanos` 重 arm。
  - `selectVictims`/`evictOne` 的 `owned` 门；`materializePng` 的 `owned=true`。

**Constraints:** 不改默认值；不改 Task 0-4 的其它 gates；不新增 transformer；测试不启动游戏。

---

- [ ] **Step 1: 写失败测试**

Create `tests/agent/fixtures/com/fs/starfarer/api/Global.java`:

```java
package com.fs.starfarer.api;

/** Test fixture for the game's state enum probe. */
public class Global {
    public static Object currentState;

    public static Object getCurrentState() {
        return currentState;
    }
}
```

Modify `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`:

- `entry(...)` 设置 `e.owned = true;`（正常可淘汰）。
- Add:

```java
    @Test
    void engineOwnedEntriesAreNotEvicted() {
        LazyTextures.ProxyEntry engine = entry("engine", 10, 100);
        engine.owned = false;
        LazyTextures.ProxyEntry mine = entry("mine", 10, 100);
        assertEquals(List.of(mine), LazyTextures.selectVictims(
                List.of(engine, mine), 150, 100, 0, 10_000, 10));
        assertFalse(LazyTextures.evictOneForTest(engine, true));
    }

    @Test
    void evictionScheduleTruthTable() {
        assertTrue(LazyTextures.shouldRunEviction(true, false, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 101, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 100, 100, true));
        assertFalse(LazyTextures.shouldRunEviction(false, false, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, true, 100, 100, false));
        assertFalse(LazyTextures.shouldRunEviction(true, false, 0, 100, false));
    }

    @Test
    void transitionArmsOnlyWhenNameChanges() {
        assertTrue(LazyTextures.shouldArmOnTransition("TITLE", "CAMPAIGN"));
        assertFalse(LazyTextures.shouldArmOnTransition("CAMPAIGN", "CAMPAIGN"));
        assertFalse(LazyTextures.shouldArmOnTransition(null, "TITLE"));
    }

    @Test
    void partialPassRearmsOnlyWhileOverBudget() {
        assertEquals(1_123, LazyTextures.nextDueAfterPass(1_000, 123, 200, 100, 1));
        assertEquals(0, LazyTextures.nextDueAfterPass(1_000, 123, 100, 100, 1));
        // empty pass over budget: back off, do not scan 45k proxies on every materialization
        assertEquals(1_000 + LazyTextures.EVICT_EMPTY_BACKOFF_NANOS,
                LazyTextures.nextDueAfterPass(1_000, 123, 200, 100, 0));
    }

    @Test
    void budgetArmOnlyWhenIdle() {
        assertTrue(LazyTextures.shouldArmOnBudget(0, 200, 100));
        assertFalse(LazyTextures.shouldArmOnBudget(123, 200, 100));
        assertFalse(LazyTextures.shouldArmOnBudget(0, 100, 100));
    }

    @Test
    void combatProbeUsesGameState() {
        LazyTextures.resetGateStateForTest();
        com.fs.starfarer.api.Global.currentState = "COMBAT";
        assertTrue(LazyTextures.isInCombat());
        com.fs.starfarer.api.Global.currentState = "CAMPAIGN";
        assertFalse(LazyTextures.isInCombat());
        com.fs.starfarer.api.Global.currentState = null;
        assertFalse(LazyTextures.isInCombat());
        LazyTextures.resetGateStateForTest();
    }
```

Add a package-private test seam in `LazyTextures` (for `evictOne` from tests):

```java
    static boolean evictOneForTest(ProxyEntry e, boolean force) {
        return evictOne(e, force);
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`
Expected: 编译失败（`shouldRunEviction`/`shouldArmOnTransition`/`nextDueAfterPass`/`isInCombat`/`evictOneForTest` 不存在；`entry` 未 owned 导致后续 null）。

- [ ] **Step 3: 实现 I-1/I-2**

3a. Fields (near the eviction state block):

```java
    // ---- M2.6 default-on fix: deterministic eviction + real combat signal ----
    private static volatile Method gameStateMethod;
    private static volatile boolean gameStateResolved;
    private static final AtomicBoolean GAME_STATE_FAIL_LOGGED = new AtomicBoolean();
    static final long EVICT_EMPTY_BACKOFF_NANOS = 30_000_000_000L;
```

3b. `resetGateStateForTest` 追加：

```java
        gameStateMethod = null;
        gameStateResolved = false;
        GAME_STATE_FAIL_LOGGED.set(false);
```

3c. Replace `noteGameState` + delete `isCombatState`; add schedule/probe methods:

```java
    static void noteGameState(String name) {
        long now = System.nanoTime();
        if (eviction) {
            String prev = lastStateName;
            if (shouldArmOnTransition(prev, name)) {
                evictDueNanos = now + evictionSceneDelayNanos;
                long n = ++stateTransitions;
                if (n <= 20) {
                    AgentLog.info("lazy: state " + prev + " -> " + name
                            + "; eviction due in " + (evictionSceneDelayNanos / 1_000_000L) + " ms");
                }
            }
            lastStateName = name;
        }
        maybeRunEviction(now);
        maybeRunSelfTest(now);
    }

    static boolean shouldArmOnTransition(String prev, String name) {
        return prev != null && name != null && !prev.equals(name);
    }

    static boolean shouldRunEviction(boolean eviction, boolean disabled, long dueNanos,
                                     long now, boolean inCombat) {
        return eviction && !disabled && dueNanos != 0 && now >= dueNanos && !inCombat;
    }

    static long nextDueAfterPass(long now, long delay, long liveBytes, long budget, int evicted) {
        if (liveBytes <= budget) return 0;
        if (evicted > 0) return now + delay;
        return now + Math.max(delay, EVICT_EMPTY_BACKOFF_NANOS);
    }

    static boolean shouldArmOnBudget(long dueNanos, long liveBytes, long budget) {
        return dueNanos == 0 && liveBytes > budget;
    }

    static void maybeRunEviction(long now) {
        if (Thread.currentThread() != runtimeMain) return;
        if (!PENDING_DELETE.isEmpty()) drainPendingDeletes();
        if (!eviction || disabled) return;
        long due = evictDueNanos;
        if (due == 0 || now < due) return;
        boolean combat = isInCombat();
        if (!shouldRunEviction(eviction, disabled, due, now, combat)) {
            if (combat) {
                evictDueNanos = now + evictionSceneDelayNanos;
            }
            return;
        }
        evictDueNanos = 0;
        evictPass(now);
    }

    static boolean isInCombat() {
        Method m = resolveGameStateMethod();
        if (m == null) return true; // conservative: unknown -> do not evict
        try {
            Object state = m.invoke(null);
            return state != null && "COMBAT".equals(String.valueOf(state));
        } catch (Throwable t) {
            return true;
        }
    }

    private static Method resolveGameStateMethod() {
        Method m = gameStateMethod;
        if (m != null || gameStateResolved) return m;
        synchronized (LazyTextures.class) {
            if (gameStateResolved) return gameStateMethod;
            try {
                Class<?> global = Class.forName("com.fs.starfarer.api.Global", false,
                        LazyTextures.class.getClassLoader());
                gameStateMethod = global.getMethod("getCurrentState");
            } catch (Throwable t) {
                if (GAME_STATE_FAIL_LOGGED.compareAndSet(false, true)) {
                    AgentLog.fail("lazy: game state probe unavailable; eviction disabled", t);
                }
            } finally {
                gameStateResolved = true;
            }
            return gameStateMethod;
        }
    }
```

3d. `lookup` and `onProxyUse` — replace the selftest-only trigger with both:

```java
            long now = System.nanoTime();
            maybeRunEviction(now);
            if (selftest) maybeRunSelfTest(now);
```

- `lookup`: after `if (path == null) return null;` inside try.
- `onProxyUse`: at the start of try (before `if (proxy == null)`).

3e. `evictPass` signature + re-arm:

```java
    private static void evictPass(long now) {
        if (!eviction || disabled || Thread.currentThread() != runtimeMain) return;
        long live = LIVE_BYTES.get();
        long budget = budgetBytes();
        if (live <= budget) return;
        List<ProxyEntry> ready = new ArrayList<>();
        for (ProxyEntry e : PROXIES.values()) {
            if (e.ready) ready.add(e);
        }
        List<ProxyEntry> victims = selectVictims(ready, live, budget,
                evictionGraceNanos, now, evictionMaxPerPass);
        int n = 0;
        long bytes = 0;
        for (ProxyEntry e : victims) {
            long b = e.bytes;
            if (evictOne(e, false)) {
                n++;
                bytes += b;
            }
        }
        EVICT_PASSES.incrementAndGet();
        if (n > 0) {
            AgentLog.info("lazy: eviction pass evicted=" + n + " bytes=" + bytes
                    + " live=" + LIVE_BYTES.get() + " budget=" + budget);
        }
        evictDueNanos = nextDueAfterPass(now, evictionSceneDelayNanos,
                LIVE_BYTES.get(), budget, n);
    }
```

3f. `selectVictims` add the owned gate:

```java
            if (!e.owned) continue;
```

after the `ready/bytes/glId` check.

3g. `evictOne` add the owned gate:

```java
        if (!e.owned) return false;
```

after the null/ready/glId/obj check (before force/startup).

3h. `materializePng` change `e.owned = false;` → `e.owned = true;`.

3i. `noteMaterialized` must not push an existing due; replace the budget arm with:

```java
        if (eviction && budgetBytes() != Long.MAX_VALUE
                && shouldArmOnBudget(evictDueNanos, LIVE_BYTES.get(), budgetBytes())) {
            evictDueNanos = System.nanoTime() + evictionSceneDelayNanos;
        }
```

3j. Add test seam (near `evictOne`):

```java
    static boolean evictOneForTest(ProxyEntry e, boolean force) {
        return evictOne(e, force);
    }
```

- [ ] **Step 4: 跑测试通过**

Run:
```bash
bash tools/java/run-agent-tests.sh LazyEviction
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
```
Expected: LazyEviction 12/12（5 个旧 + 7 个新）；full agent 172 found / 171 pass / 1 known symlink abort / 0 fail；pytest 287 passed。实际计数以报告为准。

- [ ] **Step 5: 提交**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java \
        tests/agent/fixtures/com/fs/starfarer/api/Global.java
git commit -m "fix(m26): make eviction trigger deterministic and owned-only"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## Task 2: 真实进程 auto-eviction gate + 修后 A/B + docs

**Files:**
- Modify: `docs/m26-results.md`
- Modify: `技术笔记-纹理按需加载.md`（M2.6 状态/gates）
- Modify: `大饼-DDS按需物化与LRU.md`（状态）
- Run: `build/m26/fix-auto.json`、`build/m26/ab-fix.json`、`build/m26/selftest-fix.json`

**Interfaces:**
- Consumes: Task 1 commit；`tools/smoke_run.py`、`tools/m26_ab.py`、`tools/install_agent.py`、`tools/install_manifest.py`、`graphics/hypernova/blank.png`。
- Produces: 真实 `evictPasses>=1` 证据；修后 A/B 数字；docs/gates 更新。

**Constraints:** 不改代码；不默认开；不 push（controller 在 scoped review 后按用户选项 3）；不 manual visual。

---

- [ ] **Step 1: 构建/安装新 agent + 两侧 skip/blank**

```bash
bash tools/java/run-agent-tests.sh
bash tools/java/build-mod.sh
python -I tools/install_manifest.py --game-root Starsector-098-260mods
python -I tools/install_manifest.py --game-root Starsector-098-Base
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
python -I tools/install_agent.py --game Starsector-098-Base --env base
for g in Starsector-098-260mods Starsector-098-Base; do
  mkdir -p "$g/mods/hypernova_infinite_engine/graphics"
  cp -r graphics/. "$g/mods/hypernova_infinite_engine/graphics/"
  mkdir -p "$g/starsector-core/graphics/hypernova"
  cp graphics/hypernova/blank.png "$g/starsector-core/graphics/hypernova/blank.png"
done
```

- [ ] **Step 2: budget=1/grace=0 + selftest 的真实进程 gate**

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 20 \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --jvm-arg=-Dhypernova.textures.lazy.eviction=true \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.budgetMb=1 \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.graceMs=0 \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.sceneDelayMs=100 \
  --jvm-arg=-Dhypernova.textures.lazy.selftest=true \
  --json-out build/m26/fix-auto.json
```
Expected: `selftest=1`; `evictPasses>=1`（自动触发可达）；`evicted>=1`（selftest 强制或 auto）；`rematerialized>=1`；`placeholder` 非 0；`failed=0/disabled=0/dimMismatch=0`；0 Failed/Verify/Class/Async/Corrupted。若 `evictPasses=0`，停下报告——自动触发没修好。

- [ ] **Step 3: selftest 默认预算（回归）**

```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 1 --linger 20 \
  --eviction --selftest --out build/m26/selftest-fix.json
```
Expected: `selftest_ok=true`; `selftest=1/evicted=1/rematerialized=1`; `evictPasses` 可为 0（无预算压力）；0 errors。

- [ ] **Step 4: 修后 A/B n=3（eviction off）**

```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 3 --linger 20 \
  --out build/m26/ab-fix.json
```
- 若整条超 Bash 超时：后台跑或拆三个 `--rounds 1`（`ab-fix-pair{1,2,3}.json`），不改 n。
- Expected: all gates true；`ddsHit>0`、`ddsDisabled/dimMismatch/failed/disabled=0`；0 errors。记录 C/T 中位、paired、进程 GPU。

- [ ] **Step 5: 更新 docs**

`docs/m26-results.md`:
- §1/§3：用 `ab-fix.json` 的新 A/B 数字替换/并列旧表；保留 +2.0 边界口径，不写时间收益。
- §7.5：I-2 owned 已修（`selectVictims/evictOne` 只 owned；PNG owned=true；engine-owned=false 排除）；剩余 **refcount/REQ-R1-10 拒绝并记录**与第三方 id 缓存仍未实现（default-on gate 缩小，不消失）。
- §7.7：I-1 已修：`maybeRunEviction` 从 lookup/onProxyUse + noteGameState 确定性触发；真实 `Global.getCurrentState()==COMBAT` 门禁；部分 pass 重 arm；budget=1 smoke `evictPasses>=1`；`isCombatState` 空转删除。自动 trigger 已证明；真实自动 victim（battle/long session）仍需用户。
- §7.15：把 I-1/I-2 从 open gates 移除/改为“fixed in `<fix commit>`”；剩余 default-on gates：refcount/third-party id、M2.5 W5/W6、W-2/W-3/W-5/W-10、用户 battle/manual/A→B/stutter。
- §8.3：agent-only blank.png 已由 install-manifest.sh 复制+断言；记录 Task 2 的安装命令。
- 数字全部从 `build/m26/*.json` 抄，不手改。

`技术笔记` M2.6 section: 把 I-1/I-2 状态改为 fixed；剩余 gates 一行。
`大饼` 状态: 更新为“I-1/I-2 fixed；remaining default-on gates”。

- [ ] **Step 6: 回归 + 提交 docs**

```bash
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
git add docs/m26-results.md 技术笔记-纹理按需加载.md 大饼-DDS按需物化与LRU.md
git commit -m "docs(m26): record deterministic eviction and owned-only fix"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## Self-review

- **Spec coverage**: I-1 deterministic trigger/combat/re-arm/drain → Task 1; I-2 owned → Task 1; live auto-eviction + A/B + docs → Task 2; remaining refcount/third-party/user → docs §7.15.
- **Step scan**: every step has exact code/test/command; no TBD.
- **Type consistency**: `maybeRunEviction(long)`, `evictPass(long)`, `selectVictims` unchanged signature, `owned` field, fixture `Global.getCurrentState`; tests use the same.
- **Review focus**: each risk has a task test: schedule truth table, combat fixture, owned exclusion, live `evictPasses`, A/B no-overhead.
- **Proportion**: plan code is only the changed methods/tests, not the whole 1600-line file.

**Known residual**: refcount/REQ-R1-10 is not implementable without a global registry; third-party id caches and user battle/manual/A→B/stutter remain default-on gates; `ddsBytes` mips estimate; `evictPass` first-pass cost on main thread to be observed in the budget-1 smoke (menu only).
