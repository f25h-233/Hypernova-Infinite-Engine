# M2.7 有界 LRU 默认开启资格（default-on readiness）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭 M2.6 剩下的**代码侧** default-on gates（预算口径、W-5/W-10、DDS fallback 盲区、W-7 防御、M2.5 W5/W6），用真实进程菜单门禁回归，产出一份用户手动验收清单；**不默认开启**、不对外称“可选显存优化”、不 push。

**Architecture:** 不新增 transformer、不改默认值。`LazyTextures` 维护 `STARTUP_BYTES`/`FOREIGN_BYTES`，预算只比较可淘汰字节；`evictOne` 去掉 `force` 并在 `synchronized(e)` 内二次校验（W-5）；二次物化失败的代理复位到共享占位而不是绑定 id 0（W-10）；DDS 每条回退分支带原因计数；DDS commit/handler/path-cache 用 `synchronized(loader)` 做 FR 漂移防御（W-7）。发行脚本强制重建 agent jar、校验新鲜度/内容/zip 不含宿主路径；A/B 工具缺日志/超时 fail-closed，并支持 counterbalance。实机只跑菜单锚点；战斗/读档/分辨率/长会话仍是用户门禁。

**Tech Stack:** Java 17（major 61）、ASM 9.1、Python 3.14 stdlib（`python -I`）、pytest 9、JUnit 5、`tools/smoke_run.py`、`tools/m26_ab.py`、Git Bash。

**Spec:** `docs/m26-results.md` §7.5/§7.7/§7.10–§7.15、`.superpowers/sdd/2026-11-01-m26-dds-lru/final-review.md` §1.2/§3（W-2…W-10、M2.5 W5/W6）、`技术笔记-纹理按需加载.md` §5.7/§6.1/§7、REQ-R1-10、INV-08/10。

---

## Global Constraints

- **默认 off 不变**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`；本里程碑不开默认、不改 `hypernova.json`、不改 `enabled_mods.json`。
- **线程红线**：淘汰/GL 删除/占位复位只在 `runtimeMain`；loading/worker 路径直接返回。`drainPendingDeletes` 也只在主线程。
- **owned-only 不变**：`selectVictims`/`evictOne` 只处理 `owned=true`；引擎真实对象 `owned=false` 永不被删。
- **无新 transformer/无新依赖**；agent 不 import 游戏/FR 类（反射）。
- **测试**：每个 Task TDD；纯函数覆盖预算分类、TOCTOU 门、停车决策、DDS 原因计数、release 检查、A/B fail-closed。
- **真实门禁**：budget=1/grace=0 smoke 必须 `evictPasses>=1`；selftest 必须 `1/1/1`；A/B gates 全 true；0 texture errors。
- **不改 M2.6 已闭合 gates**：generation/I2/I3/m4/DDS/preview/占位/id 卫生不变。
- **不 push**：用户未给 push 授权；所有 commit 留在本地，收尾时把 push/merge 选项呈给用户。
- **Escape hatch**：若实现与计划不符按实际修正并报告；**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**

## Review Focus

1. **预算口径**：startup 与 engine-owned（foreign）字节不得让 `liveBytes>budget` 永远可达却无可淘汰项；rematerialize/refresh 不得把同一批字节重复计入 startup/foreign。
2. **TOCTOU**：`evictOne` 在 `synchronized(e)` 内重新检查 `ready/glId/owned/startup/basic`；selftest 不再用 `force` 绕过，pick 之后变成 startup 的纹理必须存活。
3. **失败物化**：二次失败后代理指向合法占位 id，不再 `glBindTexture(target, 0)`；占位缺失时 fail-open，不把 lazy 整体禁用。
4. **DDS 盲区**：`ddsFallback` 的每一次递增都有原因；各原因之和等于总数；`ddsDimMismatch` 语义不变。
5. **发行门禁**：zip 不含 `lazy-skip-v2.txt`（宿主绝对路径）；打包的 agent jar 与当次构建逐 entry 一致；agent jar 不旧于源码。
6. **工具 fail-closed**：缺 `starsector.log`、`TimeoutExpired`、`--no-dds` 不再空过；counterbalance 只改顺序，不改 n。
7. **实机回归**：budget=1 仍能自动 pass、selftest 1/1/1、A/B 0 错误；首 pass 耗时/pass 空转可观测。
8. **默认值**：全仓库无默认开启改动；文档不写战斗/长会话收益。

---

## Pre-flight（controller）

- **Mode:** `pipeline`（Tasks 1–3 同文件 `LazyTextures.java`，必须顺序；Task 4–6 也走同一线性流水）。
- **BASE:** `26e1ca1`（M2.6 收口，origin/main）。
- **Workspace:** `.superpowers/sdd/2026-11-02-m27-default-on-readiness/`。
- **用户授权:** “开始M2.7，干吧”；用户预计睡眠 ≥6 h。SDD 计划审查由 controller 自行完成；**不默认开启、不 push**。
- **Rulings:**
  - **R-M27-1**：`LIVE_BYTES` 仍是总报告口径；预算只比较 `evictable = live - startup - foreign`。startup 与 engine-owned 都不可淘汰，必须同时排除。
  - **R-M27-2**：refcount/REQ-R1-10 的“仍被引用则拒绝并记录”无全局注册表，本轮不实现；owned-only + 失败停车 + 文档化为最低正确性门。
  - **R-M27-3**：W-2（GL context 重建占位）与 W-3（第三方 id 缓存）不在本轮代码修复；留给用户分辨率/战斗验收与文档。
  - **R-M27-4**：发行包保留 Base manifest/skip + `README-install.txt`；目标机须跑 `install_manifest.py`，generation/尺寸不符走 fail-open。
  - **R-M27-5**：战斗/读档/分辨率/手动目检、A→B 长会话净 VRAM、>200 ms 卡顿仍为 user gates；本轮只交付清单与自动化菜单证据。
- **写者表 / 接口:**

| 文件 | 任务 | 说明 |
|---|---|---|
| `src/agent/java/hypernova/agent/textures/LazyTextures.java` | 1, 2, 3 | 预算分类、evictOne/停车、DDS 原因计数、W-7 锁 |
| `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java` | 1, 2, 3 | 预算/TOCTOU/停车/原因计数测试 |
| `tests/agent/java/hypernova/agent/textures/LazyRefreshTest.java` | 1 | refreshReady → foreign 字节迁移 |
| `tools/release_check.py`（新） | 4 | zip/agent 检查纯函数 + CLI |
| `tools/java/build-mod.sh` | 4 | 强制 build-agent、新鲜度、README、release_check |
| `tools/java/README-install.txt`（新） | 4 | 发行安装说明（W5） |
| `tests/tools/test_release_check.py`（新） | 4 | 纯函数测试 |
| `tools/m26_ab.py` | 5 | 缺日志/超时 fail-closed、`--no-dds`、counterbalance、per-run 路径 |
| `tests/tools/test_m26_ab.py` | 5 | 工具测试 |
| `docs/m27-results.md` / `docs/m27-manual-acceptance.md`（新） | 6 | 结果 + 用户清单 |
| `docs/m26-results.md`、`技术笔记-纹理按需加载.md`、`大饼-DDS按需物化与LRU.md` | 6 | gates 状态回写 |

---

## Task 1: 预算口径（startup/foreign 排除）+ pass 观测

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyRefreshTest.java`

**Interfaces:**
- Consumes: 现有 `LIVE_BYTES`/`noteMaterialized`/`refreshReady`/`evictPass`/`shouldArmOnBudget`/`nextDueAfterPass`。
- Produces:
  - `LazyTextures.evictableBytes(long live, long startup, long foreign)` → `long`
  - `LazyTextures.ByteClass`（`EVICTABLE`/`STARTUP`/`FOREIGN`）、`LazyTextures.byteClass(boolean startup, boolean owned)`
  - `LazyTextures.noteMaterialized(ProxyEntry e, long bytes, boolean onMain)`（package-private 测试缝）
  - `liveBytesForTest()`/`startupBytesForTest()`/`foreignBytesForTest()`/`evictableBytesForTest()`
  - summary 新键：`startupBytes`/`foreignBytes`/`evictableBytes`/`emptyEvictPasses`/`evictPassMsTotal`/`evictPassMsMax`

