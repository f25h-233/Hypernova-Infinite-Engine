# M-1f FR 0.9.7rc2 迁移与重新基线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把宿主从 Fast Rendering 0.9.5 升到 0.9.7rc2，修掉 `onApplicationLoad` 线程语义变化导致的必然断言失败，重跑 M-1e 三门禁，并在新宿主上冻结 warm 基线；不追求新功能。

**Architecture:** 运行期模块不再把 `onApplicationLoad` 的构造线程当主线程，而是由 `onGameLoad` / `onNewGame` / 首次 `advance` 显式 `bindMainThread`（volatile，first-wins）；一次性自检从 `onApplicationLoad` 移到首次主线程 `advance`；测量工具把 FR 会话锚点从 `v0.9.5` 改成前缀 `v0.9.`；FR 安装用一个 fail-closed 的小工具完成 jar 替换、SHA-256 校验、备份与回滚，**不碰任何启动档**。260mods 保持 M-1e 的 agent-only 口径（256 mods，不启用运行期 mod），线程绑定在已启用该 mod 的 Base 环境用“读档 + 自检”验证。

**Tech Stack:** Java 17（`--release 17`，class major 61）、Python 3（stdlib）、Git Bash、PowerShell（可选提权清 standby）、Fast Rendering 0.9.7rc2、VramOptimizer 1.0.45、Base Zulu JRE 17.0.10、260mods Temurin 28+13。

**Spec:** `技术笔记-纹理按需加载.md` §7「M-1f FR 0.9.7rc2 迁移 + 重新基线」与 §10.1 ADR-05。计划是论证；规格是权威，冲突时按规格裁决并记入 ledger。

---

## 开工前实测（2026-10-31，controller 亲测，写进 ledger）

### A. 环境事实

| 项 | 实测 |
|---|---|
| 仓库 HEAD | `2a0ffc3`（M-1e 最后提交，`origin/main` 已同步） |
| 当前 FR | 260mods / Base 的 `starsector-core/fr.jar` 均为 **0.9.5**；`fr.version.txt` **不存在**（`fr_install.py status` 的 `version_file=false`），`jar_version()` 回退读 `Version.class` 得到 `v0.9.5` |
| 0.9.7rc2 工件 | `.cache/fr097/fast-rendering-0.9.7rc2/`：`fr.jar` 602,167 B / `fr.agent.jar` 155,591 B / `fr.version.txt`=`v0.9.7rc2` |
| 0.9.7rc2 SHA-256 | `fr.jar`=`5f811d32eaeb4cc359a80ae5bae95c8ee3414d3f3786abb99996afaaa6e16703`；`fr.agent.jar`=`3caea920626d666b275c8352ce1fb2f2393ff26816ec8aab89d705b2673ad7d4` |
| FR 0.9.7 字节码 | `fr.jar` 406 个 class、`fr.agent.jar` 19 个 class，全部 **major 61 / minor 0**；无 `SequencedCollection`/`ofVirtual`/`getFirst`/`Math.clamp` 等 Java 21+ API 命中 |
| 线程语义（E1） | `ResourceLoaderState.initMain` → `initMods()` → `heavyWorker.submit(lambda$initMods$2)`；lambda 内先 `ScriptStore.loadModClasses()`，再对每个 `ModPlugin` 调 `onApplicationLoad()`（`ResourceLoaderState.txt` offset 671–699） |
| Janino loader（E1） | `MultiThreadedJaninoClassLoader` 仍有 `(Ljava/lang/ClassLoader;)V` 构造器、`findClass(Ljava/lang/String;)Ljava/lang/Class;`、私有 `bytecodeCache` 字段；`ScriptCacheTransformer` 的两个描述符不变 |
| VOpt（E1） | `VramOptimizer/VOpt_VERSION.txt` = `VOpt v1.0.45`；`DeCell.VOpt.Commons.Rendering.TextureLoading.UploadDDSTexture(int, byte[])` 存在；FR 0.9.7 `DDSIntegration.initIntegrationHandles()` 反射该方法 |
| VOpt 日志 | FR 的 `Initialized VramOptimizer UploadDDSTexture method.` 是 INFO，被 `mikohime.properties` 的 `com.genir.renderer.overrides.loading=WARN` 过滤；VOpt 写 `Suitable FR Version found, skipping DDS file handling`；失败会抛 `Failed to initialize VRAM Optimizer...`（RuntimeException，崩启动） |
| 260mods 启用列表 | `mods/enabled_mods.json` **256** 个 id，**不含** `hypernova_infinite_engine`；mod 目录缺 `jars/hypernova.jar` 与 `data/config/hypernova/manifest-v1.json` → **M-1e 的口径是 agent-only** |
| Base 启用列表 | 11 个 id，**含** `hypernova_infinite_engine`；`jars/hypernova.jar` 在位；JRE = Zulu **17.0.10**；`saves/` 有存档 |
| 启动档 | `Miko_Lite.txt` 64 行 CRLF，含 `-javaagent:...hypernova.agent.jar`（在 `-javaagent:fr.agent.jar` 之前）；`Miko_Lite_nofr.txt` 已生成；**不改行尾** |
| 工具锚点 | `tools/smoke_run.py:98` 与 `tools/m1b_measure.py:16` 都硬编码 `Fast Rendering: v0.9.5`（需要改前缀） |
| Python 基线 | `python -m pytest tests/tools -q` → **183 passed, 2 failed**；2 个失败是既有 `test_smoke_check.py` 的 stale `b"old"`/`b"new"` 夹具（known/deferred，与 M-1f 无关） |
| Java 基线 | `run-tests.sh` **95/95**；`run-agent-tests.sh` **64 found / 63 successful / 1 aborted / 0 failed** |

### B. 关键裁决（写进 ledger）

- **Ruling M1f-1：260mods 保持 agent-only。** 不把 `hypernova_infinite_engine` 加进 260mods 的 `enabled_mods.json`。理由：M-1e 的 70.1 s 基线、scripts/textures 门禁都是 agent-only 口径；运行期 mod 不影响启动到主菜单。线程绑定改造在 Base（mod 已启用）+ 手动读档验证。
- **Ruling M1f-2：no-FR 臂只重跑 arm A（textures on）。** 260mods 集合未变，arm B 的 30,378 基线是 M-1e 已冻结的同一环境值；若 arm A 不是 0，再补跑 arm B 作为诊断。
- **Ruling M1f-3：基线口径。** warm 3 轮中位数冻结为 M-1f 基线；第一轮因 FR jar 进 `KeyScanner` 指纹必然 scripts cache cold，先跑 1 轮预热，不把预热轮计入基线。

---

## Global Constraints

- Java 编译仍必须 `--release 17`；新增/修改的 Python 工具只用 stdlib、UTF-8，`python -I` 可运行。
- **绝不修改启动档**：`Miko_Lite.txt`、`Miko_Lite_nofr.txt`、`fr.vmparams` 的行尾与内容都不动。FR 安装工具只写 `fr.jar`、`fr.agent.jar`、`fr.version.txt`。
- **VOpt 锁 1.0.45**；不升级到 1.0.46+。
- 不把 `hypernova_infinite_engine` 加进 260mods 的 `enabled_mods.json`（Ruling M1f-1）。
- 同一时间只跑一个游戏实例；每轮开始前 `tasklist | grep -iE "^(java|javaw)\.exe" || echo "no java/javaw process"` 确认无残留（Git Bash 下 `tasklist /FI` 的 `/FI` 会被路径转换，不要用）。
- 杀进程只杀 smoke 自己 spawn 的 PID；**禁止** `taskkill //F //IM node.exe`，也不要用 `taskkill /IM java.exe` 误杀别的 Java 进程。
- 不宣称菜单时间收益；M-1f 的数字只作为**新基线**，不跟 M-1e 的 70.1 s 做“更快/更慢”的归因。
- 不公开 `docs/audit-2026-10-31-coremod-ecosystem.md`（内部证据，未入库）。
- 不提交 FR 第三方 jar；`.cache/` 进 `.gitignore`，哈希记录在 `docs/m1f-results.md`。
- 每个代码任务一个独立 commit；消息前缀 `fix(m1f):` / `feat(m1f):` / `test(m1f):` / `docs(m1f):`，并附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 本计划按 **pipeline** 执行（ledger 首部记录 `Mode: pipeline`）。

## Escape Hatch

- 若计划里的断言数字、测试顺序、文件路径或方法描述与实际实现不符 → **按实际修正并报告**（写进 `task-N-report.md`），无需请示。
- 若需求自相矛盾或无法同时满足 → **停下报告 controller，不许挑一半照做**；写清矛盾原文、为什么不能同时成立、建议裁决。
- Pipeline 下只改本任务 `Touches:` 声明内的文件；需要越界 → 停下报告，等 controller 裁决。
- **0.9.7rc2 失败关闭**：若 260mods 或 Base 在 0.9.7rc2 下无法正常到主菜单、`textures` 静默失效、scripts cache 无法 preload、或其它 mod 崩溃 → **回滚 0.9.5**，保留日志与报告，不强行升级。
- **线程绑定无法自动证明**：菜单冒烟不会调用 `ensureLoaded`。若是 Base 手动读档无法执行（用户不在/存档不兼容）→ 报告“绑定只有单测证据”，不得用菜单轮次冒充真实修复证据。
- **no-FR 臂超时**：`--wait-menu 3600` 仍超时 → 记录日志与进程状态，报告 controller；不得把 arm A 的失败静默降级成“通过”。
- **FR 工件哈希不符**：`fr_install.py` 默认校验 0.9.7rc2 的 SHA-256；不匹配就停，不许 `--no-verify` 绕过（测试夹具除外）。
- **安装非原子（Task 4 review F1）**：若 `install` 在复制第二个 jar 时失败，会留下 `fr.jar=0.9.7rc2` + `fr.agent.jar=0.9.5` 的半状态，工具的备份守卫可能同时挡住重试与回滚。此时**不要重跑 install**；按下面步骤手工恢复，核对哈希，再重新执行 Step 2。半状态不得进入任何冒烟轮次。

