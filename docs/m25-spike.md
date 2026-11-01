# M2.5 Task 1 — 通用纹理懒加载只读可行性 spike

- 日期：2026-11-01
- BASE：`a8ebb40`（计划提交）
- 宿主：Fast Rendering **0.9.7rc2**（`fr.jar` md5 `30db0f340f993fb8e8360f5762088b69`）、Starsector **0.98a-RC8**
- 环境：Base（启用运行期 mod）与 260mods（agent-only，`hypernova_infinite_engine` 不在 `enabled_mods.json`）
- 结论：**G1/G3/G4 通过，G2 的 demand 项失败 → 按门禁判 NO-GO（收益结构不成立）**；Task 2+ 不应派发，最终由 controller/用户裁决。

---

## 1. 形状表（FR 0.9.7rc2，E1/E2）

调研结论 E1/E2（`.research/findings/E-interception-options.md`）：游戏没有官方的纹理加载器注册/回调扩展点；唯一的加载期 mod 钩子 `ModPlugin.onApplicationLoad()` 在全部 hull/weapon 贴图入队之后才执行。因此“在队列入口观测/跳过”必须发生在引擎层，普通 mod 与 `onApplicationLoad` 都做不到。

### 1.1 为什么 hook 在 `com.fs.graphics.TextureLoader`，而不是 donor

- donor 类 `com/genir/renderer/overrides/loading/textures/TextureLoader` 只作为 `mergeClass` 的**字节码资源**存在，**从不作为类加载**；运行期实际执行的是目标类 `com/fs/graphics/TextureLoader`。
- FR 的 `BytecodeFileTransformer` 对目标类先 `renameMethod("o00000", "loadTexture_vanilla", "(Lcom/fs/graphics/Object;Ljava/lang/String;IIIIZ)Lcom/fs/graphics/Object;")`，再 `mergeClass(donor)`。
- `mergeClass` 前，donor 字节先经 `ConstantFileTransformer.frTransformer`（`Transformations.overrides`）把 `com/genir/renderer/overrides/.../TextureLoader` 重写为 `com/fs/graphics/TextureLoader`；因此 donor 里 `queueImage` 的 `invokedynamic` 实现句柄在合并后指向目标类。
- `MethodCopier.copyMethods` 的判重键是目标类已有的 `name + descriptor`；donor 中同名同 descriptor 的方法被跳过。
- **因此**：agent 在 FR 之前向目标类预置 `lambda$queueImage$0(Ljava/lang/String;Ljava/lang/String;Z)V`，MethodCopier 就会跳过 donor 的同名 lambda；队列 worker 的 `invokedynamic` 解析到我们的方法。这是本计划 hook 的全部依据。

### 1.2 方法 / descriptor / 运行期名

| 来源 | 方法（javap） | descriptor | 运行期行为 |
|---|---|---|---|
| donor | `public void queueImage` | `(Ljava/lang/String;Ljava/lang/String;)V` | merge 进目标类；异步队列入队（type, path） |
| donor | `public void queueImageOptional` | `(Ljava/lang/String;Ljava/lang/String;)V` | merge；失败时可选吞掉 |
| donor | `private void queueImage` | `(Ljava/lang/String;Ljava/lang/String;Z)V` | merge；`knownImages` 去重后提交 worker |
| donor | `private void lambda$queueImage$0` | `(Ljava/lang/String;Ljava/lang/String;Z)V` | **Task 1 预置同名方法顶替**；worker 的 `invokedynamic` 调用点 |
| donor | `private void loadTextureAsync` | `(Ljava/lang/String;Ljava/lang/String;)V` | merge；worker 内解码 + 提交主线程 commit；探针用反射调用它 |
| donor | `private TextureData loadTextureData` | `(Ljava/lang/String;Ljava/lang/String;)L.../TextureData;` | merge；文件读取 / DDS / `ImageIO.read` |
| donor | `private synchronized void commitAndCacheTexture` | `(Ljava/lang/String;Ljava/lang/String;L.../TextureData;)V` | merge；主线程 commit + 注册 |
| donor | `private synchronized int commitTexture` | `(Ljava/lang/String;L.../TextureData;)I` | merge；GL 上传 |
| donor | `private TextureHandler newVanillaTextureHandler` | `(Ljava/lang/String;Ljava/lang/String;L.../TextureData;I)Lcom/fs/graphics/TextureHandler;` | merge；构造 handler |
| donor | `public TextureHandler loadTexture_vanilla` | `(Lcom/fs/graphics/TextureHandler;Ljava/lang/String;IIIIZ)Lcom/fs/graphics/TextureHandler;` | 目标类原 7 参 `o00000` 被 rename 成此名；donor 声明因同名同 descriptor 被跳过，保留原实现 |
| donor | `public TextureHandler TextureLoader_loadTextureSynchronous` | `(Lcom/fs/graphics/TextureHandler;Ljava/lang/String;IIIIZ)Lcom/fs/graphics/TextureHandler;` | merge；同步加载路径（`SettingsAPI.loadTexture` 等） |
| vanilla | `public static com.fs.graphics.Object Ò00000`（`com/fs/graphics/oOoO`） | `(Ljava/lang/String;)Lcom/fs/graphics/Object;` | 唯一全局查表；Task 1 rename 为 `hypernova$getOriginal` + wrapper |
| donor | `public static boolean renderProgress`（`.../overrides/loading/ResourceLoaderState`） | 字段 | merge 进 `com.fs.starfarer.loading.ResourceLoaderState`；探针反射置 true |
| donor | `private java.lang.Thread mainThread`（`.../overrides/loading/FileLoader`） | 字段 | merge 进 `com.fs.util.C`；`initResourceLoading()` 里 `Thread.currentThread()` 写入；未来 FileLoader 级 hook 的线程判据 |

