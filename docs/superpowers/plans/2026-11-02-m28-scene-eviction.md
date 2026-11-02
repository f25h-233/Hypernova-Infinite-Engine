# M2.8 更激进场景淘汰（experimental / default off）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status（2026-11-02 收口）:** Tasks 1–3 已完成并通过两轮 review；**Task 4 实机 gate 由用户跳过**（260mods 生涯大地图移动严重卡顿，不作为 Hypernova 结论）。默认 off、实验性；**不宣称显存收益**。结果见 `docs/m28-results.md`。

**Goal:** 在 **战役 → 战斗** 切换时，对 `owned=true`、非 `startup`、非保护集的已物化纹理代理执行一次**不受 256 MB 预算限制**的强制 LRU 淘汰；战斗进行中不再淘汰；默认 **off**、实验性、可回滚，并用控制/处理两组真实进程战斗记录判定是否值得保留。

**Architecture:** 不新增 transformer、不改默认值、不引入新依赖。`LazyTextures` 在主线程的 `maybeRunEviction` 上以 250 ms 节流轮询 `Global.getCurrentState()`；只在观察到 `CAMPAIGN → COMBAT` 时 arm 一次 scene pass。scene pass 分 8 个 chunk（默认每 chunk 最多 64 张，chunk 间隔 100 ms，窗口 10 s），按 `lastUseNanos` 升序选择，忽略 budget/low-water；有效 grace = arm 后经过的时间 + `scene_unload.grace_ms`，因此战斗期间被 touch 过的纹理不会反复被淘汰。执行复用 `evictOne` 的 `owned`/`startup`/`basic`/占位/删 id 路径；占位不可用时 fail-open。配置位于 `textures.lazy.eviction.scene_unload`，默认 `enabled=false`。

**Tech Stack:** Java 17（major 61）、ASM 9.1、JUnit 5、Python 3.14 stdlib（`python -I`）、pytest 9、`tools/smoke_run.py`、Git Bash。

**Spec:** `技术笔记-纹理按需加载.md` §5.7/§6/§7（M2.8 边界）、`docs/m27-results.md`、`docs/m27-manual-acceptance.md`、`docs/superpowers/plans/2026-11-02-m27-default-on-readiness.md`、REQ-R1-10、INV-08/INV-10。

---

## Global Constraints

- **默认 off 不变**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`、`textures.lazy.eviction.scene_unload.enabled=false`；本里程碑不开默认、不改 `hypernova.json`、不改 `enabled_mods.json`、不改发行默认值。
- **scene pass 需要 eviction 主开关**：`scene_unload.enabled=true` 但 `eviction.enabled=false` 时运行期不生效，summary `sceneUnload=0`，只打一条 INFO。
- **线程红线**：scene 探测、arm、chunk、`evictOne`、GL 删除、占位复位只在 `runtimeMain`；loading/worker 路径直接返回。
- **owned-only 不变**：scene pass 只处理 `owned=true`、`ready=true`、`glId>0`、`bytes>0` 的代理；`owned=false`/`startup`/保护路径永不淘汰。
- **保护集**：`graphics/ui/`、`graphics/fonts/`、`graphics/intro/`、`graphics/backgrounds/`、`startup`、`owned=false`、`ready=false`。
- **不按路径/类名猜 campaign/combat**：只用 `Global.getCurrentState()` 的字符串值；观察不到 `CAMPAIGN → COMBAT` 就不 arm。
- **有界**：每次切换最多 `SCENE_PASS_MAX_CHUNKS=8` 个 chunk；每 chunk 最多 `scene_unload.max_per_pass`（默认 64）；chunk 间隔 100 ms；arm 后 10 s 窗口截止；无候选立即取消剩余 chunk；不无限循环。
- **有效 grace**：`sceneGraceNanos(now, armed, configured) = max(0, now-armed) + configured`。默认 `configured=0`；战斗期间被 `touch` 的纹理（lastUse > armed）不会被本场 scene pass 淘汰。
- **无新 transformer/无新依赖**；agent 不 import 游戏/FR 类（反射）。
- **测试**：每个 Task TDD；纯函数覆盖触发、选择、保护集、grace、调度、上限；既有 agent 182 found / 181 pass / 1 known abort 与 pytest 299 不回归。
- **真实门禁**：干净存档/小舰队，对照组（scene_unload=false）与处理组（scene_unload=true）各跑一次战役→战斗→返回；处理组 `sceneEvictions>0`、`failedParked=0`、0 五类纹理错误、无白块/错位/崩溃；战斗时进程 GPU dedicated 低于对照组。没有证据不得写“有效”或“无收益”。
- **不改 M2.7 已闭合 gates**：预算口径、W-5/W-10、DDS 原因计数、W-7 defensive、release checks、A/B 工具行为不变。
- **不 push**：用户未给 push 授权；所有 commit 留在本地，收尾时把 push/merge 选项呈给用户。
- **Escape hatch**：若实现与计划不符按实际修正并报告；**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**

## Review Focus

1. **触发只认 CAMPAIGN→COMBAT**：菜单/任务/读档状态不得 arm；进入战斗后只能 arm 一次，战斗中不重复 arm。
2. **保护集与 grace**：`graphics/backgrounds/` 必须被普通 LRU 和 scene pass 同时保护；战斗期间 touch 过的纹理不得被 scene pass 淘汰（避免战斗纹理反复物化/淘汰）。
3. **有界与取消**：8 chunk/100 ms/10 s 窗口/空候选取消/离开战斗取消必须同时成立；不得出现无限 pass 或每次 lookup 全量扫描。
4. **执行安全**：scene pass 复用 `evictOne`，`synchronized(e)` 二次 `canEvict` 不变；占位不可用时 fail-open，不把 lazy 整体禁用。
5. **指标口径**：`scenePasses` 是 chunk 数、`sceneEvictions` 是成功复位数；`evicted` 仍是总数（含 scene）；`sceneEvictMsMax` 只是 chunk 耗时，不是帧 P99。
6. **默认关闭零成本**：`sceneUnload=false` 时不调用 `Global.getCurrentState()`、不扫描、不改变既有 LRU 行为。
7. **配置解析 fail-open**：坏 JSON/缺失 `scene_unload` 必须回到默认（false/0/64），不得抛异常。
8. **实机证据**：控制/处理两组同场景；GPU、错误、视觉、`failedParked` 全部记录；失败就回退当前 LRU，不阻塞 M4/M6/M5。

---

## Pre-flight（controller）

- **Mode:** `pipeline`（Task 1 改配置，Task 2 改核心状态机，Task 3 改工具/文档，均为线性依赖）。
- **BASE:** `e7baa9c`（M2.7 收口，`origin/main`）。
- **Workspace:** `.superpowers/sdd/2026-11-02-m28-scene-eviction/`。
- **用户授权:** “开始M2.8”；按 M2.7 惯例，**不默认开启、不 push**。
- **Rulings:**
  - **R-M28-1**：M2.8 的“激进”按路线裁决解释为**场景切换强制 LRU**，不是全局更小预算/更短 grace；不做路径猜测。
  - **R-M28-2**：scene pass 是 `eviction` 的子特性；主开关 off 时 scene 配置不生效。
  - **R-M28-3**：触发用主线程 250 ms 节流轮询 `Global.getCurrentState()`，不依赖 `noteGameState` 的类名变化（避免类名/路径猜测和时序问题）。
  - **R-M28-4**：有效 grace 从 arm 时刻起算；默认 `grace_ms=0` 仍然是“arm 后 touch 过的纹理受保护”，这是防战斗 churn 的必要语义，不是额外开关。
  - **R-M28-5**：每次切换有界 8 chunk × 默认 64 = 最多 512 张；不足时由下一场战斗再处理；不在战斗中持续淘汰。
  - **R-M28-6**：`graphics/backgrounds/` 加入 `isBasicPath`，同时保护普通 LRU；这是 spec 明确要求，属于安全收紧。
  - **R-M28-7**：真实战斗是用户门禁；本轮交付自动化单测、构建、安装与 gate 工具，实机数字由用户跑控制/处理两组后回填。
- **写者表 / 接口:**

| 文件 | 任务 | 说明 |
|---|---|---|
| `src/agent/java/hypernova/agent/textures/LazyTextureConfig.java` | 1 | 新 record 组件 + JSON/property 解析 |
| `tests/agent/java/hypernova/LazyTextureConfigTest.java` | 1 | 默认值 + JSON + property |
| `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java` | 1, 2 | 保护集、触发、选择、grace、调度 |
| `src/agent/java/hypernova/agent/textures/LazyTextures.java` | 1, 2 | `isBasicPath`、scene 状态机、scene pass、summary |
| `tools/m28_scene_gate.py`（新） | 3 | summary/错误/GPU 证据解析 |
| `tests/tools/test_m28_scene_gate.py`（新） | 3 | 纯函数测试 |
| `docs/m28-manual-acceptance.md`（新） | 3 | 控制/处理两组手动步骤 |
| `docs/m28-results.md`（新） | 4 | 实机结果与裁决 |
| `技术笔记-纹理按需加载.md` | 4 | M2.8 状态回写 |

---

## Task 1: 配置键 + 背景保护集

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextureConfig.java`
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`（`isBasicPath`）
- Modify: `tests/agent/java/hypernova/LazyTextureConfigTest.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