**Constraints:** 不改默认值；不改 `selectVictims` 的 startup/basic/owned 过滤；`LIVE_BYTES` 仍是总口径。

---

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java` 追加：

```java
    @Test
    void evictableBytesExcludeStartupAndForeign() {
        assertEquals(50, LazyTextures.evictableBytes(150, 100, 0));
        assertEquals(20, LazyTextures.evictableBytes(150, 100, 30));
        assertEquals(0, LazyTextures.evictableBytes(100, 80, 40));
    }

    @Test
    void byteClassTruthTable() {
        assertEquals(LazyTextures.ByteClass.STARTUP,
                LazyTextures.byteClass(true, true));
        assertEquals(LazyTextures.ByteClass.STARTUP,
                LazyTextures.byteClass(true, false));
        assertEquals(LazyTextures.ByteClass.FOREIGN,
                LazyTextures.byteClass(false, false));
        assertEquals(LazyTextures.ByteClass.EVICTABLE,
                LazyTextures.byteClass(false, true));
    }

    @Test
    void noteMaterializedClassifiesBytes() {
        LazyTextures.resetGateStateForTest();
        LazyTextures.ProxyEntry startup = new LazyTextures.ProxyEntry(
                "startup", "TEXTURE", 10, 10, new Object());
        LazyTextures.noteMaterialized(startup, 100, false);
        assertTrue(startup.startup);
        LazyTextures.ProxyEntry foreign = new LazyTextures.ProxyEntry(
                "foreign", "TEXTURE", 10, 10, new Object());
        foreign.owned = false;
        LazyTextures.noteMaterialized(foreign, 30, true);
        LazyTextures.ProxyEntry mine = new LazyTextures.ProxyEntry(
                "mine", "TEXTURE", 10, 10, new Object());
        mine.owned = true;
        LazyTextures.noteMaterialized(mine, 20, true);
        assertEquals(150, LazyTextures.liveBytesForTest());
        assertEquals(100, LazyTextures.startupBytesForTest());
        assertEquals(30, LazyTextures.foreignBytesForTest());
        assertEquals(20, LazyTextures.evictableBytesForTest());
        LazyTextures.resetGateStateForTest();
    }
```

`tests/agent/java/hypernova/agent/textures/LazyRefreshTest.java` 追加（放在 `dimensionMismatchIsRejectedNotCopied` 之后）：

```java
    @Test
    void refreshMovesOwnedBytesToForeign() throws Exception {
        LazyTextures.resetGateStateForTest();
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);
        e.owned = true;
        LazyTextures.noteMaterialized(e, 40, true);
        assertEquals(40, LazyTextures.evictableBytesForTest());

        assertTrue(LazyTextures.refreshReady(shape, e, real(77).raw(), "register"));

        assertEquals(40, LazyTextures.liveBytesForTest());
        assertEquals(40, LazyTextures.foreignBytesForTest());
        assertEquals(0, LazyTextures.evictableBytesForTest());
        LazyTextures.resetGateStateForTest();
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`
Expected: 编译失败（`evictableBytes`/`ByteClass`/`noteMaterialized(…,boolean)`/`*BytesForTest` 不存在）。

- [ ] **Step 3: 实现预算分类与观测**

3a. Fields（放在 M2.6 eviction 状态块内，`LIVE_BYTES` 之后）：

```java
    private static final AtomicLong STARTUP_BYTES = new AtomicLong();
    private static final AtomicLong FOREIGN_BYTES = new AtomicLong();
    private static final AtomicLong EVICT_PASS_EMPTY = new AtomicLong();
    private static final AtomicLong EVICT_PASS_NANOS_TOTAL = new AtomicLong();
    private static final AtomicLong EVICT_PASS_NANOS_MAX = new AtomicLong();
```

3b. `resetGateStateForTest` 追加：

```java
        STARTUP_BYTES.set(0);
        FOREIGN_BYTES.set(0);
        EVICT_PASS_EMPTY.set(0);
        EVICT_PASS_NANOS_TOTAL.set(0);
        EVICT_PASS_NANOS_MAX.set(0);
```

3c. 在 `budgetBytes()` 前加纯函数与分类：

```java
    enum ByteClass { EVICTABLE, STARTUP, FOREIGN }

    static ByteClass byteClass(boolean startup, boolean owned) {
        if (startup) return ByteClass.STARTUP;
        return owned ? ByteClass.EVICTABLE : ByteClass.FOREIGN;
    }

    static long evictableBytes(long live, long startup, long foreign) {
        return Math.max(0L, live - startup - foreign);
    }

    private static long evictableBytes() {
        return evictableBytes(LIVE_BYTES.get(), STARTUP_BYTES.get(), FOREIGN_BYTES.get());
    }
```

3d. 替换 `noteMaterialized`：

```java
    private static void noteMaterialized(ProxyEntry e, long bytes) {
        noteMaterialized(e, bytes, Thread.currentThread() == runtimeMain);
    }

    static void noteMaterialized(ProxyEntry e, long bytes, boolean onMain) {
        markStartup(e, onMain);
        if (e.bytes == 0 && bytes > 0) {
            e.bytes = bytes;
            LIVE_BYTES.addAndGet(bytes);
            switch (byteClass(e.startup, e.owned)) {
                case STARTUP -> STARTUP_BYTES.addAndGet(bytes);
                case FOREIGN -> FOREIGN_BYTES.addAndGet(bytes);
                case EVICTABLE -> { }
            }
        }
        if (e.evicted > 0) {
            e.rematerialized++;
            REMATERIALIZED.incrementAndGet();
        }
        if (eviction && budgetBytes() != Long.MAX_VALUE
                && shouldArmOnBudget(evictDueNanos, evictableBytes(), budgetBytes())) {
            evictDueNanos = System.nanoTime() + evictionSceneDelayNanos;
        }
    }
```

3e. `refreshReady` 在 `e.owned = false;` 之后追加：

```java
        if (oldOwned && !e.startup && e.bytes > 0) {
            FOREIGN_BYTES.addAndGet(e.bytes);
        }
```

3f. 替换 `evictPass` 的预算与观测（保留 victim 循环）：

```java
    private static void evictPass(long now) {
        if (!eviction || disabled || Thread.currentThread() != runtimeMain) return;
        long t0 = System.nanoTime();
        long live = evictableBytes();
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
        long elapsed = System.nanoTime() - t0;
        EVICT_PASS_NANOS_TOTAL.addAndGet(elapsed);
        EVICT_PASS_NANOS_MAX.accumulateAndGet(elapsed, (a, b) -> Math.max(a, b));
        if (n == 0) EVICT_PASS_EMPTY.incrementAndGet();
        if (n > 0) {
            AgentLog.info("lazy: eviction pass evicted=" + n + " bytes=" + bytes
                    + " live=" + evictableBytes() + " budget=" + budget);
        }
        if (elapsed >= 50_000_000L) {
            AgentLog.info("lazy: eviction pass slow " + (elapsed / 1_000_000L)
                    + " ms evicted=" + n + " live=" + evictableBytes()
                    + " budget=" + budget);
        }
        evictDueNanos = nextDueAfterPass(now, evictionSceneDelayNanos,
                evictableBytes(), budget, n);
    }
```

> Task 1 保留现有 `evictOne(e, false)` 两参调用；Task 2 把 `evictOne` 改成单参后再同步改为 `evictOne(e)`。

3g. 测试缝（放在 `evictOneForTest` 附近）：

```java
    static long liveBytesForTest() { return LIVE_BYTES.get(); }
    static long startupBytesForTest() { return STARTUP_BYTES.get(); }
    static long foreignBytesForTest() { return FOREIGN_BYTES.get(); }
    static long evictableBytesForTest() { return evictableBytes(); }
```

3h. `summary()` 在 `liveBytes` 后追加：

```java
                    + " startupBytes=" + STARTUP_BYTES.get()
                    + " foreignBytes=" + FOREIGN_BYTES.get()
                    + " evictableBytes=" + evictableBytes()
                    + " emptyEvictPasses=" + EVICT_PASS_EMPTY.get()
                    + " evictPassMsTotal=" + (EVICT_PASS_NANOS_TOTAL.get() / 1_000_000L)
                    + " evictPassMsMax=" + (EVICT_PASS_NANOS_MAX.get() / 1_000_000L)