补充事实：

- `queueImage(String,String)` 的第二个参数是 **path**（加入 `knownImages`、用于 commit 缓存键）；第一个参数是 type（日志里常见 `TEXTURE`）。探针日志首个 queue 为 `type=TEXTURE, path=graphics/cursors/cursor_red.png`，与反编译一致。
- `lambda$queueImage$0` 的真实语义：`loadTextureAsync(arg1,arg2)` → `ResourceLoaderState.renderProgress=true`；catch `Throwable` 时若第三参为 true 则 `knownImages.remove(arg2)`，否则 rethrow。探针注入的方法逐条复刻该语义。
- `com.fs.graphics.Object`（vanilla 名 `TextureHandler`）字段映射（0.98a-RC8 javap）：`ö00000`=GL target、`ô00000`=GL texture id（默认 -1）、`ÒO0000`/`Ô00000`=像素 width/height、`oO0000`/`Object`=imageWidth/imageHeight、`for`/`ø00000`=texWidth/texHeight 比例、`int`=path、`Ò00000`=stringId、`Ø00000`=deferred 标志。Task 2 的尺寸/UV 与代理实现以此为准。
- `TextureBuilder.readAndAnalyzeImage(BufferedImage, boolean)`（donor）：`doNotModify=true`（FR Blacklist，`graphics/ui/bottomright*`）时把 width/height 向上取到 2 的幂；`false`（普通路径）直接用原图尺寸。**Task 2 的尺寸/UV 依据**：非 Blacklist 纹理不补 POT，必须使用 manifest 里的真实 `w/h`。
- FileLoader（`com.fs.util.C`）的 `mainThread` 只在 `initResourceLoading()` 设置；它是未来“在输入流层拦截”的候选 hook 点（见 §4.3）。

### 1.3 队列线程模型（与探针相关的部分）

- FR 在 `ResourceLoaderState.initStaticFields()` 建 `textureWorkers`（3 线程）。`queueImage` 在调用线程（加载主线程）执行，把 lambda 提交给 `textureWorkers`。
- worker 执行 `loadTextureAsync`：读文件、DDS 命中或 `ImageIO.read` + `readAndAnalyzeImage`；随后把 commit 任务投到 `mainThreadQueue`。
- 主线程每 333 ms drain 一次 `mainThreadQueue`，执行 GL 上传与 `oOoO.super(path, handler)` 注册。
- `queueImage` 首行 `if (GameState.gameInitialized) return;`——运行期新增纹理不会进入该队列（这是“只影响启动期”的边界）。

---

## 2. 探针设计（只读，不跳过任何加载）

### 2.1 开关与配置

- 仅由 `-Dhypernova.textures.lazy.probe=true` 开启；生产开关 `textures.lazy.enabled` 在 Task 1 不存在、默认 false（R-M25-4）。
- skip 文件：`-Dhypernova.textures.lazy.skipFile=...`，否则从 agent jar 所在 mod 根推导 `data/config/hypernova/lazy-skip-v1.txt`。
- 仅当 `frPresent()` 且 probe=true 时注册 transformer 并启动计数线程；否则零日志、零注册。
- agent 安装行必须在 FR 之前（`install_agent.py` 强制）；若 transformer 看到目标类已存在 `lambda$queueImage$0`（说明 agent 在 FR 之后），不覆盖、记日志、放弃（`existingLambdaIsLeftUntouched`）。

### 2.2 Hook 1：`com/fs/graphics/TextureLoader`

