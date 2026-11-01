# M2.6 结果：DDS 按需物化 + 有界 LRU

- 日期：2026-11-01
- 宿主：Starsector **0.98a-RC8** + Fast Rendering **0.9.7rc2**；260mods（agent-only）与 Base（运行期 mod）
- 验证方式：远程桌面 + 自动化菜单锚点（`smoke_run` launchDirect → 主菜单 → `--linger 20` → 强制退出）；本轮没有人工目检
- 状态：**实现完成，experimental / 默认 off**。本文件只覆盖**自动化菜单 A/B + 真实进程 selftest**。
  **战斗/读档/分辨率/手动目检、A→B 长会话净 VRAM、>200 ms 卡顿未测，pending user。**
- 关联：`docs/m25-results.md`（M2.5 基线）、`技术笔记-纹理按需加载.md` §7、`大饼-DDS按需物化与LRU.md`

---

## 1. 结论

1. **Task 0 门禁全部落地**：generation 运行期校验、I2 尺寸、I3 drained、m4 `loadTextureAsync`、null lookup。
   修复后 Lazy 41/41；全量 agent 146 found / 145 pass / 1 known symlink abort / 0 fail；pytest 279 passed。
2. **DDS 路径真实生效**：修后 260mods 菜单 A/B treatment `ddsHit=18–29`（中位 26）、`ddsFallback=2`、
   `ddsDisabled=0`、`ddsDimMismatch=0`；`failed=0`、`disabled=0`（`build/m26/ab-fix.json`）。修前 Task 4
   为 `ddsHit=18–32`（中位 21）；Base `ddsHit=21`（Task 4，本次未重跑）。修后 6 个 A/B 会话 0
   `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError` / 0 `AsyncException` / 0
   `isStateCorrupted`。
3. **修后菜单 A/B（n=3，miko-lite，warm，eviction off）没有明确时间收益**：control 中位 **52.6 s** vs
   treatment **54.6 s**，delta **+2.0 s**，成对差 **+2.5 / +2.0 / −0.5 s**（成对中位 +2.0 s）。+2.0 s
   仍正好落在计划 ≤2 s 的边界上；成对差收窄到 3 s 以内，但同主机跨 run 中位漂移约 4–7 s，且第 1 对
   是明显 warm-up（67.6/70.1 s），因此**既不能确认 +2.0 s 是真实回退，也不能宣称菜单时间不受影响或
   受益**。v2 索引加载（`index=73,447`，后台线程，treatment-only）仍是真实成本；本文件只把 +2.0 s
   记为边界值，不据此下方向性结论。修前表见 §3，修后表见 §3.2。
4. **逐进程 GPU（`gpu_process_dedicated_mb`）方向一致**：修后菜单时 dedicated control **927.0 MB** vs
   treatment **496.6 MB**（3/3 对均为该值），三对差 **−430.4 MB**；系统级 `gpu_menu_mb` 也 3/3 同向
   （−625 / −427 / −439 MB），仅作旁证。修前 Task 4 为 control 804.8–927.0 vs treatment 368.9–496.6 MB。
   该指标是 OS 逐进程快照，不是逐纹理/VRAM 精确账；`ddsBytes` 不含 mip 链，`liveBytes` 是估算值。
5. **Selftest 走通 materialize → evict → re-materialize**：修后默认预算（`build/m26/selftest-fix.json`）
   `selftest=1`、`evicted=1`、`rematerialized=1`、`placeholder=15165`、`evictPasses=0`（默认 256 MB
   预算无压力，符合预期）、`ddsHit=24`、`ddsFallback=2`、0 错误；budget=1 smoke（`fix-auto.json`）另见
   §5：最后 10 s summary `evictPasses=69`（退出时 ≥136）、`evicted=455`、`rematerialized=447`。
   selftest 只淘汰 1 条不可见纹理，**不等价于战斗/A→B 验收**。
6. **LRU 默认 off；自动 trigger 已在真实进程证明**：`fix-auto.json`（budget=1、grace=0、
   sceneDelay=100 ms、selftest=1）最后一条 10 s summary 快照为 `evictPasses=69`（agent log 共
   135 条 `eviction pass`，最后快照后另有 67 条，退出时 **≥136**；forced exit 无 shutdown
   summary）、`evicted=455`、`rematerialized=447`、`selftest=1`、`placeholder=15165`、0 错误
   （`starsector.log` 会话切片扫描见 §6）；菜单 A/B（eviction off）`evicted=0/evictPasses=0` 仍是预期。
   自动 `evictPass` 调度（I-1）已证明；**真实自动 victim（战斗/长会话）仍需用户验收**。
7. **Base gate 通过（Task 4；Task 2 未重跑）**：all gates true；`skipped=proxies=2,330`、`ddsHit=21`、
   `failed=0`、`disabled=0`；进程 GPU dedicated 451.6 vs 274.4 MB；菜单 8.5 vs 6.5 s；0 错误。