```

- [ ] **Step 4: 跑测试通过**

Run:
```bash
bash tools/java/run-agent-tests.sh LazyEviction
bash tools/java/run-agent-tests.sh LazyRefresh
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
```
Expected: `LazyEviction` 17/17（14 旧 + 3 新）；`LazyRefresh` 6/6；full agent 176 found / 175 pass / 1 known symlink abort / 0 fail；pytest 287 passed。实际计数以报告为准。

- [ ] **Step 5: 提交**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java \
        tests/agent/java/hypernova/agent/textures/LazyRefreshTest.java
git commit -m "fix(m27): exclude non-evictable bytes from the LRU budget"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Task 2: 淘汰安全（W-5 TOCTOU / W-10 停车 / oldId 计数 / W-7）

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

**Interfaces:**
- Consumes: Task 1 的 `evictPass`/`noteMaterialized`；现有 `everyEntry`/`materialize`/`ensurePlaceholder`/`GlBridge`。
- Produces:
  - `LazyTextures.evictOne(ProxyEntry e)`（无 `force`）；`evictOneForTest(ProxyEntry e)`
  - `LazyTextures.ProxyReset` 函数接口 + `parkFailedProxy(ProxyEntry, boolean placeholderReady, int pid, ProxyReset)`（package-private 测试缝）
  - summary 新键：`failedParked`
  - `putPathCache`/`materializeDds` 在 `synchronized(loader)` 内提交/写缓存

**Constraints:** 不改 `selectVictims`；`parkFailed` 只在二次失败时调用；占位缺失时只记录一次，不置 `disabled`。

---

- [ ] **Step 1: 写失败测试**

`LazyEvictionTest.java` 追加/修改：

```java
    @Test
    void evictOneRefusesStartupAndBasicEvenWhenReady() {
        LazyTextures.ProxyEntry startup = readyWithObj("startup", true);
        startup.startup = true;
        assertFalse(LazyTextures.evictOneForTest(startup));

        LazyTextures.ProxyEntry ui = readyWithObj("graphics/ui/x.png", true);
        assertFalse(LazyTextures.evictOneForTest(ui));
    }

    @Test
    void parkFailedProxyResetsOnlyUnreadyEntries() {
        List<Integer> ids = new java.util.ArrayList<>();
        LazyTextures.ProxyEntry failed = new LazyTextures.ProxyEntry(
                "failed", "TEXTURE", 10, 10, new Object());
        assertTrue(LazyTextures.parkFailedProxy(failed, true, 77, (entry, pid) -> {
            ids.add(pid);
            entry.glId = pid;
        }));
        assertEquals(List.of(77), ids);
        assertEquals(0, failed.glId);
        assertTrue(failed.failed);
        assertEquals(1, LazyTextures.failedParkedForTest());

        LazyTextures.ProxyEntry ready = readyWithObj("ready", true);
        assertFalse(LazyTextures.parkFailedProxy(ready, true, 77, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(failed, false, 77, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(failed, true, 0, (e, pid) -> { }));
        assertFalse(LazyTextures.parkFailedProxy(
                failed, true, 77, (e, pid) -> { throw new IllegalStateException("boom"); }));
    }
```

把已有的 `assertFalse(LazyTextures.evictOneForTest(engine, true));` 改为：

```java
        assertFalse(LazyTextures.evictOneForTest(engine));
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`
Expected: 编译失败（`evictOneForTest(ProxyEntry)`/`parkFailedProxy`/`failedParkedForTest` 不存在）。

- [ ] **Step 3: 实现 W-5/W-10/oldId/W-7**

3a. `evictOne` 改为单参数，并在 `synchronized(e)` 内二次校验：

```java
    private static boolean evictOne(ProxyEntry e) {
        if (e == null || !e.ready || e.glId <= 0 || e.obj == null) return false;
        if (!e.owned) return false;
        if (e.startup || isBasicPath(e.path)) return false;
        if (Thread.currentThread() != runtimeMain) return false;
        if (!ensurePlaceholder()) return false;
        int id;
        synchronized (e) {
            // W-5: materialize()/refreshReady() hold this same monitor. Re-check
            // under it so a texture that became startup/engine-owned between
            // pick and evict is never deleted.
            if (!e.ready || e.glId <= 0 || !e.owned
                    || e.startup || isBasicPath(e.path)) {
                return false;
            }
            ProxyShape shape = proxyShape;
            if (shape == null) return false;
            id = e.glId;
            try {
                shape.reset(e.obj, 3553, placeholderId, 1, 1, 1.0f, 1.0f, e.w, e.h);
            } catch (Throwable t) {
                AgentLog.fail("lazy: eviction reset failed for " + e.path, t);
                return false;
            }
            long bytes = e.bytes;
            e.ready = false;
            e.failed = false;
            e.dds = false;
            e.owned = false;
            e.glId = 0;
            e.bytes = 0;
            e.lastSource = null;
            e.attempts.set(0);
            e.evicted++;
            LIVE_BYTES.addAndGet(-bytes);
            EVICTED.incrementAndGet();
            EVICTED_BYTES.addAndGet(bytes);
            touch(e);
        }
        // The proxy already points at the valid placeholder; a failed delete is
        // a VRAM leak, not a dangling id. Count it and let re-materialize fix it.
        if (!GlBridge.deleteTexture(id)) {
            OLD_ID_SKIPPED.incrementAndGet();
            return false;
        }
        OLD_ID_DELETED.incrementAndGet();
        return true;
    }

    static boolean evictOneForTest(ProxyEntry e) {
        return evictOne(e);
    }
```

3b. 所有调用点改成单参：`runSelfTest` 的 `evictOne(pick, true)` 改为 `evictOne(pick)`；Task 1 的 `evictPass` 里 `evictOne(e, false)` 改为 `evictOne(e)`。

3c. 停车（放在 `evictOneForTest` 后）：

```java
    @FunctionalInterface
    interface ProxyReset {
        void reset(ProxyEntry e, int placeholderId) throws Exception;
    }

    static boolean parkFailedProxy(ProxyEntry e, boolean placeholderReady, int pid,
                                   ProxyReset reset) {
        if (e == null || e.ready || !placeholderReady || pid <= 0 || reset == null) return false;
        synchronized (e) {
            if (e.ready) return false;
            try {
                reset.reset(e, pid);
            } catch (Throwable t) {
                AgentLog.fail("lazy: failed-proxy parking failed for " + e.path, t);
                return false;
            }
            e.glId = 0;
            e.owned = false;
            e.dds = false;
            e.failed = true;
            FAILED_PARKED.incrementAndGet();
            return true;
        }
    }

    private static void parkFailed(ProxyEntry e) {
        if (!ensurePlaceholder()) return;
        ProxyShape shape = proxyShape;
        if (shape == null) return;
        parkFailedProxy(e, true, placeholderId, (entry, pid) ->
                shape.reset(entry.obj, 3553, pid, 1, 1, 1.0f, 1.0f, entry.w, entry.h));
    }
```

3d. `materialize` 的 catch 改为：

```java
            } catch (Throwable t) {
                long attempts = e.attempts.incrementAndGet();
                if (attempts >= 2) {
                    e.failed = true;
                    parkFailed(e);
                }
                LAZY_FAILED.incrementAndGet();
                AgentLog.fail("lazy: materialize failed for " + e.path
                        + " (attempt " + attempts + ")", t);
            }
```

3e. Fields / reset / summary：

```java
    private static final AtomicLong FAILED_PARKED = new AtomicLong();
```
`resetGateStateForTest` 追加 `FAILED_PARKED.set(0);`；`summary()` 追加 `+ " failedParked=" + FAILED_PARKED.get()`；测试缝：

```java
    static long failedParkedForTest() { return FAILED_PARKED.get(); }
```

3f. W-7：`materializeDds` 的 commit/handler 改为同一 loader 监视器（局部变量）：

```java
        Object loader = loaderSingleton;
        if (loader == null) {
            DDS_FALLBACK.incrementAndGet();
            return false;
        }
        int id;
        Object real;
        synchronized (loader) {
            id = DdsBridge.commit(data.texData());
            if (id <= 0) {
                DDS_FALLBACK.incrementAndGet();
                return false;
            }
            try {
                real = DdsBridge.newHandler(loader, e.path, data.texData(), id);
            } catch (Throwable t) {
                deleteTextureSafe(id);
                long n = DDS_FALLBACK.incrementAndGet();
                if (n <= 20) AgentLog.fail("lazy: dds handler failed for " + e.path, t);
                return false;
            }
        }
```

3g. `putPathCache` 用同一监视器：

```java
    @SuppressWarnings("unchecked")
    private static void putPathCache(String path, Object obj) {
        Field field = pathCacheField;
        Object loader = loaderSingleton;
        if (field == null || loader == null) return;
        synchronized (loader) {
            try {
                Object value = field.get(loader);
                if (value instanceof Map<?, ?>) {
                    ((Map<Object, Object>) value).put(path, obj);
                }
            } catch (Throwable t) {
                AgentLog.fail("lazy: path cache put failed for " + path, t);
            }
        }
    }
```

- [ ] **Step 4: 跑测试通过**

Run:
```bash
bash tools/java/run-agent-tests.sh LazyEviction
bash tools/java/run-agent-tests.sh LazyRefresh
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
```
Expected: `LazyEviction` 20/20（17 + 2 新 + R-M27-6 mutation-test addendum）；`LazyRefresh` 6/6；full agent 179 found / 178 pass / 1 known symlink abort / 0 fail；pytest 287 passed。实际计数以报告为准。

- [ ] **Step 5: 提交**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java
git commit -m "fix(m27): harden eviction against TOCTOU and failed materialization"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Task 3: DDS fallback 原因计数（W-4 / §7.12 盲区）

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

**Interfaces:**
- Consumes: 现有 `DDS_FALLBACK`/`materializeDds`/`DdsCheck.Result.reason()`。
- Produces:
  - `LazyTextures.DdsFallbackReason`（`META`/`BRIDGE`/`PATH`/`GET`/`CHECK`/`COMMIT`/`HANDLER`/`NULL`/`SHAPE`/`COPY`）
  - `noteDdsFallback(DdsFallbackReason, String path, String detail)`（package-private）
  - `ddsFallbackCount(DdsFallbackReason)`（package-private）
  - summary 新键：`ddsFbMeta`/`ddsFbBridge`/`ddsFbPath`/`ddsFbGet`/`ddsFbCheck`/`ddsFbCommit`/`ddsFbHandler`/`ddsFbNull`/`ddsFbShape`/`ddsFbCopy`

**Constraints:** `DDS_FALLBACK` 总数语义不变；`ddsDimMismatch` 不计入 fallback（与 M2.6 一致）；每个原因只打第一条 INFO。

---

- [ ] **Step 1: 写失败测试**

`LazyEvictionTest.java` 追加：

```java
    @Test
    void ddsFallbackReasonsCountAndReset() {
        LazyTextures.resetGateStateForTest();
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.META, "graphics/a.png", "no metadata");
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.META, "graphics/b.png", null);
        LazyTextures.noteDdsFallback(
                LazyTextures.DdsFallbackReason.CHECK, "graphics/c.png", "dxgi 1");
        assertEquals(2, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.META));
        assertEquals(1, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.CHECK));
        assertEquals(0, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.COPY));
        LazyTextures.resetGateStateForTest();
        assertEquals(0, LazyTextures.ddsFallbackCount(
                LazyTextures.DdsFallbackReason.META));
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`
Expected: 编译失败（`DdsFallbackReason`/`noteDdsFallback`/`ddsFallbackCount` 不存在）。

- [ ] **Step 3: 实现原因计数**

3a. Fields（放在 DDS 计数器附近）：

```java
    enum DdsFallbackReason {
        META, BRIDGE, PATH, GET, CHECK, COMMIT, HANDLER, NULL, SHAPE, COPY
    }
    private static final Map<DdsFallbackReason, AtomicLong> DDS_FB =
            new ConcurrentHashMap<>();
    private static final Map<DdsFallbackReason, AtomicBoolean> DDS_FB_LOGGED =
            new ConcurrentHashMap<>();
