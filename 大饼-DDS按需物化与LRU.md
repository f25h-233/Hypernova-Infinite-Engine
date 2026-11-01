# 大饼：DDS 按需物化 + 有界 LRU（M2.6 方向）

> 状态：**M2.6 已实现并收口（2026-11-01，experimental / 默认 off）；M2.7 代码侧 default-on
> gates 已关闭（2026-11-02，`2d17977`/`ae56ac8`/`e828055`/`37899bf`/`bc886c8`/`40dd39c`/
> `196e090`/`7de2cc6`/`8e6be81`），默认仍 off；战斗/读档/分辨率/手动、A→B、stutter
> 仍 user gates**。计划为 `docs/superpowers/plans/2026-11-01-m26-dds-lru.md`（M2.6）与
> `docs/superpowers/plans/2026-11-02-m27-default-on-readiness.md`（M2.7）；结果
> `docs/m26-results.md`、`docs/m27-results.md`；用户清单 `docs/m27-manual-acceptance.md`。
> 剩余 gates：refcount/第三方 id（residual）、W-2（user gate）、战斗/读档/分辨率/手动、
> A→B 长会话净 VRAM、>200 ms stutter。
> 战斗/读档/手动目检与 A→B 长会话净 VRAM **仍 pending user**。
> 关联：`docs/m25-results.md`、`技术笔记-纹理按需加载.md` §5.7/§7（M2.5/M2.6/M2.7）、REQ-R1-10、REQ-R2-01/02、INV-08/10、ADR-02/05 补记 6。
> 前置：M2.5 的跳过 / 代理 / drain / path cache / F3 已落地（默认 off）。

## 一、要解决的问题

M2.5 已经能跳过 45,784 个非 L1 启动纹理，但按需物化走的是 **PNG（RGBA8，4 B/px）**，而且**没有淘汰**：

1. 菜单时刻的内存下降（GPU 约 −421 MB、WS 约 −199 MB）会随会话推进被吃掉——60 s 菜单停留已见 WS +219.5 MB、materialized 76→94。
2. 物化的纹理一旦加载就不会卸载；A 场景用过的纹理在 B 场景仍占着显存，长会话/战斗的净收益未知。
3. PNG 的 4 B/px 意味着“全部纹理最终都被用到”时，懒加载的 VRAM 可能**反超** baseline 的 BC7 DDS（1 B/px + mip）。

M2.6 要回答的是：**把按需物化改成 BC7 DDS，并给物化集合加一个有界 LRU，能否让内存收益在战斗/长会话里仍然成立且不卡顿。**

## 二、M2.5 实测依据

| 事实 | 数字 | 来源 |
|---|---|---|
| 启动队列 | 52,604；`wouldSkip` 45,785；`skipped=proxies=45,784` | Task 4 五个 treatment 会话 |
| 菜单时物化 | 85–91（菜单后约 8 s） | Task 4 A/B |
| 菜单后 60 s 物化 | 76（菜单前 3 s）→ 94（菜单 +57…+67 s） | Task 5 `--linger 60` 单轮 |
| 查表需求 | 菜单前 `demandQueued` 798–801 → 会话末 7,322 | Task 1 probe / Task 5 linger |
| 菜单时内存 | GPU 成对中位 −421 MB（5/5）；WS −199 MB（4/5）；free +154 MB（3/5）；45,784 个纹理未上传句柄是这一方向的来源（421 MB 是系统级 GPU 观测，不是逐句柄求和） | Task 4 A/B，n=5，GPU 系统级 |
| 菜单后 60 s | WS +219.5 MB、free −183.7 MB、GPU +107 MB（系统级） | Task 5 linger，单轮，无对照 |
| 淘汰 | **无**；`unloadTexture` 也不调 `glDeleteTextures`（release 不掉显存） | B-fr-pipeline B8/B11 |
| 物化格式 | donor 7 参同步路径 `3553 / 6408`，RGBA8 **4 B/px**，无 mip | Task 2 实现 |
| baseline 格式 | VOpt DDSCache，BC7（DXGI 98 / GL 36492）**1 B/px + mip 链** | B-fr-pipeline B7 |
| 烘焙覆盖 | M2 manifest `coverage.baked=80,286/80,286=1.0`；但 normal（GraphicsLib `cache/*_normal.png`）不在 DDSCache | docs/m2-results.md、docs/m1b-dds-optional.md |
| 需求口径 | 7.3k 是**查表命中的代理**，不是 7.3k 次同步物化；生产只在 bind/miss 时物化 | Task 5 linger |

结论：**M2.5 证明“跳过”结构可行、菜单时刻能省内存；没证明“长期/战斗”净收益，也没证明不卡。** 下一刀必须是 DDS（降低单张成本）+ LRU（给集合封顶），并用战斗/长会话 A/B 验收。