8. **默认 off / 回滚不变**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`；
   DDS 仅在 lazy 开启时默认 true；未改任何游戏配置/存档。

---

## 2. 任务链与门禁

- **Task 0（`7fbb9e6` + fix `e5c7fcf`）生命周期门禁**：generation 头（`# generation=<sha256(manifest)>`）运行期
  校验失败即整体禁用 lazy；I2 尺寸不符拒绝 copy 并 fail-open；I3 drain 后禁止再 skip，drain 时 PENDING 非空
  则 fail-open；m4 `loadTextureAsync(String,String)` 形状门禁（F2 后与 sync 形状解耦）；`lookup(null)` 不再
  刷 ERROR。测试：红 37 个编译错误 → Lazy 38/38（fix 后 41/41，含 `LazyGateTest` 8/8）；全量 agent 146
  found / 145 pass / 1 known symlink abort / 0 fail；pytest 279。两侧安装重生成：260mods skip 73,446 行、
  Base 3,112 行，header 均等于 `sha256(manifest-v1.json)`。
- **Task 1（`f2f3625`）skip v2 sidecar**：`path/w/h/absPath/ddsPath/baked` 6 列 + 同代 generation；
  v1/v2 双写，260mods 73,446 / 73,446 行（v2 25,072,701 B），Base 3,112 / 3,112 行（v2 893,198 B）；
  两侧 path 集合与顺序一致，header 均与 manifest 同代；v1 保留 3 列用于回滚；v2 含宿主绝对路径，不打包进
  发行 zip（R-M26-9）。测试：focused pytest 17、Lazy 39/39、full pytest 279、full agent 144 found / 143 pass /
  1 known symlink abort / 0 fail。
- **Task 2（`5d982e4` + fix `d2e1cb9`）BC7 DDS 物化**：`DdsCheck` 预校验（`DDS ` 魔数 + `DX10` 头、`dxgiFormat=98`、
  尺寸、完整 mip 链、`resourceDimension=3`、非 cube、`arraySize=1`、`catch Throwable`）；`DdsBridge` 调
  `DDSIntegration.getTexture/commitTexture` + `newVanillaTextureHandler`（0.9.7rc2 是 private **实例**方法，
  C1 修复 receiver）；`GlBridge` 经 FR bridge `glDeleteTextures`；失败一律回退 PNG，删除只走
  `deleteTextureSafe`（off-main 入 `PENDING_DELETE`，主线程 drain，R-M26-10）。测试：Dds 11/11
  （`DdsCheckTest` 6 + `DdsBridgeTest` 5）、Bridge 6/6、Lazy 46/46；full agent 163 found / 162 pass /
  1 known symlink abort / 0 fail；pytest 279。
- **Task 3（`8d01fe1` + fix `b716f74`）有界 LRU**：默认 off；预算 256 MB / grace 10 s / 场景切换延迟 2 s /
  每次最多 64 条；1×1 透明占位（`graphics/hypernova/blank.png`，70 B）；删除后清 `oOoO`/`TextureLoader`
  缓存、旧 id 不复用；`markStartup` 一次性闩锁把 loading 期物化永久排除在淘汰之外。测试：`LazyEvictionTest`
  6/6（选择/低水位/grace/basic/旧 id/字节/startup；Task 4 加 picker 后 7/7）；Lazy 47/47；full agent
  164 found / 163 pass / 1 known symlink abort / 0 fail；pytest 279。
- **Task 4（`ad16a4d`）真实进程 selftest + 菜单 A/B**：`LazyTextures.runSelfTest`（materialize→evict→
  re-materialize）+ `tools/m26_ab.py`（交错 C/T、归档日志与 smoke JSON、gates）；260mods 3 轮 A/B、selftest
  1 对、Base 1 对。测试：`LazyEviction` 7/7、`test_m26_ab.py` 6 passed、full agent 165 found / 164 pass /
  1 known symlink abort / 0 fail、pytest 287 passed。
- **Task 5（本条 docs commit）**：本文件 + `技术笔记-纹理按需加载.md` §6.1/§7 状态 +
  `大饼-DDS按需物化与LRU.md` 状态行。未改代码/测试/工具，未启动游戏。
- **Task 2 fix（`35fc768` + `01cf3e1`）I-1/I-2**：`maybeRunEviction` 从
  `lookup`/`onProxyUse`/`noteGameState` 确定性触发；真实 `Global.getCurrentState()==COMBAT`
  门禁；部分 pass 重 arm + 空 pass 30 s backoff；`selectVictims`/`evictOne` 只淘汰 `owned=true`
  （DDS/PNG 物化 owned=true，engine-owned 排除）。测试：`LazyEviction` 14/14；full agent 172
  found / 171 pass / 1 known symlink abort / 0 fail；pytest 287 passed。
- **Task 2（本 docs commit）**：修后 budget=1 auto smoke（`build/m26/fix-auto.json`）、默认预算
  selftest（`selftest-fix.json`）、A/B n=3（`ab-fix.json`）；更新本文件 §1/§3/§5/§7/§8、
  `技术笔记` M2.6 状态与 `大饼` 状态行。未启动 manual visual，未改默认值。

---

## 3. 菜单 A/B 原始表（修前 Task 4）

> 修后 A/B（Task 2，`build/m26/ab-fix.json`）见 §3.2；下表为修前 Task 4 原始表，保留用于对比。

协议：260mods（miko-lite）、warm、DDS on、eviction/selftest off、`--linger 20`、3 轮，每轮固定先 C 后 T
（未做 counterbalance），`build/m26/ab-result.json`。Control 只传 `-Dhypernova.textures.lazy=false`；
treatment 传 `-Dhypernova.textures.lazy=true -Dhypernova.textures.lazy.dds=true`。