- 预置 `private synthetic lambda$queueImage$0(String,String,Z)V`：
  - 调用 `LazyTextures.queue(loader, type, path)`（计数 + `wouldSkip` 判定）；
  - 成功后调用 `LazyTextures.markRenderProgress()`；
  - catch `Throwable`：第三参 true → `LazyTextures.removeKnown(loader,path)` 并吞掉；否则 rethrow。
- `LazyTextures.queue` 通过反射调用运行期类的 `loadTextureAsync(String,String)`（首次解析后缓存 `Method`），异常解包后原样抛出。
- 关键点：**每个纹理仍然走 `loadTextureAsync`**；探针只加计数与一次反射调用。

### 2.3 Hook 2：`com/fs/graphics/oOoO`

- 按 descriptor `(Ljava/lang/String;)Lcom/fs/graphics/Object;` + `ACC_STATIC` 精确匹配，必须恰好 1 个候选；0 或 >1 → 不改、记日志（当前 0.98a-RC8 为 `public static Ò00000(String)`，唯一）。
- 原方法 rename 为 `hypernova$getOriginal`，新增同名 wrapper：先 `LazyTextures.probeLookup(path)`，再调用原方法并**原样返回**；未命中时调用 `LazyTextures.lookup(path)`（Task 1 恒返回 null，即不代理）。
- 行为等价性：wrapper 对已存在纹理返回同一个 `com.fs.graphics.Object` 引用；对 miss 仍返回 null（Task 1 的 `lookup` 恒 null）。除计数外无副作用。

### 2.4 计数与日志

- `queue`：队列总数；`wouldSkip`：path 在 skip index 中（仅当索引已异步加载）；`lookups`：`oOoO` 查表总次数；`demand`：**distinct skip-set lookup**；`types`：type 分布。
- 索引在 daemon 线程加载（不阻塞加载）；summary 每 10 s + shutdown hook 各写一行；`m25_probe.py` 取最后一个 `premain` 会话的最后一条 summary。
- fail-open：索引缺失/字段缺失/反射失败都只记 ERROR 日志并继续，绝不因探针让游戏崩溃。

---

## 3. 实测

### 3.1 skip 文件生成（`tools/gen_lazy_skip.py`）

| 侧 | candidates | skip | excluded_l1 | invalid | blacklist | duplicate | 行数 | 字节 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 260mods | 73,969 | **73,446** | 31 | 5 | 9 | 478 | 73,446 | 4,427,771 |
| Base | 3,121 | **3,112** | 0 | 0 | 9 | 0 | 3,112 | 146,563 |

与计划 Pre-flight 的预期完全一致（无修正）。

### 3.2 Base 探针（1 轮，warm）

`smoke_run.py --profile base --jvm-arg=-Dhypernova.textures.lazy.probe=true`：

| 指标 | 值 |
|---|---:|
| menu_s | 12.5（基线约 11 s，+1.5 s，在 ±3 s 内） |
| ok | true |
| queue | 2,520 |
| wouldSkip | 2,331 |
| skip_fraction | 0.925 |
| lookups | 8,733 |
| demand | 145（≤ 0.20 × 3,112 = 622，仅作参考） |
| index_paths | 3,112（invalid=0，加载 7 ms） |
| queue_hook / lookup_hook / wired | true / true / true |

日志：`lazy probe: repository lookup hook added to com/fs/graphics/oOoO (method=Ò00000)`、`queue lambda hook added to com/fs/graphics/TextureLoader`、`lambda wired (first queue: type=TEXTURE, path=graphics/cursors/cursor_red.png)`、`loadTextureAsync resolved on com.fs.graphics.TextureLoader`；`starsector.log` 0 个 `VerifyError`/`ClassFormatError`、0 条 `Failed to load texture`；agent 日志 0 条 ERROR。

### 3.3 260mods control/probe（2+2 + 补充 1+1）

| 轮次 | 模式 | menu_s | 备注 |
|---|---|---:|---|
| c1 | control | 83.6 | **冷轮**：file index 全量爬 20,806 ms（CRSIDtest `_gen/__pycache__` 的旧变更）+ scripts cache 新 key 冷启动 |
| p1 | probe | 67.6 | index/cache 已 warm |
| c2 | control | 63.7 | warm |
| p2 | probe | 64.6 | warm |
| c3 | control | 64.6 | warm（协议规定的补充 1+1） |
| p3 | probe | 65.6 | warm |

probe JSON（三份一致）：