```bash
# 0.9.5 的固定哈希（2026-10-31 预检实测）
#   fr.jar       7ee51ee90e914c56fcd262087d7d65e712e767df2b7ba50ccf300afd4e742a29
#   fr.agent.jar 8b9c787134899e2027ca6023099838a11992de4c8aaab7974a3de1dda88f59a2
cp Starsector-098-260mods/starsector-core/fr.jar.bak-hypernova-v0.9.5 \
   Starsector-098-260mods/starsector-core/fr.jar
cp Starsector-098-260mods/starsector-core/fr.agent.jar.bak-hypernova-v0.9.5 \
   Starsector-098-260mods/starsector-core/fr.agent.jar
rm -f Starsector-098-260mods/starsector-core/fr.version.txt   # 0.9.5 原本没有版本文件
sha256sum Starsector-098-260mods/starsector-core/fr.jar \
          Starsector-098-260mods/starsector-core/fr.agent.jar
```

Base 环境同理，把路径换成 `Starsector-098-Base/starsector-core/`。

## Review Focus

1. **假修复：菜单冒烟没碰 `ensureLoaded`。** 0.9.7 的崩溃只会在读档后主线程调用 `ensureLoaded` 时出现；必须有 Base 读档 + `startup_probe_paths=1` 的 `selfcheck` 证据。Task 6 的 manual acceptance 是唯一真实证据。
2. **又在 `onApplicationLoad` 绑定线程。** `new TextureServiceImpl(...)` 不得再接收 `Thread.currentThread()`；`onApplicationLoad` 在 0.9.7 是 `Thread-N-FR-Main-Loader`。Task 1/2 的单测 + `AssemblyWiringTest` 静态守护。
3. **自检跑在绑定之前/错误线程。** `advance` 必须先 `bindMainThread`，再跑 `sharedStartupSelfCheck`；`Global.LOADING_SAVE=true` 时跳过，下一帧再试。Task 2 的源码断言。
4. **锚点过匹配/欠匹配。** `Fast Rendering: v0.9.` 必须同时匹配 `v0.9.5` 与 `v0.9.7rc2`，且 no-FR 日志仍然不匹配。Task 3 的两个 Python 测试。
5. **安装器碰了启动档或覆盖了唯一备份。** `fr_install.py` 只写 3 个文件；备份名带旧版本；同内容幂等，不同内容拒绝覆盖。Task 4 的测试。
6. **静默失效被当成通过。** `bytecodeCache field not found; scripts cache disabled`、`textures: TextureData sha mismatch`、`Failed to initialize VRAM Optimizer` 任一出现都必须让门禁失败。Task 5 的 grep 清单。
7. **冷/热口径混淆。** FR jar 进 key → 第一轮必然 cold；基线只用预热后的 3 轮 warm。Task 5 先预热再测量。

## File Structure

| 路径 | 责任 | 任务 |
|---|---|---|
| `src/main/java/hypernova/texture/TextureService.java` | 新增 `bindMainThread(Thread) -> boolean` 契约 | 1 |
| `src/main/java/hypernova/texture/TextureServiceImpl.java` | 去掉构造器线程；volatile 绑定；未绑定失败关闭 | 1 |
| `tests/java/hypernova/texture/TextureServiceImplTest.java` | 绑定/未绑定/first-wins/错误线程测试 | 1 |
| `tests/java/hypernova/scheduler/FrameBudgetSchedulerTest.java` | Stub 补 `bindMainThread` | 1 |
| `tests/java/hypernova/hooks/RemainingHooksTest.java` | Stub 补 `bindMainThread` | 1 |
| `src/main/java/hypernova/HypernovaPlugin.java` | 4 参调用（Task 1，仅此一处）；onGameLoad/onNewGame 绑定；自检改为 one-shot Runnable（Task 2） | 1/2 |
| `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java` | install 注入 service/self-check；advance 先绑定再跑自检 | 2 |
| `tests/java/hypernova/AssemblyWiringTest.java` | 静态守护：入口绑定、构造不捕获、自检在 advance | 2 |
| `tools/smoke_run.py` | FR 会话锚点改前缀 | 3 |
| `tools/m1b_measure.py` | FR 会话锚点改前缀 | 3 |
| `tests/tools/test_smoke_run.py` | 0.9.5/0.9.7rc2 锚点测试 | 3 |
| `tests/tools/test_m1b_measure.py` | 0.9.7rc2 会话识别测试 | 3 |
| `tools/fr_install.py` | fail-closed 安装/回滚/状态工具，SHA-256 固定 | 4 |
| `tests/tools/test_fr_install.py` | 备份/幂等/校验/回滚/不碰启动档 | 4 |
| `.gitignore` | 忽略本地第三方工件 `.cache/` | 4 |
| `Starsector-098-260mods/**`、`Starsector-098-Base/**` | 安装 FR 0.9.7rc2、构建产物、运行证据 | 5/6 |
| `build/m1f-*.json`、`build/m1f-*.log` | 运行期原始证据（git-ignored） | 5/6 |
| `docs/m1f-results.md` | 迁移、线程绑定、三门禁、基线、回滚 | 7 |
| `技术笔记-纹理按需加载.md` §7/§0.2/§10.1 | M-1f 完成状态、基线数字、下一步 M3 | 7 |

---

### Task 1: TextureService 显式主线程绑定

**Files:**
- Modify: `src/main/java/hypernova/texture/TextureService.java`
- Modify: `src/main/java/hypernova/texture/TextureServiceImpl.java`
- Modify: `src/main/java/hypernova/HypernovaPlugin.java:73-74`（**只改 4 参调用**；其余插件改动归 Task 2）
- Modify: `tests/java/hypernova/texture/TextureServiceImplTest.java`
- Modify: `tests/java/hypernova/scheduler/FrameBudgetSchedulerTest.java`
- Modify: `tests/java/hypernova/hooks/RemainingHooksTest.java`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `TextureService.bindMainThread(Thread thread) -> boolean`（true = 本次建立绑定；false = 已绑定或 `thread == null`）。
  - `TextureServiceImpl(TextureManifest, TextureBackend, Telemetry, BooleanSupplier)`（**4 参**；不再接收线程）。
  - `TextureServiceImpl.ensureLoaded` 在未绑定时抛 `IllegalStateException`，并写 `rejected|path|main-thread-unbound:<thread>` 遥测。

**Dependencies:** 无。
**Touches:** `src/main/java/hypernova/texture/TextureService.java`、`src/main/java/hypernova/texture/TextureServiceImpl.java`、`src/main/java/hypernova/HypernovaPlugin.java`（**仅 4 参调用这一处**）、`tests/java/hypernova/texture/TextureServiceImplTest.java`、`tests/java/hypernova/scheduler/FrameBudgetSchedulerTest.java`、`tests/java/hypernova/hooks/RemainingHooksTest.java`。

> **Ruling M1f-4（2026-10-31，controller）**：`run-tests.sh` 先编译全部 `src/main/java`，所以 4 参构造器一旦落地，`HypernovaPlugin.java:73-74` 的 5 参调用必须先改，否则整个套件 0 测试执行。Task 1 的 Touches 因此扩到该文件，但**只允许**改这一处调用；`onGameLoad`/`onNewGame` 绑定、自检延后等仍归 Task 2。

- [ ] **Step 1: 写失败测试（TextureServiceImplTest）**

在 `tests/java/hypernova/texture/TextureServiceImplTest.java` 中，把 helper 改成 4 参构造并在测试线程上绑定：

```java
    private static TextureServiceImpl service(TextureManifest m, TextureBackend b, Telemetry t,
                                             AtomicBoolean loadingSave) {
        TextureServiceImpl s = new TextureServiceImpl(m, b, t, loadingSave::get);
        s.bindMainThread(Thread.currentThread());
        return s;
    }

    private static TextureServiceImpl unbound(TextureManifest m, TextureBackend b, Telemetry t) {
        return new TextureServiceImpl(m, b, t, () -> false);
    }
```

追加四个测试：

```java
    @Test
    void unboundServiceRejectsLoads() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = unbound(manifestWith("a.png"), b, t);
        assertThrows(IllegalStateException.class, () -> s.ensureLoaded("a.png"));
        assertTrue(b.calls.isEmpty());
        assertTrue(t.events.stream().anyMatch(e -> e.startsWith("rejected|a.png|main-thread-unbound:")));
    }

    @Test
    void bindMainThreadReturnsTrueOnceAndIsFirstWins() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = unbound(manifestWith("a.png"), b, t);
        Thread other = new Thread(() -> { });
        assertTrue(s.bindMainThread(other));
        assertFalse(s.bindMainThread(Thread.currentThread()));
        assertThrows(IllegalStateException.class, () -> s.ensureLoaded("a.png"));
        assertTrue(b.calls.isEmpty());
    }

    @Test
    void bindNullIsIgnored() throws JSONException {
        TextureServiceImpl s = unbound(manifestWith("a.png"), new FakeBackend(), new RecordingTelemetry());
        assertFalse(s.bindMainThread(null));
        assertThrows(IllegalStateException.class, () -> s.ensureLoaded("a.png"));
    }

    @Test
    void loadsOnBoundThread() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = unbound(manifestWith("a.png"), b, t);
        assertTrue(s.bindMainThread(Thread.currentThread()));
        assertTrue(s.ensureLoaded("a.png").ok());
        assertEquals(List.of("a.png"), b.calls);
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-tests.sh TextureServiceImplTest`
Expected: 编译失败（`TextureService` 没有 `bindMainThread`，`TextureServiceImpl` 仍是 5 参构造）。

- [ ] **Step 3: 实现接口与实现类**

`src/main/java/hypernova/texture/TextureService.java` 改为：

```java
package hypernova.texture;

import java.util.List;

public interface TextureService {
    /**
     * Bind the display/main thread. Must be called from a known main-thread
     * entrypoint ({@code onGameLoad}, {@code onNewGame}, or the first
     * {@code advance}). FR 0.9.7 runs {@code onApplicationLoad} on a worker
     * thread, so the construction thread must never be captured.
     *
     * @return true if this call established the binding; false if it was
     *         already bound, or {@code thread} is null.
     */
    boolean bindMainThread(Thread thread);

    TextureLoadResult ensureLoaded(String path);

    boolean isLoaded(String path);

    boolean acquire(String path);

    void release(String path);

    boolean unload(String path);

    List<String> drainPending(int max);

    int pendingCount();
}
```

