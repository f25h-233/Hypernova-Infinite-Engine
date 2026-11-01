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
2. **DDS 路径真实生效**：260mods 菜单 treatment `ddsHit=18–32`（中位 21）、`ddsFallback=2`、`ddsDisabled=0`、
   `ddsDimMismatch=0`；`failed=0`、`disabled=0`。Base `ddsHit=21`，`ddsDisabled/ddsDimMismatch` 同为 0。10 个归档会话 0
   `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError` / 0 `AsyncException` / 0 `isStateCorrupted`。
3. **菜单 A/B（n=3，miko-lite，warm）没有明确时间收益**：control 中位 **52.6 s** vs treatment **54.6 s**，
   delta **+2.0 s**，成对差 **−3.0 / +7.0 / +2.0 s**。+2.0 s 正好落在计划 ≤2 s 的边界上；成对差跨 10 s、
   同主机跨 run 中位漂移约 4–7 s，因此**既不能确认 +2.0 s 是真实回退，也不能宣称菜单时间不受影响或受益**。
   v2 索引加载 147–178 ms 是 treatment-only（后台线程），但 pre-fix A/B（同一 25 MB v2 索引）为 −0.5 s；
   噪声主导。本文件只把它记为边界值，不据此下任何方向性结论。
4. **逐进程 GPU（新指标，`57b9b0b`）方向一致**：菜单时 dedicated control **804.8–927.0 MB** vs treatment
   **368.9–496.6 MB**；三对差 **−558.1 / −308.2 / −430.4 MB**（3/3 更低）。系统级 `gpu_menu_mb` 也 3/3 同向
   （−253 / −203 / −512 MB），仅作旁证。该指标是 OS 逐进程快照，不是逐纹理/VRAM 精确账；`ddsBytes` 不含
   mip 链，`liveBytes` 是估算值。
5. **Selftest 走通 materialize → evict → re-materialize**：`selftest=1`、`evicted=1`、`rematerialized=1`、
   `placeholder=15165`、ids **15166→15164**、`dds=1`；只淘汰 1 条不可见纹理，**不等价于战斗/A→B 验收**。
6. **LRU 默认 off，自动化淘汰证据只有 selftest**：菜单 A/B `evicted=0` 是预期的（启动期物化被 startup
   闩锁永久保护）；`evictPasses=0`，自动 `evictPass` 未在真实会话中触发过。
7. **Base gate 通过**：all gates true；`skipped=proxies=2,330`、`ddsHit=21`、`failed=0`、`disabled=0`；
   进程 GPU dedicated 451.6 vs 274.4 MB；菜单 8.5 vs 6.5 s；0 错误。
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

---

## 3. 菜单 A/B 原始表

协议：260mods（miko-lite）、warm、DDS on、eviction/selftest off、`--linger 20`、3 轮交错 C/T，
`build/m26/ab-result.json`。Control 只传 `-Dhypernova.textures.lazy=false`；treatment 传
`-Dhypernova.textures.lazy=true -Dhypernova.textures.lazy.dds=true`。

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
- `evicted=0` 是菜单 A/B 的预期值：A/B 本身 `eviction=false`；即使开启，85–99 次物化主要发生在 FR
  loading 线程、被 `markStartup` 一次性闩锁永久排除，菜单期也没有预算压力，且自动 `evictPass` 未触发
  （`evictPasses=0`）。

---

## 5. Selftest

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
  `BaseGameState.traverse`（唯一 `captureMainThread` 钩子）**每次状态切换只调一次**，diagnostic 只打印
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
- agent：260mods `failed=0`、`disabled=0`、`pending=0`、`drained=45,784`；Base `failed=0`、`disabled=0`、
  `drained=2,330`；两侧 `dimMismatch=0`、`lateRegistered=lateLoaded=0`、`deferredDeletes=0`。
- Live 日志确认 bridge 形状：`lazy: GL delete bridge resolved on com.genir.renderer.bridge.opengl.GL11`；
  `lazy: dds materialized ...` 多行；`lazy selftest: ok ...` 共 **2 行**（14:00:45.772 的 probe run 与
  14:06:54.007 的正式 run，路径/ids 相同）；selftest 归档切片已被后续 run 覆盖，这两行来自 live agent log。
- **manual visual / battle 明确未做，不标 PASS。**

---

## 7. 限制 / 偏差

1. **菜单 only、n=3**（另有一次 pre-fix 3 轮采样和 Base 1 对）：只回答自动化菜单锚点下的计数/正确性；
   无随机化、无 CI、无显著性检验。**战斗/读档/分辨率/手动目检未做，pending user。**
2. **A→B 长会话净 VRAM 未测**：逐进程 GPU 是菜单时/退出时快照（n=3），不是战斗/长会话 trace；不得据此
   宣称长会话净收益。
3. **>200 ms 卡顿未测**：没有 frame-time/P99/stutter 数据；selftest 只在菜单做一次
   materialize→delete→re-materialize，且发生在 `bind`/`id` 回调内，一次性。
4. **GL context 重建后的占位**（alt-tab/分辨率/显示模式/FR 重启）：未测。`PLACEHOLDER_FAILED` 是会话级
   一次性闩锁；context 重建会一次性作废所有 GL id，占位 id 可能悬空（预期表现为不可见/未定义，不崩溃），
   但没有检测/重解析逻辑。
5. **第三方按 id 缓存**：mod 若把 `ô00000` 的 GL id 拷进自有结构，淘汰后可能持有已删 id；selftest 选中的
   纹理在淘汰前从未 ready（没有外部持有者），所以本轮不能覆盖该风险。