```

3b. 方法（放在 `ddsBytes` 后）：

```java
    static void noteDdsFallback(DdsFallbackReason reason, String path, String detail) {
        if (reason == null) return;
        DDS_FALLBACK.incrementAndGet();
        DDS_FB.computeIfAbsent(reason, r -> new AtomicLong()).incrementAndGet();
        if (DDS_FB_LOGGED.computeIfAbsent(reason, r -> new AtomicBoolean())
                .compareAndSet(false, true)) {
            AgentLog.info("lazy: dds fallback " + reason + " path=" + path
                    + (detail == null || detail.isBlank() ? "" : " detail=" + detail));
        }
    }

    static long ddsFallbackCount(DdsFallbackReason reason) {
        AtomicLong n = DDS_FB.get(reason);
        return n == null ? 0 : n.get();
    }
```

3c. `resetGateStateForTest` 追加：

```java
        DDS_FB.clear();
        DDS_FB_LOGGED.clear();
```

3d. 用下面的完整方法替换 `materializeDds`（含 Task 2 的 W-7 锁与全部原因计数）：

```java
    private static boolean materializeDds(ProxyEntry e) {
        LazySkipIndex.Entry meta = index == null ? null : index.get(e.path);
        if (meta == null || meta.absPath() == null || meta.ddsPath() == null) {
            noteDdsFallback(DdsFallbackReason.META, e.path, "no metadata");
            return false;
        }
        if (!DdsBridge.available()) {
            DDS_DISABLED.incrementAndGet();
            noteDdsFallback(DdsFallbackReason.BRIDGE, e.path, "bridge unavailable");
            return false;
        }
        Path absPath;
        try {
            absPath = Path.of(meta.absPath());
        } catch (Throwable t) {
            noteDdsFallback(DdsFallbackReason.PATH, e.path, String.valueOf(t));
            return false;
        }
        DdsBridge.Data data = DdsBridge.get(absPath);
        if (data == null) {
            noteDdsFallback(DdsFallbackReason.GET, e.path, "getTexture null");
            return false;
        }
        if (!dimensionsMatch(data.imageWidth(), data.imageHeight(), e.w, e.h)) {
            DDS_DIM_MISMATCH.incrementAndGet();
            onDimMismatch(e, data.imageWidth(), data.imageHeight(), "dds metadata");
            return false;
        }
        DdsCheck.Result check = DdsCheck.check(data.ddsPath(), e.w, e.h);
        if (!check.ok()) {
            noteDdsFallback(DdsFallbackReason.CHECK, e.path, check.reason());
            return false;
        }
        Object loader = loaderSingleton;
        if (loader == null) {
            noteDdsFallback(DdsFallbackReason.HANDLER, e.path, "loader null");
            return false;
        }
        int id;
        Object real;
        synchronized (loader) {
            id = DdsBridge.commit(data.texData());
            if (id <= 0) {
                noteDdsFallback(DdsFallbackReason.COMMIT, e.path, "id=" + id);
                return false;
            }
            try {
                real = DdsBridge.newHandler(loader, e.path, data.texData(), id);
            } catch (Throwable t) {
                deleteTextureSafe(id);
                noteDdsFallback(DdsFallbackReason.HANDLER, e.path, "handler failed");
                AgentLog.fail("lazy: dds handler failed for " + e.path, t);
                return false;
            }
        }
        if (real == null) {
            deleteTextureSafe(id);
            noteDdsFallback(DdsFallbackReason.NULL, e.path, "handler null");
            return false;
        }
        ProxyShape shape = proxyShape;
        if (shape == null) {
            deleteTextureSafe(id);
            noteDdsFallback(DdsFallbackReason.SHAPE, e.path, "shape unavailable");
            return false;
        }
        int realW;
        int realH;
        try {
            realW = shape.imageWidth(real);
            realH = shape.imageHeight(real);
        } catch (Throwable t) {
            deleteTextureSafe(id);
            noteDdsFallback(DdsFallbackReason.SHAPE, e.path, "shape read failed");
            AgentLog.fail("lazy: dds handler shape failed for " + e.path, t);
            return false;
        }
        if (!dimensionsMatch(realW, realH, e.w, e.h)) {
            DDS_DIM_MISMATCH.incrementAndGet();
            onDimMismatch(e, realW, realH, "dds handler");
        }
        try {
            shape.copy(real, e.obj);
        } catch (Throwable t) {
            deleteTextureSafe(id);
            noteDdsFallback(DdsFallbackReason.COPY, e.path, "copy failed");
            AgentLog.fail("lazy: dds handler copy failed for " + e.path, t);
            return false;
        }
        e.ready = true;
        e.dds = true;
        e.glId = id;
        e.owned = true;
        noteMaterialized(e, ddsBytes(data.width(), data.height()));
        touch(e);
        putPathCache(e.path, e.obj);
        long n = DDS_HIT.incrementAndGet();
        LAZY_MATERIALIZED.incrementAndGet();
        if (n <= 20) {
            AgentLog.info("lazy: dds materialized " + e.path + " " + e.w + "x" + e.h
                    + " id=" + id + " bytes=" + e.bytes);
        }
        return true;
    }