`src/main/java/hypernova/texture/TextureServiceImpl.java` 的字段/构造器/`ensureLoaded` 改为：

```java
    private final TextureManifest manifest;
    private final TextureBackend backend;
    private final Telemetry telemetry;
    private final BooleanSupplier loadingSave;
    private final Set<String> pending = new LinkedHashSet<>();
    private final ConcurrentHashMap<String, Integer> refCounts = new ConcurrentHashMap<>();
    /**
     * Set once by {@link #bindMainThread(Thread)}; never reset. FR 0.9.7 moved
     * {@code onApplicationLoad} to a worker thread, so capturing the
     * construction thread would make every later main-thread call fail.
     */
    private volatile Thread mainThread;

    public TextureServiceImpl(TextureManifest manifest,
                              TextureBackend backend,
                              Telemetry telemetry,
                              BooleanSupplier loadingSave) {
        this.manifest = manifest;
        this.backend = backend;
        this.telemetry = telemetry;
        this.loadingSave = loadingSave;
    }

    @Override
    public synchronized boolean bindMainThread(Thread thread) {
        if (thread == null || mainThread != null) {
            return false;
        }
        mainThread = thread;
        return true;
    }

    @Override
    public TextureLoadResult ensureLoaded(String path) {
        Thread main = mainThread;
        if (main == null) {
            String detail = "main-thread-unbound:" + Thread.currentThread().getName();
            telemetry.event("rejected", path, 0L, detail);
            throw new IllegalStateException(
                    "ensureLoaded requires bindMainThread() first (" + detail + ")");
        }
        if (Thread.currentThread() != main) {
            String detail = "non-main-thread:" + Thread.currentThread().getName();
            telemetry.event("rejected", path, 0L, detail);
            throw new IllegalStateException("ensureLoaded must run on the display thread (" + detail + ")");
        }
        long start = System.nanoTime();
        TextureEntry entry = manifest.lookup(path);
        if (entry == null) {
            telemetry.event("miss", path, System.nanoTime() - start, "not-in-manifest");
            return new TextureLoadResult(false, false, System.nanoTime() - start, TextureState.MISS);
        }
        if (backend.isRegistered(path)) {
            refCounts.putIfAbsent(path, 1);
            telemetry.event("hit", path, System.nanoTime() - start, entry.modId());
            return new TextureLoadResult(true, false, System.nanoTime() - start, TextureState.LIVE);
        }
        if (loadingSave.getAsBoolean()) {
            pending.add(path);
            telemetry.event("queued", path, System.nanoTime() - start, "loading-save");
            return new TextureLoadResult(false, true, System.nanoTime() - start, TextureState.QUEUED);
        }
        boolean ok = loadWithRetry(path, entry);
        long nanos = System.nanoTime() - start;
        return new TextureLoadResult(ok, false, nanos, ok ? TextureState.LIVE : TextureState.FAILED);
    }
```

其余方法（`loadWithRetry`/`isLoaded`/`acquire`/`release`/`unload`/`drainPending`/`pendingCount`）保持原样。

- [ ] **Step 3b: 先改 `HypernovaPlugin` 的构造调用（编译耦合，只此一处）**

`src/main/java/hypernova/HypernovaPlugin.java` 中把：

```java
            service = new TextureServiceImpl(manifest, new GameBackend(settings), telemetry,
                    Thread.currentThread(), () -> Global.LOADING_SAVE);
```

改为：

```java
            service = new TextureServiceImpl(manifest, new GameBackend(settings), telemetry,
                    () -> Global.LOADING_SAVE);
```

**不要**在本步做任何其它插件改动（绑定入口、自检、install 参数都留给 Task 2）。

- [ ] **Step 4: 给两个测试 Stub 补接口方法**

`tests/java/hypernova/scheduler/FrameBudgetSchedulerTest.java` 的 `StubService` 内、`ensureLoaded` 之前加：

```java
        @Override
        public boolean bindMainThread(Thread thread) {
            return false;
        }
```

`tests/java/hypernova/hooks/RemainingHooksTest.java` 的 `StubService` 内同样加：

```java
        @Override
        public boolean bindMainThread(Thread thread) {
            return false;
        }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `bash tools/java/run-tests.sh TextureServiceImplTest`
Expected: PASS（含新增 4 个测试）；再跑 `bash tools/java/run-tests.sh` 全量 → **99/99 或更多，0 failed**（原 95 + 新增）。

- [ ] **Step 6: Commit**

```bash
git add src/main/java/hypernova/texture/TextureService.java \
        src/main/java/hypernova/texture/TextureServiceImpl.java \
        src/main/java/hypernova/HypernovaPlugin.java \
        tests/java/hypernova/texture/TextureServiceImplTest.java \
        tests/java/hypernova/scheduler/FrameBudgetSchedulerTest.java \
        tests/java/hypernova/hooks/RemainingHooksTest.java
git commit -m "fix(m1f): bind the texture service to an explicit main thread

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 入口绑定 + 自检延后到主线程 advance

**Files:**
- Modify: `src/main/java/hypernova/HypernovaPlugin.java`
- Modify: `src/main/java/hypernova/adapter/HypernovaCombatPlugin.java`
- Modify: `tests/java/hypernova/AssemblyWiringTest.java`

**Interfaces:**
- Consumes: Task 1 的 `TextureService.bindMainThread(Thread) -> boolean`；4 参 `TextureServiceImpl` 构造器。
- Produces:
  - `HypernovaCombatPlugin.install(TriggerPoller, PostLoadWarmupHook, SaveLoadGuard, PrefetchScheduler, Telemetry, TextureService, Runnable startupSelfCheck, int heartbeatFrames)`。
  - 日志锚点：`Hypernova init thread: <name>`、`Hypernova main thread bound at onGameLoad: <display thread>`、`Hypernova main thread bound at advance: <display thread>`。

**Dependencies:** Task 1。
**Touches:** `src/main/java/hypernova/HypernovaPlugin.java`、`src/main/java/hypernova/adapter/HypernovaCombatPlugin.java`、`tests/java/hypernova/AssemblyWiringTest.java`。

- [ ] **Step 1: 写失败测试（AssemblyWiringTest）**

在 `tests/java/hypernova/AssemblyWiringTest.java` 末尾追加：

```java
    @Test
    void mainThreadIsBoundFromGameEntrypointsNotApplicationLoad() throws Exception {
        String plugin = read(PLUGIN);
        // FR 0.9.7 moved onApplicationLoad to Thread-N-FR-Main-Loader.
        assertFalse(plugin.contains("Thread.currentThread(), () -> Global.LOADING_SAVE"),
                "TextureServiceImpl must not capture onApplicationLoad's thread");
        assertTrue(plugin.contains("bindMainThread(\"onGameLoad\")"),
                "onGameLoad must bind the main thread");
        assertTrue(plugin.contains("bindMainThread(\"onNewGame\")"),
                "onNewGame must bind the main thread");
        String combat = read(COMBAT);
        assertTrue(combat.contains("bindMainThread(Thread.currentThread())"),
                "first advance must bind the main thread");
        assertTrue(combat.contains("sharedStartupSelfCheck"),
                "the one-shot self-check must run on the main thread");
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-tests.sh AssemblyWiringTest`
Expected: `mainThreadIsBoundFromGameEntrypointsNotApplicationLoad` FAIL（旧源码仍捕获构造线程，且没有绑定入口）。

- [ ] **Step 3: 改 `HypernovaPlugin`**

3a. 在 `onApplicationLoad` 的 `try {` 之后加：

```java
            Global.getLogger(HypernovaPlugin.class).info(
                    "Hypernova init thread: " + Thread.currentThread().getName());
```

3b. 把 service 构造改成 4 参：

```java
            service = new TextureServiceImpl(manifest, new GameBackend(settings), telemetry,
                    () -> Global.LOADING_SAVE);
```

3c. 删除旧的 `if (config.startupProbePaths() > 0) { runFallbackSelfCheck(...); }` 块，改为在 `install` 之前构造 one-shot：

```java
            final int probePaths = config.startupProbePaths();
            Runnable startupSelfCheck = probePaths > 0
                    ? () -> runFallbackSelfCheck(Math.max(1, probePaths))
                    : null;
```

3d. 把 `install` 调用改成：

```java
            HypernovaCombatPlugin.install(poller, warmupHook, saveLoadGuard, scheduler, telemetry,
                    service, startupSelfCheck, config.heartbeatFrames());
```

3e. 把 catch 里的回滚改成：

```java
            HypernovaCombatPlugin.install(null, null, null, null, null, null, null, 0);
```

3f. 在 `onGameLoad` 上方加 helper：

```java
    private void bindMainThread(String where) {
        if (!active || service == null) {
            return;
        }
        Thread thread = Thread.currentThread();
        if (service.bindMainThread(thread)) {
            Global.getLogger(HypernovaPlugin.class).info(
                    "Hypernova main thread bound at " + where + ": " + thread.getName());
        }
    }
```

3g. `onGameLoad` / `onNewGame` 改为：

```java
    @Override
    public void onGameLoad(boolean newGame) {
        bindMainThread("onGameLoad");
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
        attachCampaign();
    }

    @Override
    public void onNewGame() {
        bindMainThread("onNewGame");
        if (active && warmupHook != null) {
            warmupHook.onGameLoaded();
        }
        attachCampaign();
    }
```

3h. `runFallbackSelfCheck` 的 javadoc 补一句：

```java
     * <p>调用点已从 {@code onApplicationLoad} 移到首次主线程 {@code advance}：
     * FR 0.9.7 的 {@code onApplicationLoad} 在 {@code Thread-N-FR-Main-Loader} 上执行，
     * 在那里调用 {@code ensureLoaded} 必然触发主线程断言。
```

- [ ] **Step 4: 改 `HypernovaCombatPlugin`**

4a. 加 import：

```java
import hypernova.texture.TextureService;
```

4b. 静态字段区加：

```java
    private static volatile TextureService sharedService;
    /** One-shot diagnostic, run on the first main-thread advance (may be null). */
    private static volatile Runnable sharedStartupSelfCheck;
```