**顺序偏差（M-2）**：`tools/m26_ab.py` 每轮都是 control 先跑、treatment 第二个跑，因此 treatment 总是
吃到更暖的 OS 文件缓存；该顺序对 treatment 有利，所以 +2.0 s 不会因此被解释成回归，但也不能据此证明
收益，且本轮未做隔轮反转（counterbalance）。

| # | C menu | T menu | C WS | T WS | C GPU proc | T GPU proc | C GPU sys | T GPU sys | ddsHit | ddsFallback | materialized |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 56.6 | 53.6 | 11,185.1 | 10,972.1 | 927.0 | 368.9 | 3,336.0 | 3,083.0 | 18 | 2 | 85 |
| 2 | 47.6 | 54.6 | 11,071.0 | 11,858.8 | 804.8 | 496.6 | 3,473.0 | 3,270.0 | 32 | 2 | 99 |
| 3 | 52.6 | 54.6 | 11,175.0 | 10,956.2 | 927.0 | 496.6 | 3,388.0 | 2,876.0 | 21 | 2 | 88 |

- 单位：menu 为秒；WS/GPU 为 MB。`GPU proc` = `gpu_process_dedicated_mb`（逐进程，菜单时）；
  `GPU sys` = `gpu_menu_mb`（系统级，含桌面/其它进程，只作旁证）。
- **control_median = 52.6 s，treatment_median = 54.6 s，delta_s = +2.0 s；成对差
  `[-3.0, +7.0, +2.0]`，成对中位 +2.0 s**（JSON 原值，未手工调整）。
- 成对 WS 差 = −213.0 / **+787.8** / −218.8 MB，方向不一致，不作为收益/回退口径。
- 逐进程 GPU 成对差 = **−558.1 / −308.2 / −430.4 MB**（3/3 treatment 更低）；系统级成对差 =
  −253.0 / −203.0 / −512.0 MB（3/3 更低，但噪声更大）。
- 退出时逐进程 dedicated 也全部更低（control 959.5 / 964.7 / 959.5 vs treatment 526.3 / 531.5 / 526.3 MB）；
  这仍是菜单锚点会话的收尾快照，不是长会话曲线。

**时间判读：**

- +2.0 s 正好压线（计划目标 |delta| ≤ 2 s）；成对差从 −3 到 +7 s，**没有明确时间收益**。
- 同一主机跨 run 的菜单中位漂移约 4–7 s（Task 4 报告）；本轮的 +2.0 s 与这个量级相同，不能据此下
  回归/收益结论。
- **pre-fix A/B（`build/m26/ab-result-prefix.json`，同一生产路径、selftest off）**：3 轮 control 中位
  56.1 s vs treatment 55.6 s，delta **−0.5 s**，成对 `[-7.0, +0.5, -0.5]`；当时同样使用 25 MB v2 索引
  （`index=73,446`，加载 175/178/170 ms）。第二次采样方向相反，进一步说明噪声主导。
- **v2 索引成本是 treatment-only**：control 的 `start()` 在 lazy 关闭时早退，不读 skip；treatment 每会话在
  后台 `Hypernova-Lazy-Index` 线程加载 25 MB v2，实测 **147–178 ms**（如 agent 日志 14:05:55.894
  `index loaded paths=73446 invalid=0 generation=46d623a3e453 in 147 ms`）。它是真实成本，但在当前噪声下
  既不能解释 +2.0 s，也不能证明被其它收益抵消。

### 3.1 逐进程 GPU 口径（新指标）

- `57b9b0b` 给 `tools/smoke_run.py` 增加 Windows **GPU Process Memory** 采样：`gpu_process_dedicated_mb` /
  `gpu_process_shared_mb`（菜单时）与 `*_exit_mb`（退出时）。M2.6 A/B 的 GPU 结论用 **dedicated 逐进程
  成对差分**，不用系统级单独下结论。
- 这是 **OS 的逐进程快照**，不是逐纹理/VRAM 精确计量：它包含进程内所有 GPU 分配，无法归因到某个纹理；
  采样点是菜单时/退出时，不是连续 trace。
- 配套字节账同样是估算：`ddsBytes = w*h`（BC7 level-0 1 B/px，**不含 mip 链**；完整链约为 level-0 的
  4/3，所以这是低估）；`liveBytes` 是各代理 `bytes` 的累计估算；`evictedBytes` 同样按 1 B/px 估算，不是
  VRAM 测量。
- **M2.5 W1 口径已被补充**：M2.5 的 GPU 结论来自系统级 `nvidia-smi memory.used`（W1：含桌面/浏览器等其它
  进程，不能归因）。M2.6 起用逐进程 dedicated 采样做 A/B；M2.6 的 A/B 即用该指标。系统级 `gpu_menu_mb`
  仍保留为旁证，二者不可混用。
- Base 单对是反面例子：逐进程 dedicated 451.6 → 274.4 MB（−177.2），但系统级 `gpu_menu_mb` 2669 → 2951
  （**+282**，方向相反）。这正说明系统级只能作旁证，不能单独引用。

### 3.2 修后 A/B（Task 2，`build/m26/ab-fix.json`）

协议与 §3 相同（miko-lite、warm、DDS on、eviction/selftest off、`--linger 20`、3 轮、每轮先 C 后 T、
未做 counterbalance）；`free_mb_start=15,227.6 MB`；6 个会话全部 `ok=true`、`stop=forced`。