**Interfaces:**
- Consumes: 现有 `LazyTextureConfig.load(...)` 12 参数重载、`bool(...)`/`integer(...)` 辅助函数、`isBasicPath(String)`。
- Produces:
  - `LazyTextureConfig.evictionSceneUnload()` → `boolean`（默认 `false`）
  - `LazyTextureConfig.evictionSceneUnloadGraceMs()` → `int`（默认 `0`）
  - `LazyTextureConfig.evictionSceneUnloadMaxPerPass()` → `int`（默认 `64`）
  - JSON 键：`textures.lazy.eviction.scene_unload.enabled` / `.grace_ms` / `.max_per_pass`
  - 系统属性：`hypernova.textures.lazy.eviction.sceneUnload` / `.sceneUnload.graceMs` / `.sceneUnload.maxPerPass`
  - `LazyTextures.isBasicPath("graphics/backgrounds/x.jpg") == true`
- **Dependencies:** 无
- **Touches:** `src/agent/java/hypernova/agent/textures/LazyTextureConfig.java`、`src/agent/java/hypernova/agent/textures/LazyTextures.java`、`tests/agent/java/hypernova/LazyTextureConfigTest.java`、`tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

---

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/LazyTextureConfigTest.java` 的 `defaultsOff` 追加：

```java
        assertFalse(c.evictionSceneUnload());
        assertEquals(0, c.evictionSceneUnloadGraceMs());
        assertEquals(64, c.evictionSceneUnloadMaxPerPass());
```

把 `configFileParsesDdsAndEviction` 的 JSON 字符串改为（其余断言不变）：

```java
        Files.writeString(cfg, "{\"textures\":{\"lazy\":{"
                + "\"enabled\":true,\"dds\":false,\"selftest\":true,"
                + "\"eviction\":{\"enabled\":true,\"budget_mb\":32,\"grace_ms\":500,"
                + "\"scene_delay_ms\":100,\"max_per_pass\":4,"
                + "\"scene_unload\":{\"enabled\":true,\"grace_ms\":250,"
                + "\"max_per_pass\":8}}}}}");
```

并在该测试末尾追加：

```java
        assertTrue(c.evictionSceneUnload());
        assertEquals(250, c.evictionSceneUnloadGraceMs());
        assertEquals(8, c.evictionSceneUnloadMaxPerPass());
```

在 `LazyTextureConfigTest` 末尾追加：

```java
    @Test
    void sceneUnloadFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, null,
                null, null, null, null, null, null,
                "true", "150", "7", null, null);
        assertTrue(c.evictionSceneUnload());
        assertEquals(150, c.evictionSceneUnloadGraceMs());
        assertEquals(7, c.evictionSceneUnloadMaxPerPass());
    }
```

`tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java` 末尾追加：

```java
    @Test
    void backgroundsAreBasicPath() {
        assertTrue(LazyTextures.isBasicPath("graphics/backgrounds/x.jpg"));
        assertTrue(LazyTextures.isBasicPath("graphics/ui/x.png"));
        assertTrue(LazyTextures.isBasicPath("graphics/fonts/x.png"));
        assertTrue(LazyTextures.isBasicPath("graphics/intro/x.png"));
        assertFalse(LazyTextures.isBasicPath("graphics/ships/x.png"));
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyTextureConfig`

Expected: 编译失败（`evictionSceneUnload` 等不存在；15 参数 `load` 不存在）。

Run: `bash tools/java/run-agent-tests.sh LazyEviction`

Expected: `backgroundsAreBasicPath` FAIL（`graphics/backgrounds/x.jpg` 当前返回 false）。

- [ ] **Step 3: 实现配置组件与解析**

`LazyTextureConfig.java` 的 record 头部改为：

```java
public record LazyTextureConfig(
        boolean enabled,
        boolean probe,
        Path skipFile,
        Path manifestFile,
        boolean dds,
        boolean eviction,
        int evictionBudgetMb,
        int evictionGraceMs,
        int evictionSceneDelayMs,
        int evictionMaxPerPass,
        boolean evictionSceneUnload,
        int evictionSceneUnloadGraceMs,
        int evictionSceneUnloadMaxPerPass,
        boolean selftest) {
```