## 三、设计

### 3.1 总览

```
启动期（M2.5 已有）：跳过非 L1 → 代理进 oOoO.new → drain
首次 bind / 查表 miss：
    sidecar 查 absPath + ddsPath
        ├─ DDS 可用且预校验通过 → DDSIntegration.getTexture(absPath)
        │       → commitTexture(TextureData) → BC7 id
        │       → 用 TextureLoader.newVanillaTextureHandler（或等价构造）建真实 Object
        │       → ProxyShape.copy 到代理；写 TextureLoader.ÔO0000
        └─ DDS 缺失/损坏/非 BC7 → PNG donor 同步路径（M2.5 回退）
会话推进：LRU/预算触发 → 只淘汰本组件物化、引用计数 0、非基础集
    → 清 oOoO / TextureLoader 缓存 → FR bridge glDeleteTextures
    → 代理回到占位 id，ready=false；下次 bind re-materialize（重新 glGenTextures，id 不复用）
```

### 3.2 DDS 物化

- **入口**：`DDSIntegration.getTexture(Path absPath)` 查启动期 cache（key = 原图的绝对规范路径）；`DDSIntegration.commitTexture(TextureData)` 做 `glGenTextures` + `manageTexture(target=36492, ...)`，返回 texture id。
- **时序**：`assetLoadingFinished=true` 之后 `manageTexture` 不再登记懒上传回调，而是**立即上传**（worker 读文件 → 下一帧 commit）。因此每次 DDS 物化都是一次真实上传，必须受帧预算/队列约束。
- **真实 Object**：优先复用 FR 自己的 `newVanillaTextureHandler(path, type, texData, id)`（7 参 donor 路径旁边的方法，merge 进 `com.fs.graphics.TextureLoader`），拿到 target=36492、id、尺寸、stringId 都正确的对象；再用 M2.5 的 `ProxyShape.copy(value, proxy)` 把字段拷进代理。不要自己手搓 GL 状态（target/internalformat/parameters 必须与 FR 一致）。
- **BC7 预校验**（必须在提交前，不能依赖 render 线程回退）：
  1. DDS 文件存在、可读、大小 ≥ 148 字节；
  2. DX10 头 magic `DDS ` + `DX10`，`dxgiFormat=98`（BC7）；
  3. 尺寸/层级与 manifest 的 `w/h` 一致；
  4. `getTexture` 返回非 null，`TextureData` 的 `ddsImagePath` 非空。
  任一失败 → 回退 PNG donor 同步路径；记 `ddsFallback` 计数，不抛到游戏。
- **为什么必须预校验**：FR 的 `readTextureBytes` 不校验长度/格式；坏文件会在 render 线程的 `GLCommand` 里抛 `AsyncException` 并把 `isStateCorrupted=true`，属于**不可恢复**（B-fr-pipeline B11.5）。
- **normal 不走 DDS**：GraphicsLib 的 `cache/*_normal.png` 未被 DDSCache 烘焙（M-1b 已核实），normal 继续走 M-1b 的懒法线缓存/PNG 路径。M2.6 的 DDS 收益只覆盖“有 DDS 的普通纹理”，不要把 normal 算进 BC7 收益。

### 3.3 skip v2 sidecar（绝对路径 / ddsPath）

运行时 manifest 已被 `trim_manifest.py` 裁掉 `absolutePath` / `ddsPath` / `mods` / `coverage` / `tiers`（§5.4）。agent 要在运行期调 `DDSIntegration.getTexture(absPath)`，必须知道：

- 每个 skip path 的**绝对源路径**（DDS cache 的 key）；
- 对应 `ddsPath`（可空）或至少一个 `baked` 标志；
- 尺寸（M2.5 已在 skip 文件里带 `w/h`）；
- 生成代/版本（与 runtime manifest 同代；manifest 变了 sidecar 必须重建）。

**方案**：安装器生成 `lazy-skip-v2.txt`（或 JSON sidecar），列：

```
path \t w \t h \t absPath \t ddsPath \t baked
```

- 与 `install_manifest.py` 的 manifest 写盘同代生成（沿用 Task 3 的“manifest 原子写之后、用裁剪后的 runtime”顺序）；两者都带同一 `generation`/hash。
- 运行期只加载 sidecar；缺失/版本不符 → 不做 DDS，回退 M2.5 PNG（fail-open），不阻止启动。
- 绝对路径必须按安装时的真实 mod 根生成；mod 文件夹改名/移动后 sidecar 失效 → 回退 PNG；不要把绝对路径写进运行时 manifest（体积/可移植性）。
- 大小估算：45,784 行 × 约 150–250 B ≈ 7–11 MB；用 gzip/紧凑格式，启动期后台加载（M2.5 skip 索引已经 73,446 行 / 4.4 MB，可复用同一加载线程）。