| # | C menu | T menu | C WS | T WS | C GPU proc | T GPU proc | C GPU sys | T GPU sys | ddsHit | ddsFallback | materialized |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 67.6 | 70.1 | 11,233.2 | 10,962.3 | 927.0 | 496.6 | 2,693.0 | 2,068.0 | 18 | 2 | 85 |
| 2 | 52.6 | 54.6 | 10,977.4 | 11,455.9 | 927.0 | 496.6 | 2,518.0 | 2,091.0 | 26 | 2 | 93 |
| 3 | 52.1 | 51.6 | 11,006.0 | 10,972.0 | 927.0 | 496.6 | 2,517.0 | 2,078.0 | 29 | 2 | 96 |

- **control_median = 52.6 s，treatment_median = 54.6 s，delta_s = +2.0 s；成对差
  `[+2.5, +2.0, −0.5]`，成对中位 +2.0 s**（JSON 原值）。第 1 对为 warm-up（67.6/70.1 s）。
- 成对 WS 差 = −270.9 / +478.5 / −34.0 MB，方向不一致，不作为收益/回退口径。
- 逐进程 GPU 成对差 = **−430.4 MB ×3**（3/3 treatment 更低）；系统级成对差 = −625 / −427 / −439 MB
  （3/3 更低，仅旁证）。退出时逐进程 dedicated 也全部更低（control 959.5 / 964.7 / 964.6 vs
  treatment 526.3 / 533.4 / 531.6 MB）。
- 所有 gates true（`all_rounds_ok`、`no_texture_errors`、`failed/disabled/dimMismatch/ddsDisabled=0`、
  `ddsHit>0`）；6 会话 0 Failed/Verify/Class/Async/Corrupted。
- `lazy_median`：`ddsHit=26`（18–29）、`ddsFallback=2`、`materialized=93`（85–96）、
  `skipped=proxies=drained=45,784`、`index=73,447`、`eviction=evicted=evictPasses=0`、
  `failed=disabled=dimMismatch=0`。

---

## 4. Lazy / DDS / 淘汰计数

`build/m26/ab-result.json` 的 `lazy_median`（逐 treatment 轮**最后一条 summary** 的逐键中位；不是与菜单
WS/GPU 同一瞬间的采样；字符串字段 `types/main/loading` 在中位里为 null，但每轮分别为
`{TEXTURE_ALPHA_ADDER=1,TEXTURE=52603}` / `main` / `Thread-4-FR-Main-Loader`）：

| 指标 | 值（3 轮范围） |
|---|---:|
| queue | 52,604 |
| wouldSkip | 45,785 |
| skipped / proxies / drained | **45,784 / 45,784 / 45,784** |
| materialized | 88（85–99） |
| demand / demandQueued / hits | 21,358 / 7,322 / 7,322（21,349–21,363 / 7,313–7,327 / 7,313–7,327） |
| lookups | 98,849（98,678–110,671） |
| index | 73,446 |
| deferred / pending / failed / disabled / dimMismatch | **0 / 0 / 0 / 0 / 0** |
| lateRegistered / lateLoaded | 0 / 0 |
| dds / ddsHit / ddsFallback / ddsDisabled / ddsDimMismatch | 1 / **21（18–32）** / **2** / 0 / 0 |
| eviction / evicted / evictedBytes / rematerialized | 0 / 0 / 0 / 0 |
| evictPasses / placeholder / oldIdDeleted / evictSkipped / deferredDeletes | 0 / 0 / 0 / 0 / 0 |
| selftest | 0 |
| liveBytes | 14,450,896（14,444,752–14,524,535） |

- 45,785 vs 45,784 的差仍是 1 条 `TEXTURE_ALPHA_ADDER`（按设计不跳过），与 M2.5 一致。
- **DDS 命中只覆盖有 VOpt 烘焙的普通纹理**：18–32 次命中 vs 85–99 次物化，其余是 normal/UI/未烘焙的
  PNG 路径（M-1b 已核实 normal 不在 DDSCache）。`ddsFallback=2` 在 260mods 与 Base 的**每个**会话都恒定；
  这些是设计上静默的回退分支（缺 DDS 元数据/桥接 miss），不逐条记日志，也不是失败（PNG 回退），但没有
  被诊断到具体路径。
- `evicted=0` 是菜单 A/B（eviction off）的预期值：85–96 次物化（修前 85–99）主要发生在 FR loading
  线程、被 `markStartup` 一次性闩锁永久排除，菜单期也没有预算压力；`evictPasses=0` 是配置关闭的结果。
- Task 2 修后 A/B（`ab-fix.json`）的 `lazy_median`：`index=73,447`（安装器本次生成 73,447 行；
  `skipped=proxies=45,784` 不变）、`ddsHit=26`、`ddsFallback=2`、`materialized=93`、
  `failed=disabled=dimMismatch=0`、`evicted=evictPasses=0`。

---

## 5. Selftest

**修后（Task 2，2026-11-02）**：

- `build/m26/selftest-fix.json`（`--eviction --selftest`，默认预算 256 MB，1 对 C/T）：treatment
  `selftest=1`、`evicted=1`、`rematerialized=1`、`evictPasses=0`（无预算压力，符合预期）、
  `placeholder=15165`、`ddsHit=24`、`ddsFallback=2`、`failed=disabled=dimMismatch=0`；C/T 菜单
  66.1/68.1 s；两侧 0 Failed/Verify/Class/Async/Corrupted；gates 全 true。