默认值常量追加：

```java
    private static final int DEFAULT_SCENE_GRACE_MS = 0;
    private static final int DEFAULT_SCENE_MAX_PER_PASS = DEFAULT_MAX_PER_PASS;
```

类 Javadoc 的 M2.6 行后追加一行：

```java
 * <p>M2.8 scene_unload defaults: enabled=false, grace_ms=0, max_per_pass=64
 * (only active when eviction=true).
```

`load()` 改为：

```java
    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy"),
                System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                System.getProperty("hypernova.textures.lazy.manifestFile"),
                System.getProperty("hypernova.textures.lazy.dds"),
                System.getProperty("hypernova.textures.lazy.eviction"),
                System.getProperty("hypernova.textures.lazy.eviction.budgetMb"),
                System.getProperty("hypernova.textures.lazy.eviction.graceMs"),
                System.getProperty("hypernova.textures.lazy.eviction.sceneDelayMs"),
                System.getProperty("hypernova.textures.lazy.eviction.maxPerPass"),
                System.getProperty("hypernova.textures.lazy.eviction.sceneUnload"),
                System.getProperty("hypernova.textures.lazy.eviction.sceneUnload.graceMs"),
                System.getProperty("hypernova.textures.lazy.eviction.sceneUnload.maxPerPass"),
                System.getProperty("hypernova.textures.lazy.selftest"),
                locateConfig());
    }
```

4 参数 seam 改为：

```java
    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, Path configFile) {
        return load(enabledProp, probeProp, skipProp, null, null, null,
                null, null, null, null, null, null, null, null, configFile);
    }
```

完整重载改为：

```java
    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, String manifestProp,
                                         String ddsProp, String evictionProp,
                                         String budgetProp, String graceProp,
                                         String delayProp, String maxProp,
                                         String sceneUnloadProp, String sceneGraceProp,
                                         String sceneMaxProp,
                                         String selftestProp, Path configFile) {
        JSONObject lazy = lazyJson(configFile);
        JSONObject eviction = lazy == null ? null : lazy.optJSONObject("eviction");
        JSONObject scene = eviction == null ? null : eviction.optJSONObject("scene_unload");
        Path modRoot = modRoot(configFile);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null && modRoot != null) {
            Path dir = modRoot.resolve("data/config/hypernova");
            Path v2 = dir.resolve("lazy-skip-v2.txt");
            skip = Files.isRegularFile(v2) ? v2 : dir.resolve("lazy-skip-v1.txt");
        }
        Path manifest;
        if (manifestProp != null && !manifestProp.isBlank()) {
            manifest = Path.of(manifestProp);
        } else {
            manifest = skip == null || skip.getParent() == null
                    ? null : skip.getParent().resolve("manifest-v1.json");
        }
        return new LazyTextureConfig(
                bool(enabledProp, lazy, "enabled", false),
                bool(probeProp, lazy, "probe", false),
                skip,
                manifest,
                bool(ddsProp, lazy, "dds", true),
                bool(evictionProp, eviction, "enabled", false),
                integer(budgetProp, eviction, "budget_mb", DEFAULT_BUDGET_MB),
                integer(graceProp, eviction, "grace_ms", DEFAULT_GRACE_MS),
                integer(delayProp, eviction, "scene_delay_ms", DEFAULT_SCENE_DELAY_MS),
                integer(maxProp, eviction, "max_per_pass", DEFAULT_MAX_PER_PASS),
                bool(sceneUnloadProp, scene, "enabled", false),
                integer(sceneGraceProp, scene, "grace_ms", DEFAULT_SCENE_GRACE_MS),
                integer(sceneMaxProp, scene, "max_per_pass", DEFAULT_SCENE_MAX_PER_PASS),
                bool(selftestProp, lazy, "selftest", false));
    }
```

`LazyTextures.isBasicPath` 改为：

```java
    static boolean isBasicPath(String path) {
        if (path == null) return true;
        return path.startsWith("graphics/ui/")
                || path.startsWith("graphics/fonts/")
                || path.startsWith("graphics/intro/")
                || path.startsWith("graphics/backgrounds/");
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh LazyTextureConfig`

Expected: `LazyTextureConfigTest` 全部 PASS。

Run: `bash tools/java/run-agent-tests.sh LazyEviction`

Expected: `LazyEvictionTest` 全部 PASS（含 `backgroundsAreBasicPath`）。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextureConfig.java \
        src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/LazyTextureConfigTest.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java
git commit -m "feat(m28): add scene unload config and protect backgrounds"
```

---

## Task 2: 场景触发、强制 LRU 选择、scene pass 与指标

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Modify: `tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

**Interfaces:**
- Consumes: Task 1 的 `evictionSceneUnload()` / `evictionSceneUnloadGraceMs()` / `evictionSceneUnloadMaxPerPass()`；现有 `evictOne`、`canEvict`、`isBasicPath`、`maybeRunEviction`、`summary`、`resetGateStateForTest`。
- Produces:
  - `LazyTextures.shouldArmSceneUnload(String prev, String current)` → `boolean`
  - `LazyTextures.sceneGraceNanos(long now, long armedNanos, long configuredGraceNanos)` → `long`
  - `LazyTextures.nextScenePassDue(int remaining, long now, long delayNanos)` → `long`
  - `LazyTextures.shouldRunScenePass(boolean eviction, boolean sceneUnload, boolean disabled, int remaining, long dueNanos, long now, boolean inCombat, long armedNanos, long windowNanos)` → `boolean`
  - `LazyTextures.selectSceneVictims(List<ProxyEntry> ready, long now, long graceNanos, int max)` → `List<ProxyEntry>`
  - `LazyTextures.currentGameStateName()` → `String | null`（package-private）
  - summary 新键：`sceneUnload` / `scenePasses` / `sceneEvictions` / `sceneEvictMsTotal` / `sceneEvictMsMax` / `scenePending`
- **Dependencies:** Task 1
- **Touches:** `src/agent/java/hypernova/agent/textures/LazyTextures.java`、`tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java`