### 3.4 有界 LRU / 淘汰

- **默认关闭**：`textures.lazy.eviction=false`；即使 M2.6 通过验收也先 experimental。
- **候选集**：只淘汰“本组件物化 + 引用计数 0 + 不属于启动期基础集 + 当前不在可见 UI/战斗 + 自上次场景切换后未被 bind”的代理。**没有全局 Sprite 注册表**（F-08），无法证明“无人引用”；规则必须保守，宁可少删。
- **触发**：场景切换（退出星系 / 战斗结束 / 回主菜单）跑一次；或物化集合超过预算（数量/估算 VRAM）时按 LRU 淘汰到低水位。每次 ≤2 ms，超时中止，下次再试。
- **删除顺序**（任一步失败则放弃，不做半删）：
  1. 从 `oOoO.new` 移除该 path（或替换为代理占位，保证 raw-map 读取者仍拿到非 null）；
  2. 从 `TextureLoader.ÔO0000` 移除；
  3. 经 **FR bridge `glDeleteTextures`** 删除 GL id（必须在游戏主线程录制；bridge 会同步 `TextureManager` 状态为 `DO_NOT_MANAGE`）；
  4. 代理字段回到**共享占位**（1×1，合法 id；不能是已删 id / -1 / 0 悬空），`ready=false`，`lastSource=null`，`reregistered=0`；
  5. 清本组件 LRU/引用计数条目。
- **re-materialize**：下次 bind 或查表 miss 时走 3.2 重新物化；`glGenTextures` 必须重新分配，**id 不复用**（INV-08）。代理对象保持同一引用，旧 Sprite 不需要重新拿对象。
- **id 不复用 + 第三方缓存**：FR 的 `TextureManager.texturesState` 按 id 索引；绕过 bridge 删除会留下 `UNLOADED` 状态错配。任何第三方按 id 缓存（FR 纹理追踪、`OoOO`、mod）都可能持有已删 id；这是 M2.6 最大的正确性风险，需要逐场景 manual visual + id 计数验收。
- **预算参数（草案）**：按“物化集合估算字节”而不是固定张数（不同尺寸差异大）；初始 cap 可设为 baseline 纹理字节的某个比例，默认 off 时不影响。LRU 顺序用“最后一次 bind/创建”的单调时钟。

### 3.5 与 M2.5 代码的衔接

- 复用 `LazyTextures` 的 `PROXIES` / `PROXY_BY_OBJ` / `PENDING` / `drainPending` / `lookup` / `onProxyUse` / `ProxyShape` / `refreshReady`。
- 物化入口从 `syncLoad(path)` 扩展为 `materializeDds(path)` → 失败回退 `syncLoad(path)`；`putPathCache` 不变。
- `ProxyShape.newProxy` 目前硬编码 target=3553/id=0；DDS 物化后通过 `copy` 覆盖为 target=36492/真实 id，不需要改代理构造（但需要 `newVanillaTextureHandler` 的 shape gate）。
- `summary` 增加 `ddsHit / ddsFallback / evicted / rematerialized / materializedBytes` 等计数；不影响既有 `m25_probe`/`m25_ab` 的前缀解析（新增字段放在末尾）。
- F3 的 `refreshReady` 继续负责“真实对象重新注册”的刷新；LRU 淘汰后的占位不走 F3（避免把已删 id 拷回）。

## 四、障碍