- `build/m26/fix-auto.json`（budget=1、grace=0、sceneDelay=100 ms、selftest=1，单轮 smoke）：
  最后一条 10 s summary 快照 `evictPasses=69`；agent log 共 **135 条** `lazy: eviction pass`
  日志，最后快照后另有 67 条，因此 forced exit 时 `EVICT_PASSES` **≥136**（无 shutdown summary，
  不能读最终精确值）。`evicted=455`、`evictedBytes=25,666,296`、`rematerialized=447`、
  `materialized=545`、`ddsHit=342`、`ddsFallback=138`、`placeholder=15165`、`selftest=1`、
  `failed=disabled=dimMismatch=0`，0 Failed/Verify/Class/Async/Corrupted（会话切片扫描见 §6）。
  菜单 73.6 s 是低 free 内存（2,962 MB）下的单次 smoke，不作时间口径。**自动 `evictPass`
  触发已证明**（首条 `lazy: eviction pass evicted=14 ... budget=1048576` 在 17:03:46）。
- **压力 vs 默认**：默认预算 selftest **不产生淘汰压力**（`evictPasses=0`，仅 selftest 强制
  1 次 evict/re-materialize）；budget=1 是**压力门禁**，短时 455 evicted / 447 rematerialized 的
  churn 只用于证明自动 trigger，不代表生产配置行为。
- 观察项：budget=1 时 `ddsFallback=138`（平时为 2）是 545 次物化（含大量重复物化）中的
  非 DDS/PNG 回退混合计数（normal/UI/未烘焙等），**不能证明是淘汰缺陷**；具体构成未诊断，
  列为观察项（详见 §7.12）。

修前（Task 4）：

`build/m26/selftest.json`（1 control + 1 treatment，`--eviction --selftest --linger 20`，DDS on）；
菜单 control 51.1 s / treatment 51.6 s；两侧 0 Failed/Verify/Class/Async/Corrupted。Treatment：

`selftest=1`、`eviction=1`、`evicted=1`、`evictedBytes=3432`、`rematerialized=1`、`placeholder=15165`、
`oldIdDeleted=0`、`evictPasses=0`、`evictSkipped=0`、`deferredDeletes=0`、`liveBytes=14,460,664`、
`ddsHit=27`、`ddsFallback=2`、`ddsDisabled=0`、`ddsDimMismatch=0`、`failed=0`、`disabled=0`、
`dimMismatch=0`、`skipped=proxies=drained=45,784`、`materialized=94`。

关键日志（live agent log；归档日志曾被后续 run 覆盖，见 §7.10）：

```text
2026-11-01T14:06:53.998370500Z INFO lazy: dds materialized graphics/templars/weapons/tem_arondight_turret_recoil.png 44x78 id=15166 bytes=3432
2026-11-01T14:06:54.004877600Z INFO lazy: eviction placeholder resolved id=15165
2026-11-01T14:06:54.007880200Z INFO lazy selftest: ok path=graphics/templars/weapons/tem_arondight_turret_recoil.png ids=15166->15164 dds=1 rematerialized=1
...
... materialized=94 ... dds=1 ddsHit=27 ddsFallback=2 ddsDisabled=0 ddsDimMismatch=0 eviction=1 evicted=1 evictedBytes=3432 rematerialized=1 evictPasses=0 liveBytes=14460664 placeholder=15165 oldIdDeleted=0 evictSkipped=0 deferredDeletes=0 selftest=1
```

- id 序列：首次物化 **15166** → 占位解析 **15165** → 删除 15166 → 重新物化 **15164**。`selftest=1` 要求
  `evictOne` 返回 true，即 `GlBridge.deleteTexture(15166)` 成功；`evictSkipped=0` 确认没有删除失败。
  `oldIdDeleted=0` 是计数器缺口（只有 `refreshReady` 增加它，`evictOne` 不增加），不是 id 泄漏。
- **触发偏差（必须记录）**：brief 原本假设 `noteGameState` 每帧/定时可达；实际本 build 里
  `BaseGameState.traverse`（唯一 `captureMainThread` 钩子）**每个 state 入口只执行一次**（该 state 的帧
  循环，不是每帧回调），diagnostic 只打印
  `call=1`，所以 brief 的 `noteGameState` 计时器在菜单-only 会话永远不会触发。实现把同一条件抽成
  **主线程一次性 `maybeRunSelfTest()`**：由 `noteGameState` + 每帧主线程路径 `onProxyUse`/`lookup` 调用，
  `SELFTEST_DONE` CAS、`Thread.currentThread() == runtimeMain`、capture 后 **≥5 s**；实测在标题屏 capture
  后约 7 s 触发。Selftest 在 `bind`/`id` 回调内做 GL 物化（与正常按需物化同一上下文），一次性、菜单锚点。
  这是**必要的实现偏差**，不是“每帧计时器已工作”；review 把“never fires”收窄为“menu-only 会话不重复触发”。
- Selftest **不是战斗/A→B**：只覆盖一条从未 ready 的不可见纹理（无外部持有者），不能替代第三方 id 缓存、
  战斗并发、读档、分辨率切换的验收。