| 指标 | p1 | p2 | p3 |
|---|---:|---:|---:|
| queue | 52,604 | 52,604 | 52,604 |
| wouldSkip | 45,785 | 45,785 | 45,785 |
| skip_fraction | 0.8704 | 0.8704 | 0.8704 |
| lookups | 114,938 | 111,197 | 105,439 |
| demand | 21,352 | 21,353 | 21,354 |
| index_paths | 73,446 | 73,446 | 73,446 |
| index_invalid / index_ms | 0 / 57 | 0 / 68 | 0 / 64 |
| queue_hook / lookup_hook / wired | true | true | true |

demand 的时间演化（p1 的 10 s summary 序列，p2/p3 同型）：队列在约 30 s 内到 52,604 后不再增长；demand 在队列结束后才开始上升（3 → 298 → 8,682 → **14,831（主菜单锚点前后）** → 19,283 → 21,350）。p2/p3 在菜单锚点附近的 tick 同样为 14,831，会话末为 21,353/21,354。**补充观察（不替代门禁口径）**：菜单前 demand ≈ 14,831（20.2% × index），菜单后（主线停留/菜单背景）再增约 6.5k。

### 3.4 菜单对照与偏差

- **协议 2+2（c1,c2 vs p1,p2）**：control 中位 73.65 s，probe 中位 66.1 s，差 **−7.55 s**。该数字**不可用**：c1 是冷轮（全量 file index 20.8 s + 新 scripts cache key），是环境状态漂移，不是 probe 开销。
- **补充 1+1（c3 vs p3）**：64.6 vs 65.6，差 **+1.0 s**。
- **全部 warm 轮（c2,c3 vs p2,p3）**：control 中位 64.15 s，probe 中位 65.1 s，差 **+0.95 s**。
- 绝对菜单时间 63.7–83.6 s，高于计划预期的 48–50 s（M3 基线 48.1 s）。可归因于环境/内容漂移：scripts cache key 从旧 `520b…` 变为 `7ee9…`（mod 脚本集变化）、file index 有待处理的 `__pycache__` 变更、运行期 CPU 负载约 65%（msedgewebview2 / cloudmusic / Steam++ 等后台）。跨 boot 只做同 boot 交错对照。
- Escape hatch 记录：
  1. **`LazyTransformTest` 改用 ASM core API**：`build/agent/lib/asm-9.1.jar` 只有 `org/objectweb/asm` + `signature`，**不含 `org.objectweb.asm.tree`**（全仓库与游戏 jar 均无 asm-tree）。原 brief 测试的 tree 代码无法编译；改写为等价的 `ClassReader`+`ClassVisitor`+`MethodVisitor` 断言，5 个测试语义不变（通过）。
  2. **补充 1+1**：按 brief 的 G3 条款，在 2+2 中位差 >1.5 s 且确认 c1 冷轮漂移后补跑 c3/p3。
  3. 两侧 skip 数量与预期一致，无修正。
  4. 无需求矛盾；未改游戏配置、未改 `enabled_mods.json`、未改 ledger/spec/计划。

---

## 4. GO/NO-GO 判定

### 4.1 逐条

- **G1 接线（必须）— PASS**
  - Base 与 260mods 的 probe 会话均有 `queue lambda hook added`、`repository lookup hook added`、`lambda wired`；`summary.queue > 0`。
  - `starsector.log` 无 `VerifyError`/`ClassFormatError`；Base 12.5 s、260mods 63.7–67.6 s 均到主菜单。
- **G2 结构（必须）— FAIL**
  - `skip_fraction = 0.870 ≥ 0.50`（预期 ~0.90）PASS。
  - `demand = 21,352`（p1；p2/p3 为 21,353/21,354）**> 0.20 × 73,446 = 14,689.2** → FAIL。按门禁定义“菜单/加载期确实需要大量非 L1 纹理，按需补加载会把收益吃回去”。
  - `wouldSkip` 结构与 manifest 相符：queue 52,604，wouldSkip 45,785，并非“只看到部分队列”。
  - 补充：菜单锚点前的 demand 约 14,831，也略高于 14,689；菜单后约 6.5k 的增量属于停留/菜单背景期。该拆分只作诊断，不改变 `m25_probe.py` 的官方口径（最后一条 summary）。
- **G3 中立性（必须）— PASS（warm 对照）**
  - 协议 2+2 的 −7.55 s 由 c1 冷轮解释；warm 补充 1+1 差 +1.0 s；全部 warm 轮差 +0.95 s，均 ≤1.5 s。
- **G4 正确性（必须）— PASS**
  - 6 个 260mods 会话（c1/p1/c2/p2/c3/p3）的 `starsector.log`：0 `VerifyError`/`ClassFormatError`、0 `Failed to load texture`；agent 日志 0 ERROR。
  - Base：0 `VerifyError`/`ClassFormatError`、0 `Failed to load texture`，菜单正常。