| # | 障碍 | 说明 / 缓解 |
|---|---|---|
| 1 | **FR 内部/版本** | `DDSIntegration`、`TextureData`、`newVanillaTextureHandler` 都是 FR 内部结构；0.9.7rc2 之外未验证。shape/version gate + fail-open 回 M2.5 PNG/完全加载；每次 FR 升级重新 javap。 |
| 2 | **绝对路径** | DDS cache key 是原图绝对规范路径；runtime manifest 已 trim。skip v2 sidecar + 同代生成；mod 改名/移动 → sidecar 失效 → PNG 回退；路径大小写/分隔符/symlink 需归一化。 |
| 3 | **normal 不走 DDS** | GraphicsLib `cache/*_normal.png` 未被烘焙（M-1b）；normal 继续 PNG/M-1b 懒缓存。M2.6 的 BC7 收益不能覆盖 normal 的 4 B/px；战斗净收益要分开算。 |
| 4 | **raw-map / F3** | 第三方 mod（Shadowverse/VideoLib 的 `TexReflection`）直接读 `oOoO.new`，绕过 wrapper；代理必须始终在 map 里且非 null。F3 的 re-registration 已修 copy+pathCache；淘汰后要避免把已删 id 刷回代理。 |
| 5 | **stutter** | `assetLoadingFinished=true` 后 DDS 立即上传；`glGenTextures` 同步往返 + 上传命令；批量物化会在少数帧堆叠。必须 worker 预读 DDS + 主线程帧预算（≤2 ms）+ 最多一帧占位；战斗高峰仍需预取触发点，LRU 不是性能方案。 |
| 6 | **id 不复用 / 第三方按 id 缓存** | 删除必须经 FR bridge 并清 `TextureManager` 状态；第三方可能持有旧 id，删除后 bind 会黑块/异常。保守候选集 + 逐场景 manual visual + id 计数不增长门禁。 |
| 7 | **DDS 快照不全** | DDS metadata 是启动期只读快照；未烘焙/运行期生成的纹理没有 DDS。回退 PNG；统计 `ddsFallback`，不要假设 100% 命中。 |
| 8 | **BC7 画质/兼容** | VOpt 烘焙可能有可见伪影；Blacklist（`graphics/ui/bottomright*`）与 POT 逻辑不能碰。A/B 截图 + 保留 PNG 回退。 |
| 9 | **无全局引用证明** | F-08 没有 Sprite 注册表；“无人引用”无法证明。LRU 只能保守（场景切换 + 计数 + 基础集排除），错误淘汰会导致黑块。默认 off，实验特性。 |

## 五、出口标准（若立项）

1. **净 VRAM**：战斗/长会话 A/B 中，treatment 的 GPU/WS **不高于** control（baseline），且菜单后 60 s 的 WS 回涨被 LRU 压住（目标：A→B 场景后 WS 漂移 ≤200 MB）。
2. **不卡顿**：FR sampler 无 >200 ms 卡顿（10 分钟窗口）；本组件单帧 P99 ≤2 ms；战斗高峰不出现可感知的成批同步上传。
3. **id 卫生**：进出星系/战斗 100 次，GL id 数量不增长、无重复/悬空 id；删除后旧 id 不再被 bind；`TextureManager` 无 `UNLOADED` 错配。
4. **DDS 失败可见**：DDS 缺失/坏头/非 BC7/尺寸不符 → PNG 回退，`ddsFallback` 计数可见；无 `AsyncException`/`isStateCorrupted`。
5. **正确性**：菜单/读档/战斗/分辨率切换无白块、错位、缺失；0 `Failed to load texture` / 0 Verify / 0 Class；manual visual 通过。
6. **默认 off / 回滚**：`textures.lazy.eviction=false` 默认；DDS 也可单独关；回滚到 M2.5 PNG 或完全关闭。
7. **文档**：DDS 命中率、BC7 vs PNG 的字节账、A→B 场景的 materialized/evicted 曲线、失败/偏差全部落 `docs/m26-results.md`。

## 六、与现有工作的关系

- **M2.5**（`docs/m25-results.md`）：提供跳过/代理/drain/path cache/F3；M2.6 只替换“物化”和“淘汰”，不改启动跳过结构。
- **M2 manifest**：L1/L2/L3、`w/h`、`baked` 是 sidecar 的输入；`coverage.baked=80,286/80,286` 说明烘焙覆盖够，但 normal 除外。
- **M-1b 法线缓存**：normal 已从启动期 30,378 行降到 0，战斗内按需；M2.6 不重复解决 normal，也不把 normal 算进 DDS 收益。
- **VOpt DDSCache**：baseline 已经启用 VOpt 1.0.45；DDS 文件/BC7 头/148 字节 DX10 头都来自它；M2.6 不重新烘焙。
- **REQ-R1-10（卸载）**：M2.6 的 LRU 是它的实装候选；默认 `eviction=false`、引用计数 0、基础集排除、清两级缓存、`glDeleteTextures`、id 不复用，全部沿用。
- **M2.6 不做的**：不重写 FR、不做 Form C、不改默认、不做 upstream 钩子；不把“菜单时刻收益”说成“启动/战斗收益”。

## 七、建议顺序（若立项）

1. 只读 spike：0.9.7rc2 下 `DDSIntegration.getTexture/commitTexture`/`newVanillaTextureHandler` 的 javap + 小样本 DDS 提交；确认 target 36492 的 Object 字段。
2. skip v2 sidecar 生成器 + 安装器同代校验（不接运行期）。
3. DDS 物化 + PNG 回退（默认 off），Base/260mods 菜单 gate。
4. LRU 只做“场景切换 + 计数 + 基础集排除”的最小版本，默认 off。
5. 战斗/长会话 A/B + id 计数 + manual visual；不过则保持 off 并写限制。