---

## 6. 正确性

- 本轮共 **10 个会话**（A/B 3 轮 × 2 + selftest 1 轮 × 2 + Base 1 轮 × 2）；每会话 0
  `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError` / 0 `AsyncException` /
  0 `isStateCorrupted`。错误计数来自聚合 JSON（`ab-result.json` / `selftest.json` / `base-ab.json`）与
  live agent log；selftest 的归档日志被后续 run 覆盖（§7.10），不能作为独立切片复核。
- Task 2 修后另有 **9 个会话**（fix-auto 1 + selftest-fix 2 + ab-fix 6）。fix-auto 的
  `starsector.log` 会话切片已补扫并落盘：`build/m26/fix-auto-session.log`（第 16 个
  `Fast Rendering` anchor，menu anchor 73,100 ms，2,128,915 B，sha256
  `31a170dc7b4acb32aca3bc2576ebaff4228a1e8d94aef8e7a4553c46b184eff6`），0
  `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError` / 0 `AsyncException` /
  0 `isStateCorrupted`；其余 8 个会话的错误计数来自 `selftest-fix.json` / `ab-fix.json`
  归档切片。9/9 均按切片验证 0 错误。
- agent：260mods `failed=0`、`disabled=0`、`pending=0`、`drained=45,784`；Base `failed=0`、`disabled=0`、
  `drained=2,330`；两侧 `dimMismatch=0`、`lateRegistered=lateLoaded=0`、`deferredDeletes=0`。
- Live 日志确认 bridge 形状：`lazy: GL delete bridge resolved on com.genir.renderer.bridge.opengl.GL11`；
  `lazy: dds materialized ...` 多行；`lazy selftest: ok ...` 共 **2 行**（14:00:45.772 的 probe run 与
  14:06:54.007 的正式 run，路径/ids 相同）；selftest 归档切片已被后续 run 覆盖，这两行来自 live agent log。
- **manual visual / battle 明确未做，不标 PASS。**

---

## 7. 限制 / 偏差

1. **菜单 only、修前/修后各 3 轮**（另有 pre-fix A/B 3 轮和 Base 1 对）：只回答自动化菜单锚点下的
   计数/正确性；无随机化、无 CI、无显著性检验。**战斗/读档/分辨率/手动目检未做，pending user。**
2. **A→B 长会话净 VRAM 未测**：逐进程 GPU 是菜单时/退出时快照（n=3），不是战斗/长会话 trace；不得据此
   宣称长会话净收益。
3. **>200 ms 卡顿未测**：没有 frame-time/P99/stutter 数据；selftest 只在菜单做一次
   materialize→delete→re-materialize，且发生在 `bind`/`id` 回调内，一次性。
4. **GL context 重建后的占位**（alt-tab/分辨率/显示模式/FR 重启）：未测。`PLACEHOLDER_FAILED` 是会话级
   一次性闩锁；context 重建会一次性作废所有 GL id，占位 id 可能悬空（预期表现为不可见/未定义，不崩溃），
   但没有检测/重解析逻辑。
5. **第三方按 id 缓存 + 引擎真实对象（I-2，已修）**：`selectVictims`/`evictOne` 现在只接受
   `owned=true`；DDS 与 PNG 物化均置 `owned=true`，`onRegister`/`noteEngineHit`/`refreshReady`
   保持 `owned=false`。因此 F3/cache-clear 场景下由引擎真实对象刷进来的代理（含 GL id）不会再被
   淘汰。**仍余**：mod 若把 GL id 拷进自有结构，淘汰后仍可能持有已删 id；REQ-R1-10 要求的引用计数/
   “仍被引用则拒绝并记录”没有全局注册表，无法实现；owned PNG 来自 `TextureLoader` syncLoad，若该
   id 被引擎/mod 共享，删除仍可能影响其它引用。selftest 只覆盖无外部持有者的单条代理。
   **default-on gate 缩小但未消失（eviction 默认 off）。**
6. **pick→evict 的 TOCTOU**：picker 过滤 `ready/failed/startup/basic`，但 `evictOne(pick, true)` 用
   `force=true` 绕过 startup/basic 的二次检查；pick 与 evict 之间若有并发 off-main 物化，可能淘汰刚被标记
   startup 的代理。菜单期未观察到（`pending=0`、`drained=45,784`、loading 线程空闲）；战斗/加载并发未测。
7. **自动 `evictPass` 调度（I-1，已修）**：旧实现在本 build 结构性不触发（`evictPass` 唯一调用点
   `noteGameState` 只在 state 入口执行一次，换名入口先重置 due 再检查，`delay>0` 当次必不执行；
   `isCombatState` 空转）。现实现：`maybeRunEviction` 由每帧主线程路径 `lookup`/`onProxyUse` 与
   `noteGameState` 确定性调用；`noteGameState` 只在换名时 arm，实际执行在后续主线程热路径到达 due
   时；战斗门禁改为真实 `Global.getCurrentState()==COMBAT`（反射，探测失败保守按战斗处理）；删除
   `isCombatState`；`evictPass` 结束按 `nextDueAfterPass` 重 arm（部分 pass 继续，空 pass 30 s
   backoff）；`noteMaterialized` 在 due==0 且 live>budget 时预算 arm。**真实进程证据**
   （`build/m26/fix-auto.json` + agent log，budget=1/grace=0/sceneDelay=100 ms）：
   最后一条 10 s summary 快照 `evictPasses=69`、agent log 135 条 pass（最后快照后 67 条，
   退出时 ≥136）、`evicted=455`、`rematerialized=447`、`selftest=1`、`placeholder=15165`、
   `failed=disabled=dimMismatch=0`、0 Failed/Verify/Class/Async/Corrupted。自动 trigger 已证明；
   战斗/长会话中的真实自动 victim 选择、stutter、长会话净 VRAM 仍需用户验收（selftest 仍直接调
   `evictOne`、不增加 `evictPasses`）。