4c. 实例字段区加：

```java
    private TextureService service;
```

4d. `install` 改为：

```java
    public static void install(TriggerPoller poller, PostLoadWarmupHook warmupHook,
                               SaveLoadGuard saveLoadGuard, PrefetchScheduler scheduler,
                               Telemetry telemetry, TextureService service,
                               Runnable startupSelfCheck, int heartbeatFrames) {
        sharedPoller = poller;
        sharedWarmupHook = warmupHook;
        sharedSaveLoadGuard = saveLoadGuard;
        sharedScheduler = scheduler;
        sharedTelemetry = telemetry;
        sharedService = service;
        sharedStartupSelfCheck = startupSelfCheck;
        sharedHeartbeatFrames = heartbeatFrames;
    }
```

4e. 删除未使用的 5 参构造器（`public HypernovaCombatPlugin(TriggerPoller poller, ...)` 整段）。只保留无参构造器（游戏反射用）。

4f. `advance` 开头改为：

```java
    @Override
    public void advance(float amount, List<InputEventAPI> events) {
        if (!resolve()) {
            return;
        }
        TextureService svc = service;
        if (svc != null && svc.bindMainThread(Thread.currentThread())) {
            com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).info(
                    "Hypernova main thread bound at advance: " + Thread.currentThread().getName());
        }
        Runnable selfCheck = sharedStartupSelfCheck;
        if (selfCheck != null && !com.fs.starfarer.api.Global.LOADING_SAVE) {
            sharedStartupSelfCheck = null;
            try {
                selfCheck.run();
            } catch (Throwable t) {
                com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).error(
                        "startup self-check failed", t);
            }
        }
        // I1：战役态 transient script 与战斗态插件是两个实例、共享同一调度器。
        // 同帧第二个入口不推进管线，否则预算、perTickCap 与 flush 节流全部按 2 倍速消耗。
        if (!GATE.shouldRun(scheduler, scheduler.stats().ticks(), System.nanoTime())) {
            return;
        }
        poller.tick();
        warmupHook.tick();
        saveLoadGuard.tick();
        scheduler.tick();
        GATE.completed(scheduler, scheduler.stats().ticks(), System.nanoTime());
        tickCount++;
        int hb = heartbeatFrames;
        if (hb > 0 && tickCount % hb == 1) {
            com.fs.starfarer.api.Global.getLogger(HypernovaCombatPlugin.class).info(
                    "HYPERNOVA_TICK " + tickCount + " " + scheduler.stats());
        }
        if (++framesSinceFlush >= FLUSH_EVERY_FRAMES) {
            framesSinceFlush = 0;
            telemetry.flush();
        }
    }
```

4g. `resolve` 改为：

```java
    private boolean resolve() {
        if (poller != null) {
            return true;
        }
        TriggerPoller p = sharedPoller;
        PostLoadWarmupHook w = sharedWarmupHook;
        SaveLoadGuard g = sharedSaveLoadGuard;
        PrefetchScheduler s = sharedScheduler;
        Telemetry t = sharedTelemetry;
        TextureService svc = sharedService;
        if (p == null || w == null || g == null || s == null || t == null || svc == null) {
            return false;
        }
        poller = p;
        warmupHook = w;
        saveLoadGuard = g;
        scheduler = s;
        telemetry = t;
        service = svc;
        heartbeatFrames = sharedHeartbeatFrames;
        return true;
    }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `bash tools/java/run-tests.sh`
Expected: 全量 PASS（0 failed）。特别确认 `AssemblyWiringTest` 的旧测试（`installHappensAfterActiveTrueAndRollsBackOnFailure`、`saveLoadGuardReceivesAFrameBudget`、`heartbeatFrequencyIsConfigurable`）仍通过。

- [ ] **Step 6: Commit**

```bash
git add src/main/java/hypernova/HypernovaPlugin.java \
        src/main/java/hypernova/adapter/HypernovaCombatPlugin.java \
        tests/java/hypernova/AssemblyWiringTest.java
git commit -m "fix(m1f): bind the main thread from game entrypoints and defer the self-check

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 测量工具接受 FR 0.9.x 前缀锚点

**Files:**
- Modify: `tools/smoke_run.py:98`
- Modify: `tools/m1b_measure.py:16`
- Modify: `tests/tools/test_smoke_run.py`
- Modify: `tests/tools/test_m1b_measure.py`

**Interfaces:**
- Consumes: 无。
- Produces: `smoke_run.SESSION_ANCHOR = b"Fast Rendering: v0.9."`；`m1b_measure.SESSION_ANCHOR = "Fast Rendering: v0.9."`。

**Dependencies:** 无。
**Touches:** `tools/smoke_run.py`、`tools/m1b_measure.py`、`tests/tools/test_smoke_run.py`、`tests/tools/test_m1b_measure.py`。

- [ ] **Step 1: 写失败测试**

`tests/tools/test_smoke_run.py` 末尾加：

```python
def test_session_anchor_accepts_097rc2(tmp_path):
    log = tmp_path / "starsector.log"
    old = b"1000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5\n"
    new = b"2000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.7rc2\n"
    data = old + b"middle\n" + new
    log.write_bytes(data)
    assert smoke.session_offset(log) == data.rfind(smoke.SESSION_ANCHOR)
    assert smoke.session_offset(log) > len(old)
```

`tests/tools/test_m1b_measure.py` 末尾加：

```python
def test_097_anchor_is_recognized(tmp_path):
    log_text = "\n".join([
        "1000 [main] INFO  com.genir.renderer.agent.Agent  - "
        "Fast Rendering: v0.9.7rc2",
        normal_line(1010, "a"),
        menu_line(1100),
    ]) + "\n"
    _, d = run_measure(tmp_path, log_text)
    assert d["fr_present"] is True
    assert d["session_source"] == "anchor"
    assert d["normal_before_menu"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_smoke_run.py tests/tools/test_m1b_measure.py -q`
Expected: 两个新测试 FAIL（旧锚点是完整 `v0.9.5`，`v0.9.7rc2` 不被识别）。

- [ ] **Step 3: 改两个锚点**

`tools/smoke_run.py`：

```python
# Prefix match: FR 0.9.5 logs "v0.9.5", FR 0.9.7rc2 logs "v0.9.7rc2".
# A version-pinned anchor silently stops finding sessions after an FR upgrade.
SESSION_ANCHOR = b"Fast Rendering: v0.9."
```

`tools/m1b_measure.py`：

```python
# Prefix match: FR 0.9.5 logs "v0.9.5", FR 0.9.7rc2 logs "v0.9.7rc2".
# A version-pinned anchor silently stops finding sessions after an FR upgrade.
SESSION_ANCHOR = "Fast Rendering: v0.9."
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_smoke_run.py tests/tools/test_m1b_measure.py -q`
Expected: PASS（含新测试）；再跑 `python -m pytest tests/tools -q` → **185 passed, 2 known failed**（原 183 + 新增 2，2 个既有失败不变）。

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_run.py tools/m1b_measure.py \
        tests/tools/test_smoke_run.py tests/tools/test_m1b_measure.py
git commit -m "fix(m1f): accept FR 0.9.x anchors in the measurement tools

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: FR 0.9.7rc2 安装/回滚工具

**Files:**
- Create: `tools/fr_install.py`
- Create: `tests/tools/test_fr_install.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `fr_install.sha256_file(path: Path) -> str`
  - `fr_install.jar_version(jar: Path) -> str | None`
  - `fr_install.installed_version(game: Path) -> str | None`
  - `fr_install.status(game: Path) -> dict`
  - `fr_install.install(src: Path, game: Path, *, expected=EXPECTED_SHA256, version=EXPECTED_VERSION, dry_run=False) -> dict`
  - `fr_install.rollback(game: Path, *, to_version: str | None = None, dry_run=False) -> dict`
  - `FrInstallError(Exception)`
  - CLI `python -I tools/fr_install.py --game <root> --action {install,rollback,status} [--src ...] [--to ...] [--no-verify] [--dry-run]`

**Dependencies:** 无。
**Touches:** `tools/fr_install.py`、`tests/tools/test_fr_install.py`、`.gitignore`。

- [ ] **Step 1: 写失败测试**

创建 `tests/tools/test_fr_install.py`：

```python
import json
import zipfile
from pathlib import Path

import pytest

import fr_install