---

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java` 末尾追加：

```java
    @Test
    void sceneArmsOnlyOnCampaignToCombat() {
        assertFalse(LazyTextures.shouldArmSceneUnload(null, "COMBAT"));
        assertTrue(LazyTextures.shouldArmSceneUnload("CAMPAIGN", "COMBAT"));
        assertFalse(LazyTextures.shouldArmSceneUnload("COMBAT", "COMBAT"));
        assertFalse(LazyTextures.shouldArmSceneUnload("COMBAT", "CAMPAIGN"));
        assertFalse(LazyTextures.shouldArmSceneUnload("TITLE", "COMBAT"));
        assertFalse(LazyTextures.shouldArmSceneUnload("CAMPAIGN", null));
    }

    @Test
    void sceneVictimsIgnoreBudgetAndLowWater() {
        LazyTextures.ProxyEntry old = entry("old", 30, 100);
        LazyTextures.ProxyEntry mid = entry("mid", 30, 200);
        LazyTextures.ProxyEntry young = entry("young", 30, 300);
        List<LazyTextures.ProxyEntry> ready = List.of(old, mid, young);
        assertTrue(LazyTextures.selectVictims(ready, 90, 100, 0, 1_000, 10).isEmpty());
        assertEquals(List.of(old, mid, young),
                LazyTextures.selectSceneVictims(ready, 1_000, 0, 10));
    }

    @Test
    void sceneVictimsProtectBasicStartupForeignAndYoung() {
        LazyTextures.ProxyEntry startup = entry("startup", 10, 100);
        startup.startup = true;
        LazyTextures.ProxyEntry ui = entry("graphics/ui/x.png", 10, 100);
        LazyTextures.ProxyEntry fonts = entry("graphics/fonts/x.png", 10, 100);
        LazyTextures.ProxyEntry intro = entry("graphics/intro/x.png", 10, 100);
        LazyTextures.ProxyEntry background = entry("graphics/backgrounds/x.jpg", 10, 100);
        LazyTextures.ProxyEntry foreign = entry("foreign", 10, 100);
        foreign.owned = false;
        LazyTextures.ProxyEntry young = entry("young", 10, 9_950);
        LazyTextures.ProxyEntry notReady = entry("notReady", 10, 100);
        notReady.ready = false;
        LazyTextures.ProxyEntry ok = entry("ok", 10, 100);
        assertEquals(List.of(ok), LazyTextures.selectSceneVictims(
                List.of(startup, ui, fonts, intro, background, foreign,
                        young, notReady, ok), 10_000, 1_000, 10));
    }

    @Test
    void sceneVictimsAreLruOrderedAndCapped() {
        LazyTextures.ProxyEntry a = entry("a", 10, 300);
        LazyTextures.ProxyEntry b = entry("b", 10, 100);
        LazyTextures.ProxyEntry c = entry("c", 10, 200);
        assertEquals(List.of(b, c), LazyTextures.selectSceneVictims(
                List.of(a, b, c), 1_000, 0, 2));
        assertTrue(LazyTextures.selectSceneVictims(
                List.of(a, b, c), 1_000, 0, 0).isEmpty());
    }

    @Test
    void sceneGraceIncludesElapsedSinceArm() {
        assertEquals(0, LazyTextures.sceneGraceNanos(1_000, 1_000, 0));
        assertEquals(500, LazyTextures.sceneGraceNanos(1_500, 1_000, 0));
        assertEquals(700, LazyTextures.sceneGraceNanos(1_500, 1_000, 200));
        assertEquals(200, LazyTextures.sceneGraceNanos(1_500, 0, 200));
    }

    @Test
    void sceneGraceProtectsTexturesTouchedAfterArm() {
        long armed = 1_000;
        long now = 3_000;
        long grace = LazyTextures.sceneGraceNanos(now, armed, 0);
        LazyTextures.ProxyEntry combatTex = entry("combat", 10, 2_500);
        LazyTextures.ProxyEntry campaignTex = entry("campaign", 10, 900);
        assertEquals(List.of(campaignTex), LazyTextures.selectSceneVictims(
                List.of(combatTex, campaignTex), now, grace, 10));
    }

    @Test
    void sceneScheduleTruthTable() {
        assertTrue(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 100, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                false, true, false, 8, 100, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, false, false, 8, 100, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, true, 8, 100, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 0, 100, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 0, 100, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 100, 99, true, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 100, 100, false, 100, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 100, 100, true, 0, 1_000));
        assertFalse(LazyTextures.shouldRunScenePass(
                true, true, false, 8, 100, 1_200, true, 100, 1_000));
    }

    @Test
    void sceneNextDueCapsChunks() {
        assertEquals(1_050, LazyTextures.nextScenePassDue(3, 1_000, 50));
        assertEquals(0, LazyTextures.nextScenePassDue(0, 1_000, 50));
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`

Expected: 编译失败（`shouldArmSceneUnload` / `selectSceneVictims` / `sceneGraceNanos` / `shouldRunScenePass` / `nextScenePassDue` 不存在）。

- [ ] **Step 3: 实现 scene 状态机与 pass**

3a. 在 `EVICT_EMPTY_BACKOFF_NANOS` 之后、`// ---- M2.6 selftest state ----` 之前插入：

```java
    // ---- M2.8 scene unload (aggressive, experimental; default off) ----
    private static volatile boolean sceneUnload;
    private static volatile long sceneUnloadGraceNanos;
    private static volatile int sceneUnloadMaxPerPass;
    private static volatile long scenePassDueNanos;
    private static volatile long sceneArmedNanos;
    private static volatile int scenePassesRemaining;
    private static volatile long nextSceneProbeNanos;
    private static volatile String lastGameStateName;
    private static final AtomicLong SCENE_PASSES = new AtomicLong();
    private static final AtomicLong SCENE_EVICTIONS = new AtomicLong();
    private static final AtomicLong SCENE_PASS_NANOS_TOTAL = new AtomicLong();
    private static final AtomicLong SCENE_PASS_NANOS_MAX = new AtomicLong();
    static final int SCENE_PASS_MAX_CHUNKS = 8;
    static final long SCENE_CHUNK_DELAY_NANOS = 100_000_000L;
    static final long SCENE_WINDOW_NANOS = 10_000_000_000L;
    static final long SCENE_STATE_PROBE_NANOS = 250_000_000L;
```

3b. `start()` 在 `evictionMaxPerPass = ...` 之后追加：

```java
        sceneUnload = config.evictionSceneUnload();
        sceneUnloadGraceNanos = Math.max(0, config.evictionSceneUnloadGraceMs()) * 1_000_000L;
        sceneUnloadMaxPerPass = Math.max(1, config.evictionSceneUnloadMaxPerPass());
        if (sceneUnload && !eviction) {
            AgentLog.info("lazy: scene unload requires textures.lazy.eviction.enabled=true; inactive");
        }
```

3c. `resetGateStateForTest()` 在 `GAME_STATE_FAIL_LOGGED.set(false);` 之后追加：

```java
        SCENE_PASSES.set(0);
        SCENE_EVICTIONS.set(0);
        SCENE_PASS_NANOS_TOTAL.set(0);
        SCENE_PASS_NANOS_MAX.set(0);
        scenePassDueNanos = 0;
        sceneArmedNanos = 0;
        scenePassesRemaining = 0;
        nextSceneProbeNanos = 0;
        lastGameStateName = null;
```

3d. `maybeRunEviction` 改为（在 `if (!eviction || disabled) return;` 之后插入两行，其余不变）：

```java
    static void maybeRunEviction(long now) {
        if (Thread.currentThread() != runtimeMain) return;
        if (!PENDING_DELETE.isEmpty()) drainPendingDeletes();
        if (!eviction || disabled) return;
        maybeArmSceneUnload(now);
        maybeRunSceneEviction(now);
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
```

3e. 在 `isInCombat()` 之后插入：

```java
    static String currentGameStateName() {
        Method m = resolveGameStateMethod();
        if (m == null) return null;
        try {
            Object state = m.invoke(null);
            return state == null ? null : String.valueOf(state);
        } catch (Throwable t) {
            return null;
        }
    }

    static boolean isDefinitelyInCombat() {
        return "COMBAT".equals(currentGameStateName());
    }
```

3f. 在 `shouldArmOnTransition` / `nextDueAfterPass` 之后插入纯函数：

```java
    static boolean shouldArmSceneUnload(String prev, String current) {
        return "CAMPAIGN".equals(prev) && "COMBAT".equals(current);
    }

    static long sceneGraceNanos(long now, long armedNanos, long configuredGraceNanos) {
        if (armedNanos == 0) return configuredGraceNanos;
        return Math.max(0L, now - armedNanos) + configuredGraceNanos;
    }

    static long nextScenePassDue(int remaining, long now, long delayNanos) {
        return remaining > 0 ? now + delayNanos : 0;
    }

    static boolean shouldRunScenePass(boolean eviction, boolean sceneUnload,
                                      boolean disabled, int remaining, long dueNanos,
                                      long now, boolean inCombat, long armedNanos,
                                      long windowNanos) {
        if (!eviction || !sceneUnload || disabled) return false;
        if (remaining <= 0 || dueNanos == 0 || now < dueNanos) return false;
        if (!inCombat || armedNanos == 0) return false;
        long elapsed = now - armedNanos;
        return elapsed >= 0 && elapsed <= windowNanos;
    }
```

3g. 在 `maybeRunEviction` 之后插入调度与执行方法：

```java
    static void maybeArmSceneUnload(long now) {
        if (!eviction || !sceneUnload || disabled) return;
        if (now < nextSceneProbeNanos) return;
        nextSceneProbeNanos = now + SCENE_STATE_PROBE_NANOS;
        String current = currentGameStateName();
        if (current == null) return;
        if (shouldArmSceneUnload(lastGameStateName, current)) {
            armScenePass(now);
        }
        lastGameStateName = current;
    }

    private static void armScenePass(long now) {
        sceneArmedNanos = now;
        scenePassesRemaining = SCENE_PASS_MAX_CHUNKS;
        scenePassDueNanos = now + evictionSceneDelayNanos;
        AgentLog.info("lazy: scene unload armed CAMPAIGN -> COMBAT; chunks="
                + SCENE_PASS_MAX_CHUNKS + " firstPassInMs="
                + (evictionSceneDelayNanos / 1_000_000L));
    }

    private static void maybeRunSceneEviction(long now) {
        if (!eviction || !sceneUnload || disabled) return;
        if (Thread.currentThread() != runtimeMain) return;
        int remaining = scenePassesRemaining;
        long due = scenePassDueNanos;
        if (remaining <= 0 || due == 0 || now < due) return;
        long armed = sceneArmedNanos;
        boolean combat = isDefinitelyInCombat();
        if (!shouldRunScenePass(eviction, sceneUnload, disabled, remaining, due, now,
                combat, armed, SCENE_WINDOW_NANOS)) {
            if (remaining > 0 && due != 0
                    && (!combat || armed == 0 || now - armed > SCENE_WINDOW_NANOS)) {
                scenePassesRemaining = 0;
                scenePassDueNanos = 0;
            }
            return;
        }
        scenePassesRemaining = remaining - 1;
        scenePassDueNanos = nextScenePassDue(scenePassesRemaining, now,
                SCENE_CHUNK_DELAY_NANOS);
        sceneEvictPass(now);
    }

    private static void sceneEvictPass(long now) {
        if (!eviction || !sceneUnload || disabled
                || Thread.currentThread() != runtimeMain) return;
        long t0 = System.nanoTime();
        List<ProxyEntry> ready = new ArrayList<>();
        for (ProxyEntry e : PROXIES.values()) {
            if (e.ready) ready.add(e);
        }
        long grace = sceneGraceNanos(now, sceneArmedNanos, sceneUnloadGraceNanos);
        List<ProxyEntry> victims = selectSceneVictims(ready, now, grace,
                sceneUnloadMaxPerPass);
        int n = 0;
        long bytes = 0;
        for (ProxyEntry e : victims) {
            long b = e.bytes;
            if (evictOne(e)) {
                n++;
                bytes += b;
            }
        }
        SCENE_PASSES.incrementAndGet();
        SCENE_EVICTIONS.addAndGet(n);
        long elapsed = System.nanoTime() - t0;
        SCENE_PASS_NANOS_TOTAL.addAndGet(elapsed);
        SCENE_PASS_NANOS_MAX.accumulateAndGet(elapsed, (a, b) -> Math.max(a, b));
        if (n > 0) {
            AgentLog.info("lazy: scene eviction pass evicted=" + n + " bytes=" + bytes
                    + " candidates=" + victims.size()
                    + " live=" + evictableBytes()
                    + " remaining=" + scenePassesRemaining);
        }
        if (elapsed >= 50_000_000L) {
            AgentLog.info("lazy: scene eviction pass slow " + (elapsed / 1_000_000L)
                    + " ms evicted=" + n + " candidates=" + victims.size()
                    + " live=" + evictableBytes());
        }
        if (victims.isEmpty()) {
            // Nothing eligible; later chunks would rescan the same proxies.
            scenePassesRemaining = 0;
            scenePassDueNanos = 0;
        }
    }
```

3h. 在 `canEvict` 之前插入候选判定，并把 `selectVictims` 的循环改成复用它：

```java
    private static boolean isEvictCandidate(ProxyEntry e, long now, long graceNanos) {
        if (e == null || !e.ready || e.bytes <= 0 || e.glId <= 0) return false;
        if (!e.owned || e.startup || isBasicPath(e.path)) return false;
        if (e.lastUseNanos == 0 || now - e.lastUseNanos < graceNanos) return false;
        return true;
    }
```

`selectVictims` 的过滤循环改为：

```java
        for (ProxyEntry e : ready) {
            if (!isEvictCandidate(e, now, graceNanos)) continue;
            candidates.add(e);
        }
```

3i. 在 `selectVictims` 之后插入：

```java
    static List<ProxyEntry> selectSceneVictims(List<ProxyEntry> ready, long now,
                                               long graceNanos, int max) {
        if (max <= 0) return List.of();
        List<ProxyEntry> candidates = new ArrayList<>();
        for (ProxyEntry e : ready) {
            if (!isEvictCandidate(e, now, graceNanos)) continue;
            candidates.add(e);
        }
        candidates.sort(Comparator.comparingLong(e -> e.lastUseNanos));
        if (candidates.size() > max) {
            return new ArrayList<>(candidates.subList(0, max));
        }
        return candidates;
    }
```

3j. `summary()` 末尾的 `failedParked` 行改为：

```java
                    + " failedParked=" + FAILED_PARKED.get()
                    + " sceneUnload=" + ((eviction && sceneUnload) ? 1 : 0)
                    + " scenePasses=" + SCENE_PASSES.get()
                    + " sceneEvictions=" + SCENE_EVICTIONS.get()
                    + " sceneEvictMsTotal=" + (SCENE_PASS_NANOS_TOTAL.get() / 1_000_000L)
                    + " sceneEvictMsMax=" + (SCENE_PASS_NANOS_MAX.get() / 1_000_000L)
                    + " scenePending=" + scenePassesRemaining);
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh LazyEviction`

Expected: `LazyEvictionTest` 全部 PASS。

Run: `bash tools/java/run-agent-tests.sh`

Expected: 全量 agent 测试 PASS；记录实际 found/pass/abort（基线 182/181/1，新增测试后应同步增加），known Windows symlink abort 不计失败。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextures.java \
        tests/agent/java/hypernova/agent/textures/LazyEvictionTest.java
git commit -m "feat(m28): forced LRU eviction on campaign-to-combat transition"
```

---

## Task 3: Gate 证据工具 + 手动验收清单

**Files:**
- Create: `tools/m28_scene_gate.py`
- Create: `tests/tools/test_m28_scene_gate.py`
- Create: `docs/m28-manual-acceptance.md`

**Interfaces:**
- Consumes: 现有 agent summary 行格式（`lazy probe: summary key=value ...`）、`starsector.log` 的 `Fast Rendering: v0.9.` session anchor、可选 GPU CSV（`timestamp,dedicated_mb,shared_mb`）。
- Produces:
  - `tools/m28_scene_gate.py` CLI：`--agent-log --starsector-log [--gpu-csv] [--out] [--require-scene] [--strict]`
  - `parse_summary_line(str) -> dict[str,int|str]`
  - `last_summary(str) -> dict`
  - `last_session(str, anchor=...) -> str`
  - `count_texture_errors(str) -> dict[str,int]`
  - `summarize_gpu(list[tuple]) -> dict`
  - `build_report(agent_text, starsector_text, gpu_rows=None) -> dict`
- **Dependencies:** Task 2（summary 新键）
- **Touches:** `tools/m28_scene_gate.py`、`tests/tools/test_m28_scene_gate.py`、`docs/m28-manual-acceptance.md`

---

- [ ] **Step 1: 写失败测试**

创建 `tests/tools/test_m28_scene_gate.py`：

```python
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m28_scene_gate", REPO / "tools/m28_scene_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_parse_summary_line_extracts_ints_and_strings():
    parsed = gate.parse_summary_line(
        "lazy probe: summary queue=1 evictPasses=361 sceneUnload=1 "
        "sceneEvictions=42 main=Thread-3")
    assert parsed["evictPasses"] == 361
    assert parsed["sceneUnload"] == 1
    assert parsed["main"] == "Thread-3"


def test_last_summary_uses_last_matching_line():
    text = ("lazy probe: summary sceneEvictions=1\n"
            "noise\n"
            "lazy probe: summary sceneEvictions=7\n")
    assert gate.last_summary(text)["sceneEvictions"] == 7


def test_last_summary_rejects_missing_line():
    with pytest.raises(ValueError):
        gate.last_summary("nothing here")


def test_last_session_slices_after_anchor():
    text = ("old Fast Rendering: v0.9.5\nold\n"
            "Fast Rendering: v0.9.7rc2\nnew\n")
    assert gate.last_session(text).startswith(
        "Fast Rendering: v0.9.7rc2\nnew")


def test_count_texture_errors_counts_all_five():
    text = ("Failed to load texture\nVerifyError\nClassFormatError\n"
            "AsyncException\nisStateCorrupted\n")
    errors = gate.count_texture_errors(text)
    assert errors == {name: 1 for name in gate.TEXTURE_ERRORS}
    assert sum(errors.values()) == 5


def test_summarize_gpu_skips_empty_samples():
    rows = [(0.0, 100.0, None), (1.0, None, None), (2.0, 300.0, 50.0)]
    gpu = gate.summarize_gpu(rows)
    assert gpu["samples"] == 3
    assert gpu["dedicated_mb"] == {"min": 100.0, "median": 200.0, "max": 300.0}
    assert gpu["shared_mb"] == {"min": 50.0, "median": 50.0, "max": 50.0}


def test_build_report_exposes_scene_fields():
    agent = "lazy probe: summary scenePasses=8 sceneEvictions=64 failedParked=0\n"
    starsector = "Fast Rendering: v0.9.7rc2\nFailed to load texture\n"
    report = gate.build_report(agent, starsector)
    assert report["scene_passes"] == 8
    assert report["scene_evictions"] == 64
    assert report["texture_errors_total"] == 1
    assert report["failed_parked"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_m28_scene_gate.py -q`

Expected: FAIL / collection error（`tools/m28_scene_gate.py` 不存在）。

- [ ] **Step 3: 实现 gate 工具**

创建 `tools/m28_scene_gate.py`，完整内容：

```python
#!/usr/bin/env python3
"""M2.8 scene-eviction gate evidence parser.

Reads the last `lazy probe: summary` line from the agent log, the last
Starsector session slice, and an optional GPU sample CSV. Emits JSON so the
control/treatment runs are compared from files, not manual transcription.

Usage:
    python tools/m28_scene_gate.py \
        --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
        --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
        --gpu-csv build/m28/gpu-treatment.csv \
        --require-scene --strict --out build/m28/treatment.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

SUMMARY_MARKER = "lazy probe: summary"
SESSION_ANCHOR = "Fast Rendering: v0.9."
TEXTURE_ERRORS = (
    "Failed to load texture",
    "VerifyError",
    "ClassFormatError",
    "AsyncException",
    "isStateCorrupted",
)
_KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")


def parse_summary_line(line: str) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for key, value in _KEY_VALUE.findall(line):
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = value
    return out


def last_summary(text: str) -> dict[str, int | str]:
    lines = [line for line in text.splitlines() if SUMMARY_MARKER in line]
    if not lines:
        raise ValueError("no lazy probe summary line in agent log")
    return parse_summary_line(lines[-1])


def last_session(text: str, anchor: str = SESSION_ANCHOR) -> str:
    idx = text.rfind(anchor)
    return text if idx < 0 else text[idx:]


def count_texture_errors(text: str) -> dict[str, int]:
    return {name: text.count(name) for name in TEXTURE_ERRORS}


def summarize_gpu(
        rows: list[tuple[float, float | None, float | None]]) -> dict:
    dedicated = [r[1] for r in rows if r[1] is not None]
    shared = [r[2] for r in rows if r[2] is not None]

    def stats(values: list[float]) -> dict | None:
        if not values:
            return None
        values = sorted(values)
        mid = len(values) // 2
        median = (values[mid] if len(values) % 2
                  else (values[mid - 1] + values[mid]) / 2)
        return {
            "min": round(values[0], 1),
            "median": round(median, 1),
            "max": round(values[-1], 1),
        }

    return {
        "samples": len(rows),
        "dedicated_mb": stats(dedicated),
        "shared_mb": stats(shared),
    }


def read_gpu_csv(
        path: Path) -> list[tuple[float, float | None, float | None]]:
    rows: list[tuple[float, float | None, float | None]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                ts = float(row.get("timestamp", ""))
            except (TypeError, ValueError):
                continue

            def number(name: str) -> float | None:
                raw = (row.get(name) or "").strip()
                return float(raw) if raw else None

            rows.append((ts, number("dedicated_mb"), number("shared_mb")))
    return rows


def build_report(
        agent_text: str,
        starsector_text: str,
        gpu_rows: list[tuple[float, float | None, float | None]] | None = None,
) -> dict:
    summary = last_summary(agent_text)
    errors = count_texture_errors(last_session(starsector_text))
    report = {
        "summary": summary,
        "texture_errors": errors,
        "texture_errors_total": sum(errors.values()),
        "scene_evictions": summary.get("sceneEvictions", 0),
        "scene_passes": summary.get("scenePasses", 0),
        "failed_parked": summary.get("failedParked", 0),
    }
    if gpu_rows is not None:
        report["gpu"] = summarize_gpu(gpu_rows)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-log", type=Path, required=True)
    parser.add_argument("--starsector-log", type=Path, required=True)
    parser.add_argument("--gpu-csv", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-scene", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    gpu_rows = read_gpu_csv(args.gpu_csv) if args.gpu_csv else None
    report = build_report(
        args.agent_log.read_text(encoding="utf-8", errors="replace"),
        args.starsector_log.read_text(encoding="utf-8", errors="replace"),
        gpu_rows,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.strict:
        if report["texture_errors_total"] > 0 or report["failed_parked"] > 0:
            return 1
        if args.require_scene and report["scene_evictions"] <= 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_m28_scene_gate.py -q`

Expected: 7 passed。

- [ ] **Step 5: 写手动验收清单**

创建 `docs/m28-manual-acceptance.md`，包含以下小节（正文按此结构写，不填实机数字）：

1. **前置**：`bash tools/java/build-mod.sh`；`python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite`；确认 `starsector-core/graphics/hypernova/blank.png` 非空；默认预算 256 MB。
2. **两组开关**：以 `Starsector-098-260mods/Miko_Lite_m27_diag_4m.txt` 为模板，删掉 `-Dhypernova.textures.lazy.eviction.budgetBytes=...` 行，保留 `-Dhypernova.textures.lazy=true`、`-Dhypernova.textures.lazy.dds=true`、`-Dhypernova.textures.lazy.eviction=true` 和已有的 `-javaagent:...hypernova.agent.jar` 行，然后分别保存为：
   - `Miko_Lite_m28_control.txt`：加 `-Dhypernova.textures.lazy.eviction.sceneUnload=false`；
   - `Miko_Lite_m28_treatment.txt`：加 `-Dhypernova.textures.lazy.eviction.sceneUnload=true`。
   用 `LaunchMiko.ps1` 启动对应文件（可照抄 `启动-M27-诊断-4MiB.bat` 的写法，改文件名）。不要设置 `budgetBytes` 诊断属性。
3. **场景**：干净存档/小舰队；战役停留 ≥60 s；进入一场战斗并打 ≥3 min；返回战役。两组尽量同存档、同舰队、同战斗。
4. **记录**：最后一条 `lazy probe: summary`；`sceneUnload`/`scenePasses`/`sceneEvictions`/`sceneEvictMsTotal`/`sceneEvictMsMax`/`scenePending`/`evicted`/`rematerialized`/`failedParked`/`liveBytes`；`starsector.log` 最后 session 的五类纹理错误；战斗第 2 分钟的任务管理器“专用 GPU 内存”（Dedicated GPU memory）读数；主观白块/错位/卡顿。若要做 GPU 曲线，用 `python -I -c "import sys; sys.path.insert(0,'tools'); import smoke_run; print(smoke_run.process_gpu_memory_mb(PID))"` 每 2 s 采样一次，写成 `timestamp,dedicated_mb,shared_mb` CSV（可省略，gate 工具不强制）。
5. **门禁命令**：
   ```bash
   python tools/m28_scene_gate.py \
     --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
     --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
     --out build/m28/treatment.json --require-scene --strict
   ```
   控制组用 `--out build/m28/control.json`，不加 `--require-scene`。
6. **判定**：处理组 `sceneEvictions>0`、`failedParked=0`、五类错误 0、无白块/错位/崩溃、战斗 GPU dedicated 低于控制组；任一失败记录后关闭 scene_unload，回退当前 LRU。

- [ ] **Step 6: 跑全量工具测试**

Run: `python -I -m pytest tests/tools -q`

Expected: 299 baseline + 51 new = 350 passed（以实际为准；记录数字）。

- [ ] **Step 7: Commit**

```bash
git add tools/m28_scene_gate.py tests/tools/test_m28_scene_gate.py \
        docs/m28-manual-acceptance.md
git commit -m "feat(m28): add scene-eviction gate evidence parser"
```

---

## Task 4: 真实战斗门禁、结果文档与回写

> **2026-11-02 用户裁决：跳过本 Task 的实机 gate。** 260mods 生涯大地图
> 移动严重卡顿；用户决定不投入控制/处理两组战斗，M2.8 以代码/测试/构建
> 收尾，默认 off，不宣称显存收益。以下步骤保留为将来环境允许时的可选复跑。

**Files:**
- Create: `docs/m28-results.md`
- Modify: `技术笔记-纹理按需加载.md`（§7 M2.8 状态）
- Modify: `docs/superpowers/plans/2026-11-02-m28-scene-eviction.md`（勾选/记录偏差）

**Interfaces:**
- Consumes: Task 2 的 summary 新键、Task 3 的 gate 工具、用户的控制/处理两组运行。
- Produces: `docs/m28-results.md` 的证据表与裁决；技术笔记 §7 的 M2.8 状态。
- **Dependencies:** Task 3 + 用户实机运行
- **Touches:** `docs/m28-results.md`、`技术笔记-纹理按需加载.md`、`docs/m27-results.md`、本计划文件

---

- [ ] **Step 1: 构建、安装与回归**

Run:

```bash
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
bash tools/java/build-mod.sh
```

Expected: agent 全绿（记录 found/pass/abort）；pytest 全绿（记录 passed）；`build-mod.sh` 输出 OK。

Run:

```bash
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
```

Expected: agent jar 复制到 `mods/hypernova_infinite_engine/jars/`，备份/安装信息正常。

- [ ] **Step 2: 用户跑控制组**

按 `docs/m28-manual-acceptance.md`：`sceneUnload=false`，干净存档/小舰队，战役 → 战斗 ≥3 min → 返回。记录：

- 最后 summary 的 `sceneUnload=0`、`scenePasses=0`、`sceneEvictions=0`；
- 健康字段 `failed=disabled=dimMismatch=failedParked=0`、`main != none`、
  `ddsDisabled`（仅记录，不作 strict 失败条件）；
- 战斗第 2 分钟进程 GPU dedicated；
- 五类纹理错误 0；
- 主观表现。`disabled=1` 表示 lazy fail-open，本组不是有效基线。

Run:

```bash
python tools/m28_scene_gate.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m28/control.json --require-control --strict
```

Expected: exit 0；`scene_evictions=0`、`scene_unload=0`、`scene_passes=0`，
健康字段全 0 且 `main != none`。

- [ ] **Step 3: 用户跑处理组**

同一存档/舰队/战斗，`sceneUnload=true`。记录：

- 最后 summary 的 `sceneUnload=1`、`scenePasses>0`、`sceneEvictions>0`、`sceneEvictMsTotal/Max`、`scenePending`；
- 健康字段 `failed=disabled=dimMismatch=failedParked=0`、`main != none`、
  `ddsDisabled`（仅记录）；
- `evicted` / `rematerialized` / `liveBytes`；
- 战斗第 2 分钟进程 GPU dedicated；
- 五类纹理错误 0；无白块/错位/崩溃；主观卡顿。

Run:

```bash
python tools/m28_scene_gate.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m28/treatment.json --require-scene --strict
```

Expected: exit 0；`scene_evictions>0`、`failed=disabled=dim_mismatch=failed_parked=0`、
`main != none`、`texture_errors_total=0`。

- [ ] **Step 4: 写 `docs/m28-results.md`**

至少包含：

1. **结论**：scene pass 是否触发、淘汰多少、GPU dedicated 控制 vs 处理、是否保留为 experimental/default off 还是回退。
2. **代码变化与测试**：Task 1/2/3 的 commit、测试数字；明确 `scenePasses` 是 chunk 数、`sceneEvictions` 是成功复位数。
3. **实机门禁**：控制/处理两组的 summary 关键字段（含
   `failed`/`disabled`/`dimMismatch`/`failedParked`/`main`/`ddsDisabled`）、
   GPU 读数、错误计数、视觉检查；控制组用 `--require-control`，处理组用
   `--require-scene`，两组都必须通过 lazy 健康门。
4. **成本**：`sceneEvictMsTotal/Max`；说明 `sceneEvictMsMax` 不是帧 P99，>200 ms 由 M4 frame-time probe 复核。
5. **默认 / 回滚**：`scene_unload.enabled=false` 即回当前 LRU；`eviction.enabled=false` 关闭全部淘汰；发行默认未改。
6. **限制**：无全局 Sprite 注册表，无法证明“无人引用”；scene pass 只保护 basic/startup/foreign/近期 touch；战斗纹理若未被 touch 仍有理论风险；W-2/W-3/refcount 仍 residual。
7. **下一步**：保留/回退结论；M4 接手 frame-time probe 与 A→B/stutter。

- [ ] **Step 5: 回写技术笔记 §7**

在 M2.8 行/段落后追加实际状态：`experimental / default off`、控制/处理结果、`sceneEvictions`、GPU 结论、回滚方式。不要写成默认开启或确定收益；如果 GPU 无差异，明确写“无证据支持收益”。

- [ ] **Step 6: 最终检查与 commit**

Run:

```bash
git status --short
git diff --check
```

Expected: 只有本里程碑预期文件；无空白错误。

```bash
git add docs/m28-results.md docs/m28-manual-acceptance.md \
        docs/superpowers/plans/2026-11-02-m28-scene-eviction.md \
        技术笔记-纹理按需加载.md
git commit -m "docs(m28): record scene eviction gate and results"
```

---

## Self-Review

- **Spec coverage:** 配置（Task 1）、保护集（Task 1）、触发/选择/执行/指标（Task 2）、回退默认 off（Task 1/4）、真实进程门禁（Task 4）、单测（Task 1/2）、工具（Task 3）均有任务。
- **Placeholder scan:** 计划无 TBD/TODO 代码；`docs/m28-results.md` 的数字由 Task 4 的实机步骤产生，未预填。
- **Type consistency:** `evictionSceneUnload*` 在 Task 1 的 record 与 Task 2 的 `start()` 一致；`selectSceneVictims` 签名在 Task 2 的测试与实现一致；`shouldRunScenePass` 9 参数在测试与实现一致；gate 工具键名与 Task 2 summary 一致。
- **Review Focus:** 每条 review focus 都有对应测试：触发（`sceneArmsOnlyOnCampaignToCombat`）、保护/grace（`sceneVictimsProtect...`、`sceneGraceProtects...`、`backgroundsAreBasicPath`）、有界（`sceneScheduleTruthTable`、`sceneNextDueCapsChunks`、`sceneVictimsAreLruOrderedAndCapped`）、默认关闭（`sceneScheduleTruthTable` 的 eviction/scene 假值）、配置 fail-open（`LazyTextureConfigTest` 既有 `badConfigDefaultsOff` + 新默认值断言）、实机（Task 4）。