### 4.2 裁决建议

**按门禁：NO-GO（收益结构不成立）**，G2 的 demand 超阈值约 45%。G1/G3/G4 的通过只说明“钩子可用且探针中立”，不能抵消 G2。Task 2+ 不应派发。

边界说明（供 controller/用户裁决，不自行扩大范围）：

- demand 的口径是“distinct skip-set lookups”，**不区分查表时纹理是否已 commit、也不区分查表是否返回非 null**。当前实现下许多 `new Sprite(id)` 在 commit 前查表会得到 null（A10：之后注册不会自动恢复已构造的 Sprite）。因此 21,352 可能高估“必须按需补加载”的数量；菜单前 14,831 也仅比阈值高 142（0.2% × index）。
- 若用户希望继续，建议先做一个**只读的细化探针**（不改生产路径）：在 wrapper 里记录“查表返回非 null”的 distinct skip-set 路径数，并按 10 s 窗口输出，以区分“真正被消费”的纹理与“早于 commit 的空查表”。这属于范围扩展，需用户裁决；本 Task 1 不自行修改口径。

### 4.3 若转其它方向（限制与候选）

- **FileLoader hook**：`com.fs.util.C`（FileLoader）合并了 donor 的 `mainThread` 字段，`initResourceLoading()` 记录主线程；`loadInputStream` 是更靠前的入口。缺点是它在解码之前、拿不到 manifest 语义，而且运行期 `loadTexture` 与启动期共用，需要自己做“启动期/运行期”边界。
- **后台预取**：不跳过，只把解码预热到后台线程/更早的时间窗；收益上限受 I/O 与 CPU 限制，不能减少 VRAM。
- **接受 M2 基线**：保留 manifest 数据层与现有 textures normal-cache，不继续 M2.5。

---

## 5. Task 2–5 草案（仅在 GO 后写 addendum；当前 NO-GO，不执行）

> 以下只列验收与边界，完整代码在 `docs/superpowers/plans/2026-11-01-m25-lazy-textures-addendum.md`（GO 后才写；addendum 优先）。

### Task 2：生产跳过 + 代理 + 按需补加载

- 范围：`textures.lazy.enabled`（默认 false）→ 对 skip index 命中的队列路径不调用 `loadTextureAsync`；在 `oOoO` 注册惰性代理（placeholder `Object`，尺寸用 manifest 的真实 `w/h`，非 POT）；首次查表/首次 bind 时在正确线程物化并替换。
- 验收：启动队列的 `loadTextureAsync` 调用数下降 ≥ skip 比例；`new Sprite` 拿到的代理尺寸/UV 正确；菜单、载入存档、战斗、星图四处无空纹理/错位；与 FR 的 DDS/TextureManager 不冲突；`TEXTURE_ALPHA_ADDER` 与 `graphics/ui/bottomright*` 永不跳过；L1 永不跳过。
- 边界：`queueImage` 的 `gameInitialized` 早退；运行期 `loadTexture` 不走本路径；代理物化失败必须 fail-open 到同步加载或保留占位并记日志。

### Task 3：安装集成

- 范围：`install_agent.py` 在安装时由运行时 manifest 生成/刷新 `lazy-skip-v1.txt`；版本不匹配只禁用模块；回滚 = 删除启动文件 agent 行（`--action uninstall`），不写游戏状态。
- 验收：两侧安装幂等；启动文件 agent 行在 FR 之前；卸载后回到 M2 基线；skip 文件缺失/损坏时模块自动关闭而非崩溃。

### Task 4：A/B + VRAM + 正确性

- 范围：同 boot warm 交错 control/probe 2+2（必要时补 1+1）；记录 menu_s、`loadTextureAsync` 次数、VRAM（FR/驱动计数）、失败纹理与异常。
- 验收：warm 中位差 ≤1.5 s；VRAM 降幅与 skip 比例同量级；Base 运行期 mod 正确性（载入/战斗/存档读档）；260mods 菜单冒烟；无新增 `Failed to load texture`。
- 边界：冷轮/全量 file index 轮不得混入 A/B 中位数；环境漂移必须记录。

### Task 5：结果、规格、回滚、记忆、终审

- 范围：回写 spec（REQ-R2-01 指标口径、REQ-R2-03 agent 顺序、R-M25-1..5）、ADR、`MEMORY.md` 与 milestone 文档；记录回滚步骤与残余风险；最终全分支 review。
- 验收：文档与实装一致；回滚演练通过；审查发现全部关闭或有明确 deferred 记录。