8. **逐进程 GPU 是快照，不是 VRAM 账**：OS 逐进程计数，不能逐纹理归因；`ddsBytes` 不含 mip；
   `liveBytes`/`evictedBytes` 是估算值；系统级 `gpu_menu_mb` 只作旁证（Base 单对甚至方向相反：逐进程
   451.6→274.4 MB，系统级 2669→2951 MB）。
9. **淘汰计数语义（M-6）**：`evicted` 是**代理复位成功的条数**（`evictOne` 在 delete 之前就递增
   `EVICTED/EVICTED_BYTES` 并扣 `LIVE_BYTES`），不是“VRAM 已释放量”；`evictSkipped` 同时混入淘汰删除
   失败与 `refreshReady` 旧 id 删除失败两类；`evictOne` 成功删除旧 id 也不增加 `oldIdDeleted`，summary
   可同时出现 `evicted=1 ... oldIdDeleted=0`。删除成功以 `selftest=1` + `evictSkipped=0` 为准。
10. **每 run 产物互相覆盖**：`tools/m26_ab.py` 硬编码 `build/m26/ab-c{i}.json` / `ab-t{i}.json`，日志写进
    共享 `--log-dir`；selftest 的归档日志被后续 A/B 覆盖、`ab-c1.json` 现在是 Base control 行、
    `selftest.json` 里的日志路径已失效。聚合 JSON（`ab-result.json` / `selftest.json` / `base-ab.json`）
    保留了全部数值，门禁结论不变。
11. **工具门禁缺口**：缺 `starsector.log` 时 `archive_round` 返回全零，`no_texture_errors` 可空过（不是
    fail-closed）；`--no-dds` 因无条件要求 `ddsHit>0` 永远无法 exit 0；单轮 `TimeoutExpired` 会中止整个
    A/B 且不落聚合 JSON（Minor，留给 final review triage）。
12. **`ddsFallback` 常态 2、budget=1 压力下 138**：该计数是“DDS 物化未走通 → PNG 回退”的混合
    计数（normal/UI/未烘焙、缺 DDS 元数据/桥接 miss 等），不逐条记日志，原因未诊断；138 出现在
    545 次物化（含大量重复物化）的压力场景，**不能证明是淘汰缺陷**。按设计回退 PNG，不是失败，
    但属于盲区。
13. **版本耦合**：FR 0.9.7rc2 内部形状（`DDSIntegration` / `TextureData` / private 实例
    `newVanillaTextureHandler` / GL11 bridge）；FR 升级需重新 javap/shape gate。fail-open 路径有单元测试和
    代码审查，但只在 rc2 运行时实际跑过。
14. **Selftest 触发偏差**：见 §5；"noteGameState 计时器"在本 build 的菜单-only 会话不成立，实际是
    `maybeRunSelfTest()` 的主线程一次性门。该偏差已由 Task 4 review 复核（runtimeMain/CAS/≥5 s/无 worker
    触发），但战斗/读档下的触发时机未测。
15. **default-on gates（默认开启 / 对外“可选显存优化”声明前必须修）**：**I-1（自动 `evictPass`
    调度）与 I-2（owned-only）已在 `35fc768` + `01cf3e1` 修复**，budget=1 真实进程 smoke 已见
    自动 pass（最后 10 s summary 快照 `evictPasses=69`，退出时 ≥136；§5/§7.7）。仍余：
    refcount/REQ-R1-10（“仍被引用则拒绝并记录”）、第三方按 id 缓存、**预算口径**（`liveBytes`
    含 startup 物化字节，这些字节被 `markStartup` 永久排除，可能造成预算不可达/空 pass）与
    **空 pass 30 s backoff** 的真实会话行为、M2.5 W5/W6（发行包 manifest/skip 与 agent jar
    新鲜度）、W-2/W-3/W-5/W-10（GL context 重建后的占位、第三方 id 持有者、pick→evict TOCTOU、
    失败物化 id=0），以及用户完成战斗/读档/分辨率/手动目检、A→B 长会话净 VRAM、>200 ms 卡顿
    （M-4 安装可复现已由 `install-manifest.sh` 的 blank 断言 + §8.3 命令记录覆盖）。在这些项
    关闭前，不得声称 bounded LRU 已在真实会话自动工作（自动 trigger 已证明，真实自动 victim/
    长会话未验收），也不得对外称“可选显存优化”。

---

## 8. 默认 / 回滚 / 文件 / commits

### 8.1 默认值