def make_jar(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("com/genir/renderer/Version.class", b"\xca\xfe\xba\xbe" + version.encode())


def make_game(tmp_path: Path, version: str = "v0.9.5") -> Path:
    game = tmp_path / "Starsector"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    make_jar(core / "fr.jar", version)
    make_jar(core / "fr.agent.jar", version)
    (core / "fr.version.txt").write_text(version, encoding="utf-8")
    return game


def make_src(tmp_path: Path, version: str = "v0.9.7rc2") -> Path:
    src = tmp_path / "src"
    src.mkdir()
    make_jar(src / "fr.jar", version)
    make_jar(src / "fr.agent.jar", version)
    (src / "fr.version.txt").write_text(version, encoding="utf-8")
    return src


def test_jar_version_reads_baked_string(tmp_path):
    jar = tmp_path / "fr.jar"
    make_jar(jar, "v0.9.7rc2")
    assert fr_install.jar_version(jar) == "v0.9.7rc2"


def test_install_backs_up_and_replaces(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    res = fr_install.install(src, game, expected=None, version=None)
    assert res["old_version"] == "v0.9.5"
    assert res["new_version"] == "v0.9.7rc2"
    core = game / "starsector-core"
    assert (core / "fr.jar.bak-hypernova-v0.9.5").is_file()
    assert (core / "fr.agent.jar.bak-hypernova-v0.9.5").is_file()
    assert fr_install.installed_version(game) == "v0.9.7rc2"


def test_install_is_idempotent(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    fr_install.install(src, game, expected=None, version=None)
    second = fr_install.install(src, game, expected=None, version=None)
    assert second["changed"] is False
    assert second["backups"] == []
    backups = list((game / "starsector-core").glob("fr.jar.bak-hypernova-*"))
    assert len(backups) == 1


def test_install_refuses_missing_target_jar(tmp_path):
    game = tmp_path / "Starsector"
    (game / "starsector-core").mkdir(parents=True)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.install(make_src(tmp_path), game, expected=None, version=None)


def test_install_verifies_pins(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.install(src, game, expected={"fr.jar": "0" * 64}, version=None)


def test_install_does_not_touch_launch_files(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    launch = game / "Miko_Lite.txt"
    vmparams.write_text("-Xmx10g\n", encoding="utf-8")
    launch.write_bytes(b"-javaagent:fr.agent.jar\r\n")
    before = (vmparams.read_bytes(), launch.read_bytes())
    fr_install.install(src, game, expected=None, version=None)
    assert (vmparams.read_bytes(), launch.read_bytes()) == before


def test_rollback_restores_and_preserves_current(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    fr_install.install(src, game, expected=None, version=None)
    res = fr_install.rollback(game, to_version="v0.9.5")
    assert res["from_version"] == "v0.9.7rc2"
    assert res["to_version"] == "v0.9.5"
    assert fr_install.installed_version(game) == "v0.9.5"
    core = game / "starsector-core"
    assert (core / "fr.jar.bak-hypernova-v0.9.7rc2").is_file()


def test_rollback_without_backup_fails(tmp_path):
    game = make_game(tmp_path)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.rollback(game, to_version="v0.9.0")


def test_status_reports_hashes(tmp_path):
    game = make_game(tmp_path)
    data = fr_install.status(game)
    assert data["version"] == "v0.9.5"
    assert data["fr_sha256"]
    assert data["agent_sha256"]


def test_cli_status_returns_json(tmp_path):
    game = make_game(tmp_path)
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "tools" / "fr_install.py"),
         "--game", str(game), "--action", "status"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["version"] == "v0.9.5"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_fr_install.py -q`
Expected: `ModuleNotFoundError` / 导入失败（`tools/fr_install.py` 不存在）。

- [ ] **Step 3: 实现 `tools/fr_install.py`**

```python
#!/usr/bin/env python3
"""Install or roll back a Fast Rendering distribution in a Starsector install.

Only ``fr.jar``, ``fr.agent.jar`` and ``fr.version.txt`` are touched.
``fr.vmparams`` and the launch profiles are never modified: they carry local
memory settings and the Hypernova agent line.

The 0.9.7rc2 pins are recorded below; pass ``--no-verify`` only for synthetic
fixtures. A backup is created as ``<name>.bak-hypernova-<old-version>`` and is
never overwritten with different content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

FR_JAR = "fr.jar"
FR_AGENT = "fr.agent.jar"
FR_VERSION = "fr.version.txt"
CORE = "starsector-core"
VERSION_CLASS = "com/genir/renderer/Version.class"
VERSION_RE = re.compile(rb"v0\.9\.[0-9A-Za-z][0-9A-Za-z.\-]{0,19}")

EXPECTED_VERSION = "v0.9.7rc2"
EXPECTED_SHA256 = {
    FR_JAR: "5f811d32eaeb4cc359a80ae5bae95c8ee3414d3f3786abb99996afaaa6e16703",
    FR_AGENT: "3caea920626d666b275c8352ce1fb2f2393ff26816ec8aab89d705b2673ad7d4",
}


class FrInstallError(Exception):
    """The install/rollback cannot proceed safely."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jar_version(jar: Path) -> str | None:
    """Read the version string baked into com/genir/renderer/Version.class."""
    try:
        with zipfile.ZipFile(jar) as z:
            data = z.read(VERSION_CLASS)
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    m = VERSION_RE.search(data)
    return m.group(0).decode("ascii") if m else None


def installed_version(game: Path) -> str | None:
    core = game / CORE
    version_file = core / FR_VERSION
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text
    return jar_version(core / FR_JAR)


def status(game: Path) -> dict:
    core = game / CORE
    return {
        "game": str(game),
        "core": str(core),
        "version": installed_version(game),
        "version_file": (core / FR_VERSION).is_file(),
        "fr_sha256": sha256_file(core / FR_JAR) if (core / FR_JAR).is_file() else None,
        "agent_sha256": sha256_file(core / FR_AGENT) if (core / FR_AGENT).is_file() else None,
    }


def _validate_source(src: Path, expected: dict[str, str] | None,
                     version: str | None) -> str:
    if not src.is_dir():
        raise FrInstallError(f"source directory not found: {src}")
    for name in (FR_JAR, FR_AGENT):
        if not (src / name).is_file():
            raise FrInstallError(f"source is missing {name}: {src}")
    if expected:
        for name, want in expected.items():
            got = sha256_file(src / name)
            if got != want:
                raise FrInstallError(f"{name} sha256 mismatch: {got} != {want}")
    version_file = src / FR_VERSION
    if version is not None:
        if not version_file.is_file():
            raise FrInstallError(f"source is missing {FR_VERSION}: {src}")
        got = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if got != version:
            raise FrInstallError(f"version mismatch: {got!r} != {version!r}")
    if version is None and version_file.is_file():
        version = version_file.read_text(encoding="utf-8", errors="replace").strip() or None
    return version or "unknown"


def _backup(path: Path, version: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-hypernova-{version}")
    if backup.exists():
        if sha256_file(backup) != sha256_file(path):
            raise FrInstallError(
                f"backup {backup} already exists with different content; refusing to overwrite")
        return backup
    shutil.copy2(path, backup)
    return backup


def install(src: Path, game: Path, *, expected: dict[str, str] | None = EXPECTED_SHA256,
            version: str | None = EXPECTED_VERSION, dry_run: bool = False) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    for name in (FR_JAR, FR_AGENT):
        if not (core / name).is_file():
            raise FrInstallError(
                f"refusing to install into {core}: {name} is missing (not an FR install?)")
    new_version = _validate_source(src, expected, version)
    old_version = installed_version(game) or "unknown"
    backups: list[str] = []
    changed = False
    for name in (FR_JAR, FR_AGENT):
        src_file = src / name
        dst_file = core / name
        if sha256_file(src_file) == sha256_file(dst_file):
            continue
        changed = True
        if dry_run:
            backups.append(str(dst_file.with_name(
                f"{dst_file.name}.bak-hypernova-{old_version}")))
            continue
        backup = _backup(dst_file, old_version)
        if backup is not None:
            backups.append(str(backup))
        shutil.copy2(src_file, dst_file)
    src_version_file = src / FR_VERSION
    if src_version_file.is_file():
        dst_version_file = core / FR_VERSION
        new_text = src_version_file.read_text(encoding="utf-8", errors="replace").strip()
        old_text = (dst_version_file.read_text(encoding="utf-8", errors="replace").strip()
                    if dst_version_file.is_file() else "")
        if new_text != old_text:
            changed = True
            if not dry_run:
                if dst_version_file.is_file():
                    _backup(dst_version_file, old_version)
                shutil.copy2(src_version_file, dst_version_file)
    return {
        "game": str(game),
        "old_version": old_version,
        "new_version": new_version,
        "backups": backups,
        "changed": changed,
        "dry_run": dry_run,
    }


def rollback(game: Path, *, to_version: str | None = None, dry_run: bool = False) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    current = installed_version(game) or "unknown"
    chosen: dict[str, Path] = {}
    for name in (FR_JAR, FR_AGENT):
        if to_version is not None:
            wanted = core / f"{name}.bak-hypernova-{to_version}"
            backups = [wanted] if wanted.is_file() else []
        else:
            backups = [p for p in core.glob(f"{name}.bak-hypernova-*")
                       if p.name != f"{name}.bak-hypernova-{current}"]
            backups.sort(key=lambda p: p.stat().st_mtime)
            backups = backups[-1:]
        if not backups:
            raise FrInstallError(
                f"no rollback backup for {name}"
                + (f" at {to_version}" if to_version else ""))
        chosen[name] = backups[0]
    target_version = to_version
    if target_version is None:
        target_version = chosen[FR_JAR].name.split(f"{FR_JAR}.bak-hypernova-", 1)[1]
    restored: list[str] = []
    for name, backup in chosen.items():
        dst = core / name
        if dry_run:
            restored.append(str(dst))
            continue
        _backup(dst, current)
        shutil.copy2(backup, dst)
        restored.append(str(dst))
    version_file = core / FR_VERSION
    new_text = target_version if target_version and target_version.startswith("v") else ""
    old_text = (version_file.read_text(encoding="utf-8", errors="replace").strip()
                if version_file.is_file() else "")
    if old_text != new_text:
        if not dry_run:
            if version_file.is_file():
                _backup(version_file, current)
            version_file.write_text(new_text, encoding="utf-8")
    return {"game": str(game), "from_version": current, "to_version": target_version,
            "restored": restored, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--src", default=".cache/fr097/fast-rendering-0.9.7rc2")
    ap.add_argument("--action", choices=("install", "rollback", "status"), default="status")
    ap.add_argument("--to", default=None, help="rollback target version, e.g. v0.9.5")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the pinned 0.9.7rc2 sha256/version checks (tests only)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    game = Path(args.game)
    try:
        if args.action == "status":
            data = status(game)
        elif args.action == "install":
            expected = None if args.no_verify else EXPECTED_SHA256
            version = None if args.no_verify else EXPECTED_VERSION
            data = install(Path(args.src), game, expected=expected, version=version,
                           dry_run=args.dry_run)
        else:
            data = rollback(game, to_version=args.to, dry_run=args.dry_run)
    except FrInstallError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 更新 `.gitignore`**

在“构建产物”段之后加：

```gitignore
# ---- 本地第三方工件缓存（FR 0.9.7rc2 等；哈希记录在 docs/m1f-results.md）----
.cache/
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_fr_install.py -q`
Expected: **10 passed**；再跑 `python -m pytest tests/tools -q` → **193 passed, 2 known failed**（183 基线 + 10 新增；2 个既有失败不变）。

- [ ] **Step 6: Commit**

```bash
git add tools/fr_install.py tests/tools/test_fr_install.py .gitignore
git commit -m "feat(m1f): add a fail-closed Fast Rendering installer

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 安装 FR 0.9.7rc2 + 260mods FR-on 门禁与基线

**Files:**
- Runtime: `Starsector-098-260mods/**`、`Starsector-098-Base/**`（git-ignored）
- Evidence: `build/m1f-first.json`、`build/m1f-rounds-warm.json`、`build/m1f-textures*.log/json`
- 无 tracked 源码改动；不改 `enabled_mods.json`

**Interfaces:**
- Consumes: Task 1–4 的构建产物与 `tools/fr_install.py`。
- Produces: `build/m1f-rounds-warm.json`（`menu_s.median` = M-1f 基线）、`build/m1f-textures-measure.json`（`gate_ok=true`）。

**Dependencies:** Task 1、Task 2、Task 3、Task 4。
**Touches:** 仅运行期目录与 `build/`；不改仓库源码。

- [ ] **Step 1: 预检（无残留进程、记录当前版本与启动档哈希）**

Run:

```bash
tasklist | grep -iE "^(java|javaw)\.exe" || echo "no java/javaw process"
python -I tools/fr_install.py --game Starsector-098-260mods --action status
python -I tools/fr_install.py --game Starsector-098-Base --action status
sha256sum Starsector-098-260mods/Miko_Lite.txt Starsector-098-260mods/Miko_Lite_nofr.txt \
  > build/m1f-launch-before.sha256
```

**先把旧日志移走（终审 P1）**：现有 `starsector.log` 含 6（260mods）/ 24（Base）条旧的 `Fast Rendering: v0.9.5` 锚点，以及旧的 VOpt 行；不隔离就会造成 `grep -m1` 假失败/假通过。

```bash
mkdir -p build/m1f-logs
mv Starsector-098-260mods/starsector-core/starsector.log build/m1f-logs/260mods-pre-m1f.log 2>/dev/null || true
mv Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1f-logs/260mods-pre-m1f-agent.log 2>/dev/null || true
mv Starsector-098-Base/starsector-core/starsector.log build/m1f-logs/base-pre-m1f.log 2>/dev/null || true
mv Starsector-098-Base/saves/hypernova/scripts-agent.log build/m1f-logs/base-pre-m1f-agent.log 2>/dev/null || true
```

Expected:
- 没有 `java.exe`/`javaw.exe` 在跑；若有残留，先确认 PID 是目标进程再处理，不得盲杀。
- 两个 `status` 的 `version` = `v0.9.5`，`fr_sha256` 与 0.9.7rc2 不同。
- `build/m1f-launch-before.sha256` 生成；旧日志已移到 `build/m1f-logs/`（保留证据，不删除）。

- [ ] **Step 2: 安装 FR 0.9.7rc2 到两个环境**

Run:

```bash
python -I tools/fr_install.py --game Starsector-098-260mods \
  --src .cache/fr097/fast-rendering-0.9.7rc2 --action install
python -I tools/fr_install.py --game Starsector-098-Base \
  --src .cache/fr097/fast-rendering-0.9.7rc2 --action install
python -I tools/fr_install.py --game Starsector-098-260mods --action status
python -I tools/fr_install.py --game Starsector-098-Base --action status
```

Expected:
- 两个 install 返回 `old_version=v0.9.5`、`new_version=v0.9.7rc2`、`changed=true`，并列出 `fr.jar.bak-hypernova-v0.9.5` / `fr.agent.jar.bak-hypernova-v0.9.5`。
- 两个 status 的 `version=v0.9.7rc2`，`fr_sha256=5f811d32...`，`agent_sha256=3caea920...`。
- 启动档哈希不变：`sha256sum -c build/m1f-launch-before.sha256` → 两行 `OK`。

- [ ] **Step 3: 构建并安装 agent 与 Base 的完整 mod**

Run:

```bash
bash tools/java/build-agent.sh
bash tools/java/build-mod.sh --env 260mods
mkdir -p build/m1f-backup
cp -r Starsector-098-260mods/mods/hypernova_infinite_engine build/m1f-backup/260mods-hypernova-before
cp -r Starsector-098-Base/mods/hypernova_infinite_engine build/m1f-backup/base-hypernova-before
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite \
  --jar build/agent/hypernova.agent.jar
cp -r build/java/hypernova-mod/. Starsector-098-260mods/mods/hypernova_infinite_engine/
bash tools/java/build-mod.sh --env base
cp -r build/java/hypernova-mod/. Starsector-098-Base/mods/hypernova_infinite_engine/
sha256sum -c build/m1f-launch-before.sha256
```

注意：
- **260mods 的 `enabled_mods.json` 不动**（Ruling M1f-1）；上面只是把 mod 文件补齐，保持环境完整，但不启用。
- `install_agent.py` 若报告 `install:`（说明它改了启动档）→ 停下检查行尾；应只看到 `installed:` / `no vmparams change:`。
- `build-mod.sh` 每次会重建 `build/java/hypernova-mod`；260mods 的 `cp` 必须在 `--env base` 重建之前完成（上面的顺序已保证）。

Expected:
- `build/agent/hypernova.agent.jar` 重新生成。
- Base 的 `mods/hypernova_infinite_engine/jars/` 有新的 `hypernova.jar` 与 `hypernova.agent.jar`，`data/config/hypernova/manifest-v1.json` 存在。
- 启动档哈希仍 OK。

- [ ] **Step 4: 第一轮 FR-on 冒烟（预期 scripts cache cold）**

Run:

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --json-out build/m1f-first.json
```

Expected:
- 正常到主菜单（`ok=true`），菜单时间显著高于 warm（scripts cache 因 FR jar 进 key 而 cold）。
- `agent` 字段出现 `preload_cold`（不是 `preload_hit`）；`textures_patched` 出现。
- 进程正常退出（`stop=forced` 可接受）。

随后检查关键行：

```bash
grep -a -m1 "Fast Rendering: v0.9.7rc2" Starsector-098-260mods/starsector-core/starsector.log
grep -a -m2 "Hypernova init thread" Starsector-098-260mods/starsector-core/starsector.log
grep -a -m2 "Hypernova active\|Hypernova disabled" Starsector-098-260mods/starsector-core/starsector.log
grep -a -i "IllegalStateException" Starsector-098-260mods/starsector-core/starsector.log | head
```

> 日志已在 Step 1 移走，本次会话是唯一内容；这里仍用**精确版本** `v0.9.7rc2`，不要用会匹配旧 0.9.5 行的前缀。

Expected:
- `Fast Rendering: v0.9.7rc2`。
- `Hypernova init thread:` 出现（260mods 未启用 mod，可能不出现；这是预期——见 Ruling M1f-1）。
- 无 `IllegalStateException`。
- 若出现 `Hypernova disabled: manifest unavailable` → 检查 Step 3 的 manifest 安装；但 260mods 未启用 mod，此行走不到。

- [ ] **Step 5: warm 3 轮（基线）**

Run:

```bash
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --tag m1f-warm \
  --json-out build/m1f-rounds-warm.json
```

Expected:
- 3/3 `ok=true`（`m1e_rounds` 在任一轮失败时 exit 1）。
- `summary.menu_s.median` 记录为 M-1f 基线；`summary.key_ms.median` 在 ~500 ms 量级。
- 每轮 `agent.preload_hit` 出现（第一轮之后的 scripts cache 已热）。

- [ ] **Step 6: textures 门禁（单独一轮干净日志）**

warm 3 轮的日志可能含多次会话；为了不让 `m1b_measure` 选错会话，先把它们移到 `build/m1f-logs/`，再跑一轮 warm 的 textures 测量：

```bash
mv Starsector-098-260mods/starsector-core/starsector.log build/m1f-logs/260mods-warm3.log 2>/dev/null || true
mv Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1f-logs/260mods-warm3-agent.log 2>/dev/null || true
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --json-out build/m1f-textures-run.json
cp Starsector-098-260mods/starsector-core/starsector.log build/m1f-textures.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1f-textures-agent.log
python -I tools/m1b_measure.py --log build/m1f-textures.log \
  --agent-log build/m1f-textures-agent.log --baseline 30378 \
  --json-out build/m1f-textures-measure.json
```

Expected:
- `build/m1f-textures-run.json` `ok=true`；这一轮是 warm（scripts cache 已热）。
- `build/m1f-textures.log` 只含本次会话。
- exit 0。
- `normal_before_menu=0`、`patched=true`、`mismatch_line=null`、`gate_ok=true`。
- `failed_texture_lines=0`（本字段只在 `--expect-no-fr` 时进门禁，但仍记录）。

- [ ] **Step 7: scripts 与 VOpt 证据**

Run:

```bash
python -I -c "import json; d=json.load(open('build/m1f-first.json')); print(d[0]['agent'].get('preload_cold'))"
grep -a "scripts cache preloaded:\|miss breakdown:" build/m1f-textures-agent.log | tail -6
grep -a "bytecodeCache field not found\|transform failed" build/m1f-textures-agent.log | tail -5
grep -a -m1 "VOpt Loaded" build/m1f-textures.log
grep -a -m1 "Suitable FR Version found" build/m1f-textures.log
grep -a "Failed to initialize VRAM Optimizer" build/m1f-textures.log | head
```

Expected:
- `build/m1f-first.json` 的 `preload_cold` 证明首轮 cold；`build/m1f-textures-agent.log` 的 `preload_hit` 证明 warm 轮（2113 entries / 7–8 ms）。
- `bytecodeCache field not found` 与 `transform failed` **为空**。
- VOpt 出现 `VOpt Loaded` 与 `Suitable FR Version found`；`Failed to initialize VRAM Optimizer` **为空**。
- `Initialized VramOptimizer UploadDDSTexture method.` 是 INFO，被 `mikohime.properties` 的 `com.genir.renderer.overrides.loading=WARN` 过滤；**不要求出现**。反射失败会抛 RuntimeException 崩启动，游戏正常到菜单即为集成成功的证据。
- `script phase ended:` 不是当前 agent 的输出（只存在于 `tools/smoke_run.py` 的解析器），**不作为门禁**。
- 若 scripts 没有 preload 或出现 `bytecodeCache field not found` → **停止，按 Escape Hatch 回滚 0.9.5**。

- [ ] **Step 8: 记录证据（不 commit）**

把 Step 4–7 的 JSON 与 grep 结果写入 `build/m1f-task5-evidence.md`（临时文件，供 Task 7 使用）。本任务 **不 commit**（运行期目录与 `build/` 都是 git-ignored）。

---

### Task 6: no-FR / Java 17 / Base 线程绑定验收

**Files:**
- Runtime: `Starsector-098-260mods/**`、`Starsector-098-Base/**`
- Evidence: `build/m1f-nofr-on*.json/log`、`build/m1f-java-audit.json`、`build/m1f-jre17-*.log`、`build/m1f-base-jre17.json`、`build/m1f-binding*.log`
- 无 tracked 源码改动

**Interfaces:**
- Consumes: Task 5 的 0.9.7rc2 安装与构建产物。
- Produces: no-FR 门禁 `gate_ok=true`；Java 17 审计 `ok=true`；Base 读档日志含 `Hypernova main thread bound at advance: <display thread>` 与 `selfcheck: RESULT ... PASS`，无 `IllegalStateException`；读档后 telemetry 有 `loaded|`/`hit|` 事件。

**Dependencies:** Task 5。
**Touches:** 仅运行期目录与 `build/`。

- [ ] **Step 1: 重新生成 no-FR 档并确认源档不变**

Run:

```bash
python -I tools/m1e_profile.py --src Starsector-098-260mods/Miko_Lite.txt \
  --out Starsector-098-260mods/Miko_Lite_nofr.txt --force
sha256sum -c build/m1f-launch-before.sha256
```

Expected: `Miko_Lite.txt` 仍匹配原哈希；`Miko_Lite_nofr.txt` 生成（移除 `fr.jar` 与 `-javaagent:fr.agent.jar`，保留 Hypernova agent）。

- [ ] **Step 2: no-FR arm A（textures on，约 20 分钟）**

Run:

```bash
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 --wait-menu 3600 \
  --jvm-arg=-Dhypernova.textures=true --json-out build/m1f-nofr-on.json
```

Expected: 正常到主菜单（约 1,200–1,400 s）；`agent.fr_missing` 出现；`agent.textures_patched` 出现；`failed_texture_lines` 为 0。

复制日志（若 `starsector.log` 轮转，按 M-1e 顺序拼接 `.3` 头 + `.log` 尾）：

```bash
ls -l Starsector-098-260mods/starsector-core/starsector.log*
cp Starsector-098-260mods/starsector-core/starsector.log build/m1f-nofr-on.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1f-nofr-on-agent.log
# 仅当发生轮转时改用：
# cat Starsector-098-260mods/starsector-core/starsector.log.3 \
#     Starsector-098-260mods/starsector-core/starsector.log > build/m1f-nofr-on.log
python -I tools/m1b_measure.py --log build/m1f-nofr-on.log \
  --agent-log build/m1f-nofr-on-agent.log --expect-no-fr --normal-metric cleaned \
  --baseline 30378 --json-out build/m1f-nofr-on-measure.json
```

Expected:
- exit 0；`normal_before_menu=0`、`fr_present=false`、`fr_missing_disabled=true`、`failed_texture_lines=0`、`patched=true`、`gate_ok=true`。
- 若 `normal_before_menu` 不是 0 → 先检查 `--normal-metric cleaned` 与日志轮转；仍不为 0 才补跑 arm B（`-Dhypernova.textures=false`）作诊断（Ruling M1f-2）。

- [ ] **Step 3: Java 17 审计与 JRE17 全量**

Run:

```bash
python -I tools/m1e_java_audit.py --classes build/agent/classes --classes build/java/classes \
  --jar build/agent/hypernova.agent.jar --jar build/java/hypernova.jar \
  --source src --json-out build/m1f-java-audit.json
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-agent-tests.sh 2>&1 | tee build/m1f-jre17-agent-tests.log
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-tests.sh 2>&1 | tee build/m1f-jre17-mod-tests.log
```

Expected:
- 审计 `ok=true`、`java21_api_hits=[]`、first-party class major 61。
- agent **64 found / 63 successful / 1 aborted / 0 failed**（symlink assumption abort 可接受）。
- mod **95/95 或更多，0 failed**（新增测试后数量增加）。
- 两个日志首行 `runtime: openjdk version "17.0.10"`。

- [ ] **Step 4: Base + JRE17 + FR 0.9.7rc2 冒烟**

Run:

```bash
python -I tools/smoke_run.py --profile base --rounds 1 --json-out build/m1f-base-jre17.json
```

Expected:
- 正常到主菜单；`starsector-core/starsector.log` 含 `Fast Rendering: v0.9.7rc2`。
- `Hypernova init thread: Thread-...-FR-Main-Loader`（**不是** `main`）——这是 0.9.7 线程语义的直接证据。
- `Hypernova active: ...` 出现；无 `IllegalStateException`。
- 若 Base 在 0.9.7rc2 下无法到主菜单 → **停止，回滚两个环境到 0.9.5**，报告 controller。

**4b. 移走 Base 冒烟日志**，确保手动读档的证据只含本次会话：

```bash
mv Starsector-098-Base/starsector-core/starsector.log build/m1f-logs/base-smoke.log 2>/dev/null || true
mv Starsector-098-Base/saves/hypernova/scripts-agent.log build/m1f-logs/base-smoke-agent.log 2>/dev/null || true
```

- [ ] **Step 5: 手动读档验收（需要用户操作）**

这是唯一真正调用 `ensureLoaded` 的验收，不能省略。

5a. 备份并临时打开自检：

```bash
cp Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json \
  build/m1f-backup/base-hypernova.json.installed
python - <<'PY'
import json, pathlib
p = pathlib.Path("Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["startup_probe_paths"] = 1
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
grep -n "startup_probe_paths" Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
```

5b. **请用户**用 Base 的正常启动方式启动游戏（JRE17 + FR 0.9.7rc2），读一个存档（`Starsector-098-Base/saves/` 下任意一个），进入战役后退出。若该存档因 mod 集合/版本不兼容无法载入，改开一个新战役（`onGameLoad(true)` 同样会绑定主线程并触发首次 `advance` 的自检）；无论读档还是新战役，都必须真正进入战役画面，不能只停在主菜单。

5c. 检查日志：

```bash
grep -a "Fast Rendering: v0.9.\|Hypernova init thread\|Hypernova main thread bound\|Hypernova active" \
  Starsector-098-Base/starsector-core/starsector.log | tail -20
grep -a "selfcheck:" Starsector-098-Base/starsector-core/starsector.log | tail -10
grep -a -i "IllegalStateException" Starsector-098-Base/starsector-core/starsector.log | tail -5
cp Starsector-098-Base/starsector-core/starsector.log build/m1f-binding.log
```

Expected:
- `Hypernova init thread: Thread-...-FR-Main-Loader`。
- `Hypernova main thread bound at advance: <display thread>`（本次实测 `Thread-3`；若首次 advance 早于读档，`onGameLoad` 时已是 first-wins no-op，可能没有 `at onGameLoad` 行）。
- `selfcheck: RESULT 1/1 PASS`（本次在标题画面首次 advance 就 PASS；若 `INCONCLUSIVE`，改为打开一次接触对话框/百科触发预取，再查 `saves/hypernova/scripts-telemetry.jsonl` 的 `loaded|`/`hit|` 事件）。
- 读档后 `saves/hypernova/scripts-telemetry.jsonl` 出现 `loaded|`/`hit|` 事件（本次 **79 条 `ensureLoaded` 命中在 `Thread-3`**）。
- 无 `IllegalStateException`，无 `startup self-check failed` 堆栈。

5d. 恢复配置：

```bash
cp build/m1f-backup/base-hypernova.json.installed \
  Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
grep -n "startup_probe_paths" Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
```

Expected: 恢复为 `0`。

- [ ] **Step 6: 记录证据（不 commit）**

把 Step 1–5 的 JSON、grep 结果、手动验收结论写入 `build/m1f-task6-evidence.md`。若手动验收未完成，明确写“只有单测/菜单证据，线程绑定尚未在真实读档路径验证”。

---

### Task 7: 结果文档与规格回写

**Files:**
- Create: `docs/m1f-results.md`
- Modify: `技术笔记-纹理按需加载.md`（§0.2、§7 M-1f、§10.1 ADR-05）

**Interfaces:**
- Consumes: `build/m1f-rounds-warm.json`、`build/m1f-textures-measure.json`、`build/m1f-nofr-on-measure.json`、`build/m1f-java-audit.json`、`build/m1f-base-jre17.json`、`build/m1f-task5-evidence.md`、`build/m1f-task6-evidence.md`。
- Produces: 冻结的 M-1f 基线数字与 G-01' 绝对目标。

**Dependencies:** Task 5、Task 6。
**Touches:** `docs/m1f-results.md`、`技术笔记-纹理按需加载.md`。

- [ ] **Step 1: 写 `docs/m1f-results.md`**

按以下结构写（数字必须来自 Step 2 的 JSON，**不得手填估计值**）：

```markdown
# M-1f FR 0.9.7rc2 迁移与重新基线结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）；
>      Base（11 mods，含 hypernova）、Zulu JRE 17.0.10
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…，fr.agent.jar SHA-256 3caea920…）

## 1. 结论

| 门禁 | 结果 | 证据 |
|---|---|---|
| FR 0.9.7rc2 到主菜单 | <通过/失败> | `build/m1f-first.json`、`build/m1f-rounds-warm.json` |
| scripts cache preload | <通过/失败> | `build/m1f-textures-agent.log`、`build/m1f-rounds-warm.json` |
| textures patched | <通过/失败> | `build/m1f-textures-measure.json`（`normal_before_menu=0`, `gate_ok=true`） |
| 主线程断言/崩溃 | <通过/失败> | `build/m1f-binding.log`（`Hypernova main thread bound at advance: Thread-3`，无 `IllegalStateException`） |
| VOpt 0.9.7 DDSIntegration | <通过/失败> | `VOpt Loaded` + `Suitable FR Version found`；无 `Failed to initialize VRAM Optimizer` |
| no-FR 臂 | <通过/失败> | `build/m1f-nofr-on-measure.json`（`gate_ok=true`） |
| Java 17 | <通过/失败> | `build/m1f-java-audit.json`、`build/m1f-jre17-*.log`、`build/m1f-base-jre17.json` |

**M-1f 基线：warm 3 轮中位 <X> s**（<min>–<max>；`build/m1f-rounds-warm.json`）。
**G-01' 目标：≤ <0.8X> s**（相对基线下降 ≥20%）。

## 2. 安装与回滚

- 安装：`python -I tools/fr_install.py --game <game> --action install`；只写 `fr.jar`、`fr.agent.jar`、`fr.version.txt`。
- 备份：`fr.jar.bak-hypernova-v0.9.5`、`fr.agent.jar.bak-hypernova-v0.9.5`。
- 启动档未改：`Miko_Lite.txt` / `Miko_Lite_nofr.txt` / `fr.vmparams` SHA-256 前后一致。
- 回滚：`python -I tools/fr_install.py --game <game> --action rollback --to v0.9.5`。

## 3. 线程绑定证据

- 0.9.7 的 `onApplicationLoad` 线程：`Hypernova init thread: Thread-...-FR-Main-Loader`。
- 绑定：`Hypernova main thread bound at advance: Thread-3`（首次 advance 在主菜单；`onGameLoad` 时已 first-wins no-op）。
- 自检：`selfcheck: RESULT 1/1 PASS`（或 `LOADED`）；读档后 telemetry 有 **79 条 `ensureLoaded` 命中在 `Thread-3`**。
- 无 `IllegalStateException` / `ensureLoaded requires bindMainThread`。

## 4. 260mods warm 基线

| 轮 | menu_s | read_bytes_menu | key ms | preload | stop |
|---|---:|---:|---:|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 中位 | | | | | |

- `cache_control` = <none/standby-purged>；不宣称相对 M-1e 的净收益。
- 第一轮预热（scripts cache cold）不计入基线。

## 5. 门禁细节

### 5.1 textures

- `normal_before_menu` = <0>（M-1e 基线 30,378）；`patched=true`；`mismatch_line=null`；`gate_ok=true`。
- `m1b_measure` 的 `menu_s` 是日志 `Playing music` 锚点口径（比 smoke 进程口径可能小 0.3 s 左右），不是差异；基线以 `build/m1f-rounds-warm.json` 的 60.6 s 为准。

### 5.2 scripts

- 首轮 cold：`build/m1f-first.json` 的 `agent.preload_cold`（不是 textures 轮日志）。
- warm 轮：`scripts cache preloaded: entries=2113, bytes=8,781,716, in 7–8 ms`。
- `bytecodeCache field not found` = 0；`transform failed` = 0；`miss breakdown` 稳定（total=11,264）。
- `script phase ended:` 不是当前 agent 的输出，不作为证据。

### 5.3 VOpt

- `VOpt Loaded`；`Suitable FR Version found, skipping DDS file handling`；`Failed to initialize VRAM Optimizer` = 0。
- FR 的 `Initialized VramOptimizer UploadDDSTexture method.` 是 INFO，被 `mikohime.properties` 的
  `com.genir.renderer.overrides.loading=WARN` 过滤，所以日志里看不到；反射失败会抛 RuntimeException 崩启动，
  游戏正常到菜单即为集成成功。

### 5.4 no-FR 臂

- `normal_before_menu=0`；`fr_present=false`；`fr_missing_disabled=true`；`failed_texture_lines=0`；`gate_ok=true`。
- `m1b_measure` 的 `cleaned` 口径只计 `cache/*_normal.png`；本次另有 21 条非 cache 的 `Cleaned buffer` 行，不计入门禁。
- arm B 未重跑：260mods 集合未变，30,378 为 M-1e 冻结的同一环境基线（Ruling M1f-2）。

## 6. Java 17

- 审计 `ok=true`，`java21_api_hits=[]`；agent 64/63/1 abort/0 failed；mod <N>/<N>。
- FR 0.9.7rc2 的 425 个 class 全部 major 61 / minor 0，无 Java 21+ API 命中。
- Base JRE17 + FR 0.9.7rc2 冒烟 <通过/失败>。

## 7. 已知限制

- 0.9.7rc2 是 prerelease；回滚档为 0.9.5。
- 工具锚点前缀是 `Fast Rendering: v0.9.`；FR 升到 v0.10 时需要同步改 `tools/smoke_run.py` 与 `tools/m1b_measure.py`，否则 `session_offset` 返回 0、`fr_present=False`（门禁会 fail-closed，不会误报通过）。
- 菜单冒烟不调用 `ensureLoaded`；线程绑定的真实证据来自 Base 手动读档。
- 260mods 为 agent-only；运行期 mod 的验证在 Base。
- 不宣称菜单时间收益；数字只作为新基线。
- `tests/tools/test_smoke_check.py` 的 2 个既有失败与 M-1f 无关。
```

把 `<...>` 替换为实测值；若某一项失败，按 Escape Hatch 回滚并写明失败原因，**不得把失败写成通过**。

- [ ] **Step 2: 回写规格**

2a. §0.2 的第 7 条之后加：

```markdown
8. **M-1f 已完成（2026-10-31）**：FR 0.9.7rc2 迁移 + 重新基线；warm 3 轮中位 **<X> s** 冻结为 G-01' 基线，目标 ≤ **<0.8X> s**。下一步是 **M3（0–50 s 桶）**。
```

2b. 把 §7 的 `### M-1f FR 0.9.7rc2 迁移 + 重新基线（2026-10-31 立项，M3 前置）` 整节替换为完成版：

```markdown
### M-1f FR 0.9.7rc2 迁移 + 重新基线（已完成，2026-10-31）

- **状态**：**完成**。<一句话结论：三门禁均通过 / 某项失败并已回滚>。
- **目标**：把宿主从 FR 0.9.5 升到 0.9.7rc2，修掉 `onApplicationLoad` 线程语义变化，重跑 M-1e 三门禁并在新宿主上冻结基线。
- **代码改造**：
  1. `TextureServiceImpl` 不再捕获 `onApplicationLoad` 的线程；`bindMainThread` 由 `onGameLoad` / `onNewGame` / 首次 `advance` 显式调用（volatile，first-wins）。
  2. `runFallbackSelfCheck` 移到首次主线程 `advance`（`startup_probe_paths=0` 默认关闭）。
  3. 工具锚点改为前缀 `Fast Rendering: v0.9.`。
  4. VOpt 继续锁 **1.0.45**。
- **实测**：warm 3 轮 **<a> / <b> / <c> s**（中位 **<X> s**）；`textures` `normal_before_menu=0`、`gate_ok=true`；no-FR `gate_ok=true`；Java 17 全绿；VOpt 走 0.9.7 的 `DDSIntegration`；Base 读档 `Hypernova main thread bound at advance: Thread-3`，无断言。
- **出口**：0.9.7rc2 正常到主菜单；`scripts` cache 冷→热；`textures` patched；无主线程断言/崩溃；VOpt 走 0.9.7 的 `DDSIntegration`；M-1e 三门禁重跑；warm 3 轮中位数冻结为 **G-01' 基线 <X> s**。
- **回滚**：`python -I tools/fr_install.py --game <game> --action rollback --to v0.9.5`；启动档未改动。
- **注**：0.9.7rc2 是 prerelease；FR 0.9.7 并行化法线解码后，A−B 时间差会变小，不能把 0.9.5 的 59.2 s / 37 s 窗口直接套用。
```

2c. 在 §10.1 的 ADR-05 行末尾追加：

```markdown
；M-1f 已完成（2026-10-31），warm 中位 **<X> s** 冻结为 G-01' 基线
```

2d. 更新 §7 里程碑顺序行：把 `**M-1f（FR 0.9.7rc2 迁移 + 重新基线，下一个）**` 改为 `**M-1f（FR 0.9.7rc2 迁移 + 重新基线）✔（已完成，2026-10-31）**`，并把 `**M3（0–50 s 桶）**` 标为下一个。

2e. 更新所有 G-01' 的绝对目标引用（`grep -n "56 s\|70.1" 技术笔记-纹理按需加载.md`）：
- G-01 行（§0.1 的验收表）：“若 M-1f 基线为 70.1 s，目标 ≤56 s” → “M-1f 实测基线 **60.6 s**，目标 **≤48.5 s**”。
- REQ-N-01 行：“三次中位数，M-1f 后冻结基线” → “三次中位数；M-1f 基线 **60.6 s**，目标 **≤48.5 s**”。
- 验收表的“首屏时间”行：“目标 ≤56 s @70.1 s” → “目标 **≤48.5 s @60.6 s**”。
- **不要**改 §0.1/§5 里“纯配置上限约 56 s”的历史论述——那是 FR 0.9.5 时代的分析，不是 G-01' 目标。

- [ ] **Step 3: 文档自检**

Run:

```bash
grep -n "M-1f\|G-01'\|<X>\|<a>\|<b>\|<c>" 技术笔记-纹理按需加载.md | head -20
grep -n "<X>\|<a>\|<b>\|<c>\|<N>" docs/m1f-results.md
```

Expected: 文档里没有残留的 `<X>`/`<a>`/`<b>`/`<c>`/`<N>` 占位符（除规格里刻意保留的历史占位）；所有数字与 `build/m1f-*.json` 一致。

- [ ] **Step 4: Commit**

```bash
git add docs/m1f-results.md 技术笔记-纹理按需加载.md \
        docs/superpowers/plans/2026-10-31-m1f-fr097-migration.md
git commit -m "docs(m1f): record the FR 0.9.7rc2 baseline and gates

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 执行顺序与门禁

```
Task 1 (binding API) ─┐
Task 3 (anchor) ──────┤
Task 4 (installer) ───┤
Task 2 (wiring) ──────┘→ Task 5 (FR-on + baseline) → Task 6 (no-FR/J17/Base) → Task 7 (docs)
```

- Task 1/2 是硬前置：不改就升 0.9.7，`onApplicationLoad` 线程断言必然触发。
- Task 5 的停止条件：260mods 或 Base 在 0.9.7rc2 下崩溃 / textures 静默失效 / scripts preload 失败 → 回滚 0.9.5，保留报告。
- Task 6 的手动读档是线程绑定唯一真实证据；未完成时必须如实标注。
- Task 7 的数字必须来自 JSON；任何失败都要写成失败。