6. **pick→evict 的 TOCTOU**：picker 过滤 `ready/failed/startup/basic`，但 `evictOne(pick, true)` 用
   `force=true` 绕过 startup/basic 的二次检查；pick 与 evict 之间若有并发 off-main 物化，可能淘汰刚被标记
   startup 的代理。菜单期未观察到（`pending=0`、`drained=45,784`、loading 线程空闲）；战斗/加载并发未测。
7. **自动淘汰未触发**：`evictPasses=0`（A/B 与 selftest 都是）；`runSelfTest` 直接调 `evictOne`，而
   `evictPass` 只从 `noteGameState` 进入——该钩子在菜单-only 会话是稀疏的（每次状态切换一次），正常游戏
   是否按时触发未验证。startup 闩锁永久保护 loading 期物化，菜单 A/B 的 `evicted=0` 是预期，不是调度器
   健康的证据。
8. **逐进程 GPU 是快照，不是 VRAM 账**：OS 逐进程计数，不能逐纹理归因；`ddsBytes` 不含 mip；
   `liveBytes`/`evictedBytes` 是估算值；系统级 `gpu_menu_mb` 只作旁证（Base 单对甚至方向相反：逐进程
   451.6→274.4 MB，系统级 2669→2951 MB）。
9. **`oldIdDeleted` 计数缺口**：`evictOne` 删除旧 id 但不增加 `OLD_ID_DELETED`，summary 可同时出现
   `evicted=1 ... oldIdDeleted=0`。删除成功以 `selftest=1` + `evictSkipped=0` 为准。
10. **每 run 产物互相覆盖**：`tools/m26_ab.py` 硬编码 `build/m26/ab-c{i}.json` / `ab-t{i}.json`，日志写进
    共享 `--log-dir`；selftest 的归档日志被后续 A/B 覆盖、`ab-c1.json` 现在是 Base control 行、
    `selftest.json` 里的日志路径已失效。聚合 JSON（`ab-result.json` / `selftest.json` / `base-ab.json`）
    保留了全部数值，门禁结论不变。
11. **工具门禁缺口**：缺 `starsector.log` 时 `archive_round` 返回全零，`no_texture_errors` 可空过（不是
    fail-closed）；`--no-dds` 因无条件要求 `ddsHit>0` 永远无法 exit 0；单轮 `TimeoutExpired` 会中止整个
    A/B 且不落聚合 JSON（Minor，留给 final review triage）。
12. **`ddsFallback=2` 是常量且静默**：分支（缺 DDS 元数据/桥接 miss）不逐条记日志，原因未诊断；按设计
    回退 PNG，不是失败，但属于盲区。
13. **版本耦合**：FR 0.9.7rc2 内部形状（`DDSIntegration` / `TextureData` / private 实例
    `newVanillaTextureHandler` / GL11 bridge）；FR 升级需重新 javap/shape gate。fail-open 路径有单元测试和
    代码审查，但只在 rc2 运行时实际跑过。
14. **Selftest 触发偏差**：见 §5；"noteGameState 计时器"在本 build 的菜单-only 会话不成立，实际是
    `maybeRunSelfTest()` 的主线程一次性门。该偏差已由 Task 4 review 复核（runtimeMain/CAS/≥5 s/无 worker
    触发），但战斗/读档下的触发时机未测。

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

### 8.3 文件与证据

- 代码：`src/agent/java/hypernova/agent/textures/{LazyTextures,LazySkipIndex,LazyTextureConfig,ProxyShape,DdsCheck,DdsBridge,GlBridge}.java`；
  `graphics/hypernova/blank.png`；`tools/{gen_lazy_skip.py,install_manifest.py,m26_ab.py}`；
  `tools/java/{build-mod.sh,install-manifest.sh}`。
- 测试：`tests/agent/java/hypernova/agent/textures/{LazyGateTest,LazyEvictionTest,DdsCheckTest,DdsBridgeTest,GlBridgeTest}.java`、
  `tests/tools/test_m26_ab.py` 等（全量 agent 165 found / 164 pass / 1 known symlink abort / 0 fail；
  pytest 287 passed，Task 4 最终 jar 时点）。
- 运行证据（`build/` 不入库）：`build/m26/ab-result.json`、`ab-result-prefix.json`、`selftest.json`、
  `base-ab.json`、`logs/`、`logs-base/`、`probe/`、`ab-run2.log`、`selftest-run.log`、`base-run.log`。

### 8.4 commits

- 计划/addenda：`0a88714`、`68bb9fb`、`c2fe8ed`、`a2135b8`、`e2b66ae`、`2b66373`
- 实现：`7fbb9e6`（Task 0）、`f2f3625`（Task 1）、`e5c7fcf`（Task 0 F1/F2）、`5d982e4`（Task 2）、
  `8d01fe1`（Task 3）、`d2e1cb9`（Task 2 C1/I1/I2）、`b716f74`（Task 3 I2）、`ad16a4d`（Task 4）
- 工具：`57b9b0b`（逐进程 GPU 采样）
- 文档：`e02bff6`（本文件 + `技术笔记` §6.1 的 M2.5 W1 → 逐进程 GPU 口径行 + §7 M2.6 状态 +
  `大饼` 状态行）；本条 review-fix docs commit（4 个文字更正，见 `.superpowers/sdd/2026-11-01-m26-dds-lru/task-5-fix-report.md`）。