- `textures.lazy.enabled=false`（配置缺失/坏配置均为 false）。
- `textures.lazy.eviction.enabled=false`；预算默认 256 MB、grace 10 s、场景切换延迟 2 s、每次最多 64 条。
- `textures.lazy.dds=true`（**仅当 lazy 开启时**生效；lazy 默认关闭时 `dds` 不触发反射/桥接）。
- `textures.lazy.selftest=false`。
- 两侧安装的 `hypernova.json` **没有 `textures.lazy` 键**（等同默认关闭；`textures` 下只有
  `enabled=true`）；A/B 的开关都走命令行 `-D`，没有写进 `Miko_*.txt` / `fr.vmparams` /
  `enabled_mods.json` / 游戏设置。

### 8.2 回滚（任一即可）

1. 配置 `textures.lazy.enabled=false`（或 `textures.lazy.eviction.enabled=false` 单独关淘汰）；
2. 启动参数 `-Dhypernova.textures.lazy=false`；
3. 删除启动文件中的 `-javaagent:.../hypernova.agent.jar` 行（`python tools/install_agent.py --action uninstall ...`）。

skip v1/v2 可以保留；关闭后不读取、不跳过、不注册代理，行为回到 M2/M2.5。回滚不改存档/设置。

### 8.3 安装（agent-only 260mods）

- 260mods 的 `hypernova_infinite_engine` **不在** `enabled_mods.json` 里（agent-only 安装），所以
  `mods/hypernova_infinite_engine/graphics/hypernova/blank.png` 不保证被 FileLoader 扫描。淘汰占位要求
  `starsector-core/graphics/hypernova/blank.png` 存在且非空（缺失/为空会 latch `PLACEHOLDER_FAILED`，
  selftest=2、淘汰整会话不可用）。
- Task 4 是**手工**把 `blank.png` 复制到 `starsector-core/graphics/hypernova/` 才使 `placeholder=15165`
  成立；`tools/java/install-manifest.sh` 现在会在拷贝 mod `graphics/` 之后自动复制该文件并断言非空，
  失败时报 `ERROR`。
- **Task 2（修后重装，2026-11-02）**：`run-agent-tests.sh` → `build-mod.sh` → 两侧
  `install_manifest.py --game-root <game>` → 两侧 `install_agent.py --game <game> --env <260mods-lite|base>`
  → `cp -r graphics/. <mod>/graphics/` 与 `cp graphics/hypernova/blank.png
  <game>/starsector-core/graphics/hypernova/`。安装时校验：两侧 `hypernova.agent.jar` 与当次
  `build/agent/hypernova.agent.jar` `cmp` 一致；manifest/skip 非空；两侧 core `blank.png` 非空；
  两次 `install_agent.py` 均报 `no vmparams change`（仅刷新 jar）。Step 6 再次
  `run-agent-tests.sh` 重建 jar 后 zip 时间戳变化，但 class entry 的 CRC/大小与安装件完全一致
  （内容相同；sha256 会因 zip 时间戳不同而不同，不能用于跨构建比较）。

### 8.4 文件与证据

- 代码：`src/agent/java/hypernova/agent/textures/{LazyTextures,LazySkipIndex,LazyTextureConfig,ProxyShape,DdsCheck,DdsBridge,GlBridge}.java`；
  `graphics/hypernova/blank.png`；`tools/{gen_lazy_skip.py,install_manifest.py,m26_ab.py}`；
  `tools/java/{build-mod.sh,install-manifest.sh}`。
- 测试：`tests/agent/java/hypernova/agent/textures/{LazyGateTest,LazyEvictionTest,DdsCheckTest,DdsBridgeTest,GlBridgeTest}.java`、
  `tests/tools/test_m26_ab.py` 等（Task 4 时点全量 agent 165 found / 164 pass / 1 known symlink abort /
  0 fail；Task 2 fix 后 172 found / 171 pass / 1 known symlink abort / 0 fail；pytest 287 passed）。
- 运行证据（`build/` 不入库）：`build/m26/ab-result.json`、`ab-result-prefix.json`、`selftest.json`、
  `base-ab.json`、`logs/`、`logs-base/`、`probe/`、`ab-run2.log`、`selftest-run.log`、`base-run.log`；
  修后证据：`build/m26/fix-auto.json`、`fix-auto-session.log`（starsector.log 会话切片）、
  `selftest-fix.json`、`ab-fix.json`、`ab-fix-run.log`。

### 8.5 commits

- 计划/addenda：`0a88714`、`68bb9fb`、`c2fe8ed`、`a2135b8`、`e2b66ae`、`2b66373`
- 实现：`7fbb9e6`（Task 0）、`f2f3625`（Task 1）、`e5c7fcf`（Task 0 F1/F2）、`5d982e4`（Task 2）、
  `8d01fe1`（Task 3）、`d2e1cb9`（Task 2 C1/I1/I2）、`b716f74`（Task 3 I2）、`ad16a4d`（Task 4）
- 修后 gates：`35fc768`（I-1 确定性触发 + I-2 owned-only）、`01cf3e1`（bind recency + 测试强化）
- 工具：`57b9b0b`（逐进程 GPU 采样）
- 文档：`e02bff6`（本文件 + `技术笔记` §6.1 的 M2.5 W1 → 逐进程 GPU 口径行 + §7 M2.6 状态 +
  `大饼` 状态行）；本条 review-fix docs commit（4 个文字更正，见 `.superpowers/sdd/2026-11-01-m26-dds-lru/task-5-fix-report.md`）；
  Task 2 docs commit（本提交，修后 A/B/selftest/auto 证据 + gates 更新）。