```

> 该完整方法同时替代 Task 2 Step 3f 的局部替换；`CHECK` 分支不再单独递增 `DDS_FALLBACK`（避免与 `noteDdsFallback` 双计），每路径前 20 条日志由 `noteDdsFallback` 的“每原因第一条”取代。

3e. Summary helper：

```java
    private static String ddsFallbackSummary() {
        StringBuilder sb = new StringBuilder();
        for (DdsFallbackReason r : DdsFallbackReason.values()) {
            sb.append(" ddsFb").append(reasonKey(r)).append('=')
              .append(ddsFallbackCount(r));
        }
        return sb.toString();
    }

    private static String reasonKey(DdsFallbackReason r) {
        return switch (r) {
            case META -> "Meta";
            case BRIDGE -> "Bridge";
            case PATH -> "Path";
            case GET -> "Get";
            case CHECK -> "Check";
            case COMMIT -> "Commit";
            case HANDLER -> "Handler";
            case NULL -> "Null";
            case SHAPE -> "Shape";
            case COPY -> "Copy";
        };
    }
```

`summary()` 在 `ddsFallback=` 后追加 `+ ddsFallbackSummary()`。

- [ ] **Step 4: 跑测试通过**

Run:
```bash
bash tools/java/run-agent-tests.sh LazyEviction
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
```
Expected: `LazyEviction` 21/21（20 + 1 新）；full agent 180 found / 179 pass / 1 known symlink abort / 0 fail；pytest 287 passed。

- [ ] **Step 5: 提交**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java
git commit -m "fix(m27): count DDS fallback reasons"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Task 4: 发行包 / agent jar 门禁（M2.5 W5/W6）

**Files:**
- Create: `tools/release_check.py`
- Create: `tools/java/README-install.txt`
- Modify: `tools/java/build-mod.sh`
- Create: `tests/tools/test_release_check.py`

**Interfaces:**
- Consumes: `build-mod.sh` 的 `$OUT/hypernova-0.1.0.zip`、`$AGENT_JAR`、`src/agent/java`。
- Produces:
  - `release_check.check_zip(Path, Path | None) -> list[str]`
  - `release_check.check_agent_fresh(Path, Path) -> list[str]`
  - `release_check.generation_header(bytes) -> str | None`
  - `release_check.jar_entries(bytes) -> dict[str, tuple[int, int]]`

**Constraints:** zip 不含 `lazy-skip-v2.txt`；README 说明目标机必须跑 `install_manifest.py`；不 push。

---

- [ ] **Step 1: 写失败测试**

`tests/tools/test_release_check.py`：

```python
import hashlib
import importlib.util
import os
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
_spec = importlib.util.spec_from_file_location("release_check", TOOLS / "release_check.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

MANIFEST = b'{"schema":"hypernova-runtime-1","layers":[]}'
GEN = hashlib.sha256(MANIFEST).hexdigest()
AGENT = ("hypernova/agent/HypernovaAgent.class",
         "hypernova/agent/textures/LazyTextures.class",
         "hypernova/agent/textures/LazyProxyObject.class")


def _agent_jar(path, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        for name in AGENT:
            zf.writestr(name, b"x")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def _release_zip(tmp_path, drop=(), overrides=None):
    jar = _agent_jar(tmp_path / "agent.jar")
    files = {
        "mod_info.json": b"{}",
        "README-install.txt": b"note",
        "data/config/hypernova/manifest-v1.json": MANIFEST,
        "data/config/hypernova/lazy-skip-v1.txt":
            b"# generation=" + GEN.encode() + b"\npath\t1\t1\n",
        "jars/hypernova.agent.jar": jar.read_bytes(),
        "graphics/hypernova/blank.png": b"png",
    }
    files.update(overrides or {})
    for name in drop:
        files.pop(name, None)
    zip_path = tmp_path / "mod.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return zip_path, jar


def test_valid_release_passes(tmp_path):
    zip_path, jar = _release_zip(tmp_path)
    assert rc.check_zip(zip_path, jar) == []


def test_missing_manifest_fails(tmp_path):
    zip_path, jar = _release_zip(
        tmp_path, drop=("data/config/hypernova/manifest-v1.json",))
    assert any("missing data/config/hypernova/manifest-v1.json" in f
               for f in rc.check_zip(zip_path, jar))


def test_host_skip_v2_is_forbidden(tmp_path):
    zip_path, jar = _release_zip(tmp_path, overrides={
        "data/config/hypernova/lazy-skip-v2.txt":
            b"# generation=" + GEN.encode()
            + b"\npath\t1\t1\tC:/x.png\tC:/x.dds\t1\n",
    })
    assert any("lazy-skip-v2" in f for f in rc.check_zip(zip_path, jar))


def test_generation_mismatch_fails(tmp_path):
    zip_path, jar = _release_zip(tmp_path, overrides={
        "data/config/hypernova/lazy-skip-v1.txt":
            b"# generation=deadbeef\npath\t1\t1\n",
    })
    assert any("generation" in f for f in rc.check_zip(zip_path, jar))


def test_agent_jar_markers_and_match(tmp_path):
    zip_path, jar = _release_zip(tmp_path)
    bad = _agent_jar(tmp_path / "bad.jar", extra={"extra/Thing.class": b"x"})
    assert any("agent jar entries differ" in f
               for f in rc.check_zip(zip_path, bad))
    incomplete = tmp_path / "incomplete.jar"
    with zipfile.ZipFile(incomplete, "w") as zf:
        zf.writestr("hypernova/agent/HypernovaAgent.class", b"x")
    assert any("missing hypernova/agent/textures/LazyTextures.class" in f
               for f in rc.check_zip(zip_path, incomplete))


def test_agent_freshness(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    source = src / "a" / "X.java"
    source.write_text("class X {}", encoding="utf-8")
    jar = _agent_jar(tmp_path / "agent.jar")
    now = time.time()
    os.utime(source, (now - 60, now - 60))
    os.utime(jar, (now, now))
    assert rc.check_agent_fresh(jar, src) == []
    os.utime(source, (now + 60, now + 60))
    assert any("agent sources newer than jar" in f
               for f in rc.check_agent_fresh(jar, src))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_release_check.py -q`
Expected: `ModuleNotFoundError`/文件不存在（`tools/release_check.py` 未创建）。

- [ ] **Step 3: 实现 `tools/release_check.py`**

```python
#!/usr/bin/env python3
"""Release zip checks for the Hypernova mod (M2.7 W5/W6 gates)."""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

REQUIRED = (
    "mod_info.json",
    "README-install.txt",
    "data/config/hypernova/manifest-v1.json",
    "data/config/hypernova/lazy-skip-v1.txt",
    "graphics/hypernova/blank.png",
)
FORBIDDEN = ("data/config/hypernova/lazy-skip-v2.txt",)
AGENT_MARKERS = (
    "hypernova/agent/HypernovaAgent.class",
    "hypernova/agent/textures/LazyTextures.class",
    "hypernova/agent/textures/LazyProxyObject.class",
)


def generation_header(data: bytes) -> str | None:
    for line in data.decode("utf-8", "replace").splitlines():
        if line.startswith("# generation="):
            return line[len("# generation="):].strip()
    return None


def jar_entries(data: bytes) -> dict[str, tuple[int, int]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {i.filename: (i.CRC, i.file_size) for i in zf.infolist()}
    except zipfile.BadZipFile:
        return {}


def check_zip(zip_path: Path, agent_jar: Path | None = None) -> list[str]:
    failures: list[str] = []
    if not zip_path.is_file():
        return [f"zip missing: {zip_path}"]
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        return [f"bad zip {zip_path}: {exc}"]
    with zf:
        names = set(zf.namelist())
        for req in REQUIRED:
            if req not in names:
                failures.append(f"missing {req}")
            elif zf.getinfo(req).file_size == 0:
                failures.append(f"empty {req}")
        for bad in FORBIDDEN:
            if bad in names:
                failures.append(f"forbidden host artifact: {bad}")
        manifest_name = "data/config/hypernova/manifest-v1.json"
        if manifest_name in names:
            manifest = zf.read(manifest_name)
            expected = hashlib.sha256(manifest).hexdigest()
            for skip in ("data/config/hypernova/lazy-skip-v1.txt",
                         "data/config/hypernova/lazy-skip-v2.txt"):
                if skip not in names:
                    continue
                got = generation_header(zf.read(skip))
                if got != expected:
                    failures.append(
                        f"{skip} generation {got or '<none>'} != manifest {expected}")
        if agent_jar is not None:
            if "jars/hypernova.agent.jar" not in names:
                failures.append("missing jars/hypernova.agent.jar")
            elif agent_jar.is_file():
                packaged = zf.read("jars/hypernova.agent.jar")
                entries = jar_entries(packaged)
                built = jar_entries(agent_jar.read_bytes())
                for marker in AGENT_MARKERS:
                    if marker not in entries:
                        failures.append(f"packaged agent jar missing {marker}")
                    if marker not in built:
                        failures.append(f"built agent jar missing {marker}")
                if entries and entries != built:
                    failures.append(
                        "packaged agent jar entries differ from "
                        f"{agent_jar}")
            else:
                failures.append(f"agent jar missing: {agent_jar}")
    return failures


def check_agent_fresh(agent_jar: Path, sources: Path) -> list[str]:
    if not agent_jar.is_file():
        return [f"agent jar missing: {agent_jar}"]
    if not sources.is_dir():
        return [f"agent sources missing: {sources}"]
    built = agent_jar.stat().st_mtime_ns
    stale = sorted(
        str(p.relative_to(sources))
        for p in sources.rglob("*.java")
        if "tools" not in p.relative_to(sources).parts
        and p.stat().st_mtime_ns > built
    )
    if not stale:
        return []
    shown = ", ".join(stale[:5])
    more = "" if len(stale) <= 5 else f" (+{len(stale) - 5} more)"
    return [f"agent sources newer than jar: {shown}{more}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", required=True, type=Path)
    ap.add_argument("--agent-jar", type=Path)
    ap.add_argument("--sources", type=Path)
    args = ap.parse_args(argv)
    failures = check_zip(args.zip, args.agent_jar)
    if args.agent_jar is not None and args.sources is not None:
        failures += check_agent_fresh(args.agent_jar, args.sources)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"OK: {args.zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 创建 `tools/java/README-install.txt`**

```text
Hypernova Infinite Engine — 纹理懒加载安装说明（M2.7）

1. 本包内的 data/config/hypernova/manifest-v1.json 与 lazy-skip-v1.txt 由
   Starsector-098-Base 的纹理集生成，只对 Base 安装准确。
2. 在 260mods 或任何其它 mod 集上使用前，必须在该游戏目录运行：
     python -I tools/install_manifest.py --game-root <游戏目录>
   然后重启游戏。skip/manifest 的 generation 不匹配时 lazy 会 fail-open
   （不跳过、不代理），不会崩溃；尺寸不一致时同样 fail-open。
3. 默认 textures.lazy.enabled=false、textures.lazy.eviction.enabled=false。
   开启方式见 data/config/hypernova/hypernova.json 或 -D 启动参数。
4. 回滚：把 textures.lazy.enabled 设为 false，或加
   -Dhypernova.textures.lazy=false，或删除启动文件中的 -javaagent 行。
```

- [ ] **Step 5: 修改 `tools/java/build-mod.sh`**

在 `ROOT_W=...` 后、编译 mod 前插入：

```bash
AGENT_JAR="$ROOT_W/build/agent/hypernova.agent.jar"
bash "$ROOT_W/tools/java/build-agent.sh" >/dev/null
if [ ! -s "$AGENT_JAR" ]; then
  echo "FATAL: agent jar missing after build-agent.sh" >&2
  exit 1
fi
if find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*' -newer "$AGENT_JAR" | grep -q .; then
  echo "FATAL: agent jar is older than agent sources (stale build)" >&2
  exit 1
fi
```

把 agent 复制块从条件改为无条件，并复制 README：

```bash
cp "$AGENT_JAR" "$MODDIR/jars/hypernova.agent.jar"
cp "$ROOT_W/tools/java/README-install.txt" "$MODDIR/README-install.txt"
```

在 zip 创建后追加：

```bash
python -I "$ROOT_W/tools/release_check.py" --zip "$OUT/hypernova-0.1.0.zip" \
  --agent-jar "$AGENT_JAR" --sources "$ROOT_W/src/agent/java"
```

- [ ] **Step 6: 跑测试 + 构建通过**

Run:
```bash
python -I -m pytest tests/tools/test_release_check.py -q
python -I -m pytest tests/tools -q
bash tools/java/build-mod.sh
```
Expected: 新测试全过；pytest 293 passed（287 + 6）；`build-mod.sh` 输出 `OK: .../hypernova-0.1.0.zip` + `OK:` release_check；zip 含 README、无 v2。

- [ ] **Step 7: 提交**

```bash
git add tools/release_check.py tools/java/README-install.txt tools/java/build-mod.sh \
        tests/tools/test_release_check.py
git commit -m "build(m27): gate release zips on manifest, agent freshness, and host paths"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Task 5: `m26_ab.py` fail-closed + counterbalance

**Files:**
- Modify: `tools/m26_ab.py`
- Modify: `tests/tools/test_m26_ab.py`

**Interfaces:**
- Consumes: 现有 `run_round`/`archive_round`/`stats_from_text`/`main`。
- Produces:
  - `run_round` 超时返回 `{"ok": False, "reason": "timeout"}`，不中止整轮
  - `archive_round` 增加 `log_present: bool`；缺日志**或缺 session anchor** 时 `no_texture_errors=false`
  - `main` 新增 `--counterbalance`
  - 每轮 JSON 写到 `--out` 同目录的 `<stem>-c{i}.json` / `<stem>-t{i}.json`

**Constraints:** 不改 smoke 协议；不改 `stats_from_text` 的统计口径；counterbalance 只改 C/T 顺序。

---

- [ ] **Step 1: 写失败测试**

`tests/tools/test_m26_ab.py` 追加/修改：

```python
import subprocess


def test_run_round_timeout_is_a_row(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="smoke", timeout=1)
    monkeypatch.setattr(ab.subprocess, "run", boom)
    row = ab.run_round("miko-lite", True, True, False, False,
                       tmp_path / "x.json", 1, 1)
    assert row["ok"] is False
    assert row["reason"] == "timeout"


def test_missing_anchor_fails_closed(tmp_path, monkeypatch):
    game = tmp_path / "game"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    (core / "starsector.log").write_bytes(b"no anchor here
")
    monkeypatch.setattr(ab, "ROOT", tmp_path)
    monkeypatch.setattr(ab, "PROFILES", {"fake": {"game": "game"}})
    row = ab.archive_round("fake", "c", 1, tmp_path / "out")
    assert row["log_present"] is False
    assert row["log"] is None


def test_missing_log_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(ab, "run_round", lambda *a, **k: _row(50.0))
    monkeypatch.setattr(ab, "archive_round", lambda *a, **k: {
        "log": None, "log_present": False, "failed": 0, "verify": 0,
        "class_errors": 0, "async_errors": 0, "corrupted": 0})
    monkeypatch.setattr(ab, "stats_from_text", lambda text: {
        "skipped": 1, "failed": 0, "disabled": 0, "dimMismatch": 0,
        "ddsDisabled": 0, "ddsHit": 1, "selftest": 0})
    monkeypatch.setattr(ab, "free_physical_mb", lambda: 20_000.0)
    agent = tmp_path / "agent.log"
    agent.write_text("premain\n", encoding="utf-8")
    out = tmp_path / "ab.json"
    assert ab.main(["--rounds", "1", "--agent-log", str(agent),
                    "--out", str(out)]) == 1
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["gates"]["logs_present"] is False
    assert result["gates"]["no_texture_errors"] is False


def test_no_dds_skips_hit_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(ab, "run_round", lambda *a, **k: _row(50.0))
    monkeypatch.setattr(ab, "archive_round", lambda *a, **k: {
        "log": None, "log_present": True, "failed": 0, "verify": 0,
        "class_errors": 0, "async_errors": 0, "corrupted": 0})
    monkeypatch.setattr(ab, "stats_from_text", lambda text: {
        "skipped": 1, "failed": 0, "disabled": 0, "dimMismatch": 0,
        "ddsDisabled": 0, "ddsHit": 0, "selftest": 0})
    monkeypatch.setattr(ab, "free_physical_mb", lambda: 20_000.0)
    agent = tmp_path / "agent.log"
    agent.write_text("premain\n", encoding="utf-8")
    out = tmp_path / "ab.json"
    assert ab.main(["--rounds", "1", "--no-dds", "--agent-log", str(agent),
                    "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["gates"]["treatment_dds_hit_positive"] is True


def test_counterbalance_reverses_even_rounds(tmp_path, monkeypatch):
    calls = []

    def fake_run(profile, lazy, dds, eviction, selftest, out, wait, linger):
        calls.append(lazy)
        return _row(50.0)

    monkeypatch.setattr(ab, "run_round", fake_run)
    monkeypatch.setattr(ab, "archive_round", lambda *a, **k: {
        "log": None, "log_present": True, "failed": 0, "verify": 0,
        "class_errors": 0, "async_errors": 0, "corrupted": 0})
    monkeypatch.setattr(ab, "stats_from_text", lambda text: {
        "skipped": 1, "failed": 0, "disabled": 0, "dimMismatch": 0,
        "ddsDisabled": 0, "ddsHit": 1, "selftest": 0})
    monkeypatch.setattr(ab, "free_physical_mb", lambda: 20_000.0)
    agent = tmp_path / "agent.log"
    agent.write_text("premain\n", encoding="utf-8")
    out = tmp_path / "ab.json"
    assert ab.main(["--rounds", "2", "--counterbalance", "--agent-log", str(agent),
                    "--out", str(out)]) == 0
    assert calls == [False, True, True, False]
```

同时把 `test_main_pairs_and_gates` 里的 `archive_round` 假值补上 `"log_present": True`（否则新 gate 会失败）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_m26_ab.py -q`
Expected: 新测试失败（`log_present`/`--counterbalance` 未实现；timeout 未捕获）。

- [ ] **Step 3: 实现工具改动**

3a. `run_round` 捕获超时：

```python
    try:
        proc = subprocess.run(cmd, check=False, cwd=str(ROOT), timeout=SMOKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "returncode": None}
```

3b. `archive_round` 增加 `log_present`：

```python
    result = {"log": None, "log_present": False, "failed": 0, "verify": 0,
              "class_errors": 0, "async_errors": 0, "corrupted": 0}
    game = ROOT / PROFILES[profile]["game"]
    log = game / "starsector-core" / "starsector.log"
    if not log.is_file():
        return result
    data = log.read_bytes()
    idx = data.rfind(SESSION_ANCHOR)
    if idx < 0:
        return result
    session = data[idx:]
    result["log_present"] = True
```

3c. `main` 增加参数：

```python
    ap.add_argument("--counterbalance", action="store_true")
```

3d. 替换 round 循环：

```python
    for i in range(1, args.rounds + 1):
        order = [("control", False), ("treatment", True)]
        if args.counterbalance and i % 2 == 0:
            order.reverse()
        side_rows = {}
        for side, treatment in order:
            label = f"#{i}/{args.rounds} {side}"
            print(f"\n[ab] {label}", flush=True)
            round_dir = Path(args.out).parent
            out_path = round_dir / (
                f"{Path(args.out).stem}-{'t' if treatment else 'c'}{i}.json")
            row = run_round(args.profile, treatment,
                            args.dds if treatment else False,
                            args.eviction if treatment else False,
                            args.selftest if treatment else False,
                            out_path, args.wait_menu, args.linger)
            row.update(archive_round(args.profile,
                                     "t" if treatment else "c", i, log_dir))
            side_rows[side] = row
            print(f"[ab] {label}: menu={row.get('menu_s')}s "
                  f"err={row['failed']}/{row['verify']}/{row['class_errors']}",
                  flush=True)
        c = side_rows["control"]
        t = side_rows["treatment"]
        stats = stats_from_text(agent.read_text(encoding="utf-8", errors="replace")) \
            if agent.is_file() else {}
        rows.append({"control": c, "treatment": t, "lazy": stats,
                     "order": [side for side, _ in order]})
        print(f"[ab] #{i}: control={c.get('menu_s')}s treatment={t.get('menu_s')}s "
              f"lazy={stats}", flush=True)
```

3e. gates：

```python
        "logs_present": all(
            r[side].get("log_present", False)
            for r in rows for side in ("control", "treatment")),
        "no_texture_errors": all(
            r[side].get("log_present", False)
            and r[side]["failed"] == 0 and r[side]["verify"] == 0
            and r[side]["class_errors"] == 0 and r[side]["async_errors"] == 0
            and r[side]["corrupted"] == 0
            for r in rows for side in ("control", "treatment")),
...
        "treatment_dds_hit_positive": (not args.dds)
            or (lazy_median.get("ddsHit") or 0) > 0,
```

- [ ] **Step 4: 跑测试通过**

Run: `python -I -m pytest tests/tools/test_m26_ab.py -q`
Expected: 全部通过（原 6 + 新 5）。再跑 `python -I -m pytest tests/tools -q` → 298 passed（293 + 5）。实际计数以报告为准。

- [ ] **Step 5: 提交**

```bash
git add tools/m26_ab.py tests/tools/test_m26_ab.py
git commit -m "test(m27): make menu A/B fail closed and counterbalanced"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Task 6: 真实进程验证 + 文档 + 手动验收清单

**Files:**
- Create: `docs/m27-results.md`
- Create: `docs/m27-manual-acceptance.md`
- Modify: `docs/m26-results.md` §7.15（gates 状态）
- Modify: `技术笔记-纹理按需加载.md` §7（M2.7 状态）
- Modify: `大饼-DDS按需物化与LRU.md`（状态行）
- Run: `build/m27/*` 证据

**Interfaces:**
- Consumes: Tasks 1–5 commits；`tools/smoke_run.py`、`tools/m26_ab.py`、`tools/install_manifest.py`、`tools/install_agent.py`、`build-mod.sh`。
- Produces: M2.7 结果文档、默认开启资格矩阵、用户手动验收清单。

**Constraints:** 不改代码/默认值；不 push；manual battle/visual 不标 PASS；数字全部从 JSON/日志抄。

- [ ] **Step 1: 构建/安装两侧**

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

Expected: 两侧 `install_manifest.py` 非 Critical；`install_agent.py` 报 `no vmparams change`；`build-mod.sh` 通过 release_check；两侧 `blank.png` 非空。

- [ ] **Step 2: budget=1/grace=0 自动淘汰门禁**

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 30 \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --jvm-arg=-Dhypernova.textures.lazy.eviction=true \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.budgetMb=1 \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.graceMs=0 \
  --jvm-arg=-Dhypernova.textures.lazy.eviction.sceneDelayMs=100 \
  --jvm-arg=-Dhypernova.textures.lazy.selftest=true \
  --json-out build/m27/fix-auto.json
```

Expected: `ok=true`；`selftest=1`；`evictPasses>=1`；`evicted>=1`；`rematerialized>=1`；`placeholder>0`；`failed=disabled=dimMismatch=0`；`failedParked=0`（菜单无二次失败）；`evictPassMsMax` 有值；**最后一条稳定 summary** 的 `ddsFb*` 之和 == `ddsFallback`（瞬时快照可能差 1，不作为失败）；0 Failed/Verify/Class/Async/Corrupted。若 `evictPasses=0`，**停下报告**。

- [ ] **Step 3: 默认预算 selftest 回归**

```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 1 --linger 20 \
  --eviction --selftest --out build/m27/selftest.json
```

Expected: `selftest=1/evicted=1/rematerialized=1`；`startupBytes>0`；`evictableBytes=liveBytes-startupBytes-foreignBytes`；0 errors；gates 全 true。

- [ ] **Step 4: counterbalanced 菜单 A/B n=3**

```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 3 --linger 20 \
  --counterbalance --out build/m27/ab.json
```

Expected: `logs_present=true`、`all_rounds_ok=true`、`no_texture_errors=true`、`treatment_failed_zero=true`、`treatment_disabled_zero=true`、`treatment_dim_mismatch_zero=true`、`treatment_dds_disabled_zero=true`、`treatment_dds_hit_positive=true`。记录 C/T 中位、paired、逐进程 GPU、`startupBytes`/`foreignBytes`/`evictableBytes`、`ddsFb*` 分解。**不写时间收益**；若 delta 落在噪声内，按边界值记录。

- [ ] **Step 5: 长停留回归（默认预算，可选但建议）**

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 120 \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --jvm-arg=-Dhypernova.textures.lazy.eviction=true \
  --json-out build/m27/linger120.json
```

Expected: 0 errors；`evictPasses` 可为 0（默认 256 MB 无压力，符合预期）；`evictableBytes` 不得因 startup bytes 被推高；`evictPassMsMax` 不出现异常大值。若 `evictPasses>0` 且 `evicted=0`，检查 `emptyEvictPasses` 与 `evictableBytes` 是否一致，记录。

- [ ] **Step 6: 写 `docs/m27-results.md`**

结构：

```markdown
# M2.7 结果：有界 LRU 默认开启资格（default-on readiness）

- 日期/宿主/配置/验证方式（菜单锚点，非战斗）
- 状态：**代码侧 gates 关闭，默认仍 off；用户战斗/读档/分辨率/手动目检、A→B、stutter pending**
## 1. 结论（编号列表，含 commit）
## 2. 代码变化与测试（每 Task：commit、测试计数、关键行为）
## 3. 实机门禁（budget=1 / selftest / linger120，表格：counter → value）
## 4. counterbalanced A/B（C/T 中位、paired、GPU proc、lazy_median）
## 5. 默认开启资格矩阵（gate → 状态 → 证据）
## 6. 剩余 user gates（战斗/读档/分辨率/手动、A→B、stutter、W-2/W-3/refcount）
## 7. 默认/回滚/文件
## 8. 限制
```

矩阵至少包含：

| Gate | 状态 | 证据 |
|---|---|---|
| 预算口径（startup/foreign 排除） | fixed | Task 1 + `startupBytes`/`foreignBytes`/`evictableBytes` |
| W-5 pick→evict TOCTOU | fixed | Task 2 单测 + `evictOne` 二次校验 |
| W-10 失败物化 id=0 | fixed | Task 2 停车 + `failedParked` |
| W-4 ddsFallback 盲区 | closed（可诊断） | Task 3 原因计数 + 实机分解；BRIDGE 自 M2.7 起计入总数，M2.6/M2.7 仅在 `ddsDisabled=0` 时可直接比较 |
| W-7 DDS commit 监视器 | defensive fixed | Task 2 `synchronized(loader)` |
| M2.5 W5 发行包 mod 集 | documented + fail-open | README + release_check |
| M2.5 W6 agent jar 新鲜度 | fixed | build-mod 强制重建/新鲜度/release_check |
| refcount/REQ-R1-10 | **not implementable**（无全局注册表） | owned-only + 文档 |
| 第三方 id 缓存（W-3） | **residual** | owned-only + 文档 |
| GL context 重建（W-2） | **user gate** | 分辨率/alt-tab 手动验收 |
| 战斗/读档/分辨率/手动目检 | **user gate** | `docs/m27-manual-acceptance.md` |
| A→B 长会话净 VRAM | **user gate** | 手动 |
| >200 ms stutter | **user gate** | 手动 + `evictPassMsMax` 仅菜单旁证 |

- [ ] **Step 7: 写 `docs/m27-manual-acceptance.md`**

内容至少：

```markdown
# M2.7 手动验收清单（战斗/读档/分辨率/长会话）

前置：两侧安装最新 agent；开启 lazy+DDS+eviction（默认预算 256 MB）；
记录 `saves/hypernova/scripts-agent.log` 最后一条 summary + starsector.log。

1. 战斗：进入一场 5–10 分钟战斗，观察 0 `Failed to load texture`、0
   `VerifyError`/`ClassFormatError`/`AsyncException`/`isStateCorrupted`；记录
   `evictPasses/evicted/rematerialized/evictPassMsMax/failedParked/ddsFallback`
   及原因分解；主观记录 >200 ms 卡顿次数。
2. 读档/存档：读档两次、存档一次，确认无白块/错位/崩溃；记录 `dimMismatch`、
   `reregistered`。
3. 分辨率/全屏/alt-tab：1707x1067 → 2560x1440 → 返回；确认占位纹理不残留
   （W-2）；若 lazy 因 `dimMismatch` 自动禁用，记录为 fail-open，不是崩溃。
4. A→B 长会话：A 场景 10 分钟 → B 场景 10 分钟，记录逐进程 GPU dedicated
   曲线（菜单/战斗/退出）与 `liveBytes/evictableBytes` 漂移。
5. 回滚：`textures.lazy.enabled=false` 或 `-Dhypernova.textures.lazy=false`，
   确认行为回到 M2。
6. 判定：全部通过才可讨论 default-on；任何一项失败先记录再修。
```

- [ ] **Step 8: 回写 `docs/m26-results.md` §7.15 / 技术笔记 / 大饼**

- `docs/m26-results.md` §7.15：把预算口径、W-4、W-5、W-10、W-7、M2.5 W5/W6 标为 “M2.7 fixed/closed（commit …）”；保留 refcount/第三方 id/W-2/user gates 为 open。
- `技术笔记-纹理按需加载.md` §7 M2.7 段：新增一段状态（代码侧 gates 关闭，默认 off，用户验收 pending），链接 `docs/m27-results.md`。
- `大饼-DDS按需物化与LRU.md` 状态行：更新为 “M2.7 代码侧 gates 关闭；默认 off；剩余 user gates”。
- 不改 `docs/m26-results.md` 的历史数字；M2.7 数字只写新文件。

- [ ] **Step 9: 回归 + 提交 docs**

```bash
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
git add docs/m27-results.md docs/m27-manual-acceptance.md docs/m26-results.md \
        技术笔记-纹理按需加载.md 大饼-DDS按需物化与LRU.md
git commit -m "docs(m27): record default-on readiness gates and manual acceptance"
```
Commit message append `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。

---

## Self-review

- **Spec coverage**：预算口径 → Task 1；W-5/W-10/oldId/W-7 → Task 2；W-4 → Task 3；M2.5 W5/W6 → Task 4；工具 fail-closed/counterbalance → Task 5；实机门禁/文档/用户清单 → Task 6。refcount/第三方 id/W-2/user gates 明确记为 residual（R-M27-2/3/5），不是漏项。
- **Step scan**：每个 Step 有测试/代码/命令/预期；无 TBD。CHECK 分支的双重计数在 Task 3 Step 3d 里明确要求删除裸计数。
- **Type consistency**：Task 1 `evictableBytes(long,long,long)` 与 Task 2 `evictOne(ProxyEntry)`；Task 2 `parkFailedProxy(ProxyEntry,boolean,int,ProxyReset)`；Task 3 `DdsFallbackReason`/`noteDdsFallback`；Task 4 `check_zip(Path, Path|None)`；Task 5 `--counterbalance` 与 `log_present`。测试名与实现签名一致。
- **Review Focus**：每类风险都有任务测试：预算分类/refresh 迁移、TOCTOU/停车、原因计数、release zip、工具 fail-closed、实机 gate。
- **Proportion**：计划只含改动的方法/测试/命令，不是整文件转录。

**Known residual**：refcount/REQ-R1-10 无全局注册表不可实现；第三方 id 缓存与 GL context 重建仍是用户/后续门禁；`ddsBytes` 仍是 1 B/px 估算；`evictPassMsMax` 只覆盖菜单/长停留，不是逐帧 P99。
