# M2.5 结果：通用纹理懒加载（跳过 / 代理 / 按需物化）

- 日期：2026-11-01
- 宿主：Starsector **0.98a-RC8** + Fast Rendering **0.9.7rc2**；Base（运行期 mod）与 260mods（agent-only）
- 主链 commits：`a9bc2a3` + `7ea15db`（Task 2）、`e4b091d`（Task 3）、`a1971f6`（Task 4）、`b625743`（Task 5 F3 修复）
- **状态：M2.5 以 experimental / 默认 off 收口。** 菜单时间无收益；菜单时刻有 ~400 MB GPU / ~200 MB WS 量级的内存下降；没有淘汰，会话越久节省越少；post-menu burst/stutter 与战斗未测。下一里程碑 M2.6（DDS 按需物化 + 有界 LRU）见 `大饼-DDS按需物化与LRU.md`。

---

## 1. 结论

1. **Task 1 GO（operational 口径）**：G1/G3/G4 PASS；G2 按字面 raw demand 为 NO-GO，按审查修正的 operational 口径（分母 `wouldSkip`）PASS。菜单前 `demandQueued` 798–801（1.74–1.75%），会话末 7,317–7,382（15.98–16.12%），均低于阈值 9,157（0.20 × 45,785）。
2. **生产结构性成立**：260mods 启动队列 52,604，`wouldSkip` 45,785，实际 `skipped = proxies = 45,784`；`deferred / pending / failed / disabled = 0`。1 条 `TEXTURE_ALPHA_ADDER` 按设计不跳过（45,785 − 1）。
3. **菜单时间收益不成立**：协议 3 轮 control 中位 51.1 s vs treatment 46.6 s（−4.5 s），但 control 序列 64.2 → 51.1 → 46.1 明显漂移；加 2 对稳态补充后，5 对成对差中位 **−0.5 s**。−4.5 s 不归因 lazy。
4. **内存（菜单时刻，定性）**：GPU 成对中位 **−421 MB（5/5 对更低）**；进程 working set 成对中位 **−199 MB（4/5 对）**；系统 free 成对中位 **+154 MB（3/5 对）**。n=5、无显著性检验，GPU 是 `nvidia-smi` 系统级 `memory.used`，不是进程级。
5. **收益仅限菜单时刻**：A/B 每轮在菜单后约 8 s 结束，`materialized=85–91`；Task 5 单轮 `--linger 60` treatment 显示菜单后 60 s 内 `materialized` 76 → 94、WS +219.5 MB、free −183.7 MB，内存节省随会话推进会吃掉一部分。**post-menu burst/stutter 未测**。
6. **M2.5 是 deferral，不是 cap**：没有淘汰；A 场景物化的纹理在 B 场景不卸载；节省 = 当前尚未使用的纹理；会话越久、用到的越多，节省越少。PNG 物化是 RGBA 4 B/px，理论上可能反超 baseline 的 BC7 DDS；DDS 版（M2.6）不会超过 baseline。
7. **F3 已修**（`b625743`）：ready 代理收到新真实对象时 `copy` 字段（含新 GL id）+ 更新 `TextureLoader.ÔO0000` + 计数 + 限频日志；260mods 菜单冒烟实测触发一次 `graphics/intro/bbplus_boss_splash_intro.png`，`reregistered=1`、`failed=0`。**manual visual 仍 pending user**。
8. **默认仍 off**：`textures.lazy.enabled=false`；A/B 只用 `-Dhypernova.textures.lazy=true/false`。Task 5 未改默认值。

---

## 2. 任务链与门禁

### 2.1 Task 1：只读 spike（`docs/m25-spike.md`）

| 门禁 | 结果 | 证据 |
|---|---|---|
| G1 接线 | PASS | Base / 260mods 均有 queue lambda + lookup hook + `lambda wired`；`summary.queue > 0`；`degraded=0` |
| G2 结构（字面 raw） | **NO-GO** | raw `demand` 21,353–21,418 > 0.20 × 73,446 = 14,689.2 |
| G2 结构（operational） | **PASS（翻转）** | `demandQueued / wouldSkip`：菜单前 1.74–1.75%，会话末 15.98–16.12%，阈值 9,157 |
| G3 中立性 | PASS（warm 对照） | warm 补充 1+1 差 +1.0 s；全部 warm 轮差 +0.95 s（≤1.5 s） |
| G4 正确性 | PASS | 每会话 0 `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError`；agent 0 ERROR |

skip 文件：260mods 73,446 行 / 4,427,771 B；Base 3,112 行 / 146,563 B；`skip_fraction=0.8704`（260mods）。

### 2.2 Task 2：生产实现内部 gate（`-Dhypernova.textures.lazy=true`）

最终 lazy3 轮（修复后）：

| 项 | Base | 260mods |
|---|---:|---:|
| menu_s | 8.0 | 68.7 |
| wiring armed（queue/register/drain/thread） | true/true/true/true | true/true/true/true |
| drained（pending） | 2,330（0） | 45,784（0） |
| skipped / proxies | 2,330 / 2,330 | 45,784 / 45,784 |
| materialized（最后 summary） | 27 | 138 |
| failed / disabled / degraded | 0 / 0 / 0 | 0 / 0 / 0 |
| captures | 1（TitleScreenState） | 1（TitleScreenState） |
| starsector `Failed` / `Verify` / `Class` | 0 / 0 / 0 | 0 / 0 / 0 |

更早一轮 gate：Base menu 12.0 s、260mods menu 78.2 s、materialized 25 / 85；结论相同。Task 2 期间修复了 review F1（wiring gate + drain fail-open）、F2（`loadingThread` 不再缓存 null）、F4（错误路径硬 fail-open）；F3 当时只加诊断计数，Task 5 修复。内部 gate 的一次 260mods 起跑空闲内存为 11.48 GB（低于 12 GB guard，无 OOM）；后续轮次 12.36 / 12.50 GB 仅为报告声明（未归档，不能作为独立证据）。

### 2.3 Task 3：安装集成

- `install_manifest.py` 在 manifest 原子写之后、用**裁剪后的 runtime** 生成同代 `lazy-skip-v1.txt`；Critical 时不写 skip。
- Base：L1/L2/L3 = 185/509/2,612，baked 3,285/3,285，`skip=3,112`（146,563 B，3 列，与 L1 交集 0）；连跑两次 md5 相同。
- `build-mod.sh` 产出的 zip 同时含 `manifest-v1.json` 与 `lazy-skip-v1.txt`；manifest 185/509/2,612，skip 3,112 行。
- 目标测试 8 passed（变异移除 skip 写入 → 红后恢复）。
- 残余（Task 3 review，非阻塞）：manifest/skip 非事务（skip 写失败可能留下跨代 pair）；`build-mod.sh` 的 `dist/` 不主动 `mkdir`；`install-manifest.sh` 静默忽略多余参数。`build-mod.sh` 现在拒绝任何参数（含 `--env`）。

### 2.4 Task 4：同 boot A/B（`tools/m25_ab.py`，warm，交错 C/T）

Warm-up（不计入）：control 62.6 s，`preload=hit`（5 ms / 2,113 条），file index 已加载（223,537 mod entries）。

**协议 3 轮原始值**（`build/m25/ab-result.json`）：

| # | C menu | T menu | C WS MB | T WS MB | C GPU MB | T GPU MB | C free MB | T free MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 64.2 | 52.1 | 11,132.1 | 11,775.2 | 2,584 | 2,250 | 3,566.6 | 3,028.9 |
| 2 | 51.1 | 46.6 | 11,957.1 | 10,815.9 | 2,403 | 1,991 | 4,415.3 | 5,755.0 |
| 3 | 46.1 | 46.6 | 11,074.6 | 10,844.5 | 2,385 | 1,955 | 5,503.3 | 5,895.7 |
| 中位 | **51.1** | **46.6** | 11,132.1 | 10,844.5 | 2,403 | 1,991 | 4,415.3 | 5,755.0 |

**协议外稳态补充 2 对**（手工 smoke，单独 JSON/日志，不改 `ab-result.json`）：

| # | C menu | T menu | C WS | T WS | C GPU | T GPU | C free | T free |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 61.6 | 62.1 | 11,123.7 | 10,924.7 | 2,391 | 1,957 | 5,475.1 | 5,628.8 |
| 5 | 62.6 | 62.1 | 10,937.5 | 10,929.5 | 2,387 | 1,966 | 5,652.0 | 5,626.6 |

**判读（注意 marginal 与成对的区别）**：

- 协议 **marginal** 中位差：menu −4.5 s、WS −287.6 MB、GPU −412 MB、free **+1,339.7 MB（两列各自中位，不是成对收益，不得当收益引用）**。
- **5 对成对差（T−C）**：menu = −12.1 / −4.5 / +0.5 / +0.5 / −0.5 → 中位 **−0.5 s**；WS 4/5 更低，中位 **−199 MB**；GPU **5/5 更低**，中位 **−421 MB**；free 3/5 更高，中位 **+154 MB**。
- C 序列 64.2 → 51.1 → 46.1 明显下行，补充轮又回到 61.6 / 62.6；首轮 C 是离群。C 永远先跑、T 永远后跑，这个顺序本身偏向 T（缓存/预热）。因此“T 没有稳定赢”是更强的阴性证据；**菜单时间收益不成立**。
- 统计强度：n=5（3 协议 + 2 补充），无随机化、无 CI、无 sign test；GPU 是系统级 `nvidia-smi memory.used`（含桌面/浏览器/其它进程），WS 是进程 working set，free 是系统可用物理内存。内存结论只能写成“与 ~400 MB GPU / ~200 MB WS 的下降一致”，不是严格因果。
- 时间对齐（W1）：WS/GPU/free 是**菜单时**采样；`materialized` 是最后一次 10 s summary（约菜单后 0–8 s）。两者不是同一瞬间。

---

## 3. 结构指标与 lazy 计数

5 个 treatment 会话（最后一个 `premain` 之后）：

| 指标 | 值 |
|---|---:|
| queue | 52,604 |
| wouldSkip | 45,785 |
| skipped | **45,784** |
| proxies | **45,784** |
| drained | 45,784 |
| materialized | **91 / 85 / 85 / 85 / 85** |
| deferred / pending / failed / disabled / degraded | **0 / 0 / 0 / 0 / 0** |
| reregistered（F3 前诊断） | 1 / 1 / 1 / 1 / 1 |

- 5 个 control 会话没有 `lazy:` 启动/ summary 行；treatment 的 `wouldSkip` 与 manifest/skip 结构一致。
- 45,785 vs 45,784 的差是 1 条 `TEXTURE_ALPHA_ADDER`：`eligible()` 按设计永不跳过。
- `Loading image`（**PNG 解码计数，DDS 命中静默**，R-M25-2）：control 81 / 75 / 75 / 75 / 75 行，treatment 68 / 57 / 57 / 57 / 57 行。**这是 PNG 计数，不是纹理总数**；结构指标以 agent 的 queue/skip 为准。
- Base lazy=true：`skipped=proxies=2,330`、`materialized=25–27`、`failed=disabled=0`。

---

## 4. 内存

### 4.1 菜单时刻（A/B，n=5）

| 指标 | 成对中位 | 方向一致性 | 口径 |
|---|---:|---|---|
| GPU used | **−421 MB** | 5/5 对更低 | `nvidia-smi --query-gpu=memory.used`，系统级总和 |
| 进程 working set | **−199 MB** | 4/5 对更低（第 1 对 T 高 643 MB） | `GetProcessMemoryInfo.WorkingSetSize` |
| 系统 free physical | **+154 MB** | 3/5 对更高 | `GlobalMemoryStatusEx.ullAvailPhys`；协议 marginal +1,340 不是成对收益 |

### 4.2 菜单后 60 s（Task 5 单轮 treatment，`--linger 60`，固定后 jar）

这不是 A/B；只有 1 轮 treatment，没有同轮 control，绝对时间（menu 74.1 s）受环境漂移影响，不能与 Task 4 的 46–64 s 比较。仅用于回答“菜单后内存会怎么走”。

| 指标 | 菜单时 / 最后一条菜单前 summary | 菜单 +60 s | 变化 |
|---|---:|---:|---:|
| materialized（agent summary） | 76（菜单前 3 s） | 94（菜单 +57…+67 s） | **+18** |
| demandQueued | 798（菜单前 13 s） | 7,322 | +6,524 |
| WS | 10,874.5 MB | 11,094.0 MB | **+219.5 MB** |
| free physical | 4,279.2 MB | 4,095.5 MB | **−183.7 MB** |
| GPU used（外部 5 s 采样，系统级） | 2,090 MB（smoke）/ 2,098 MB（t≈73 s） | 2,205 MB（t≈135 s） | **+107 MB** |

同轮 agent 日志：`refreshed ready proxy graphics/intro/bbplus_boss_splash_intro.png`、`reregistered=1`、`failed=disabled=deferred=pending=0`；starsector 本会话 0 `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError`。

**判读**：

- 菜单后 60 s 只新增 18 次物化（约 0.3 次/秒）；7.3k 是 `demandQueued`（查表命中代理），不是 7.3k 次同步物化。生产实现只在代理首次 bind（`LazyProxyObject.Ø00000/ö00000`）或引擎查表 miss 时物化；大量查表只返回代理对象。
- 但 WS 在 60 s 内回涨 219.5 MB，说明“菜单时省下的 ~200 MB WS”会随会话推进被吃掉；GPU 同轮 +107 MB（系统级、背景负载漂移，只作方向参考）。
- **没有 frame-time / P99 / stutter 数据**。不能从“物化次数少”推断“不会卡”；每次物化仍是主线程同步 `syncLoad`。post-menu burst/stutter 与战斗 A/B 留给 M2.6。

---

## 5. post-menu / I1 状态（明确承接 Task 4 review）

- Task 4 A/B 的 `m25_ab.py` 不传 `--linger`，`smoke_run.py` 默认停留 8 s；每轮在菜单后约 8 s 结束，最后 summary `materialized=85–91`。计划 Review Focus 7 要求测的 post-menu burst/stutter **在 Task 4 没有测**；Task 4 brief 的 `materialized≈7.3k` 与实测 85–91 的差异也来自口径：7.3k 是 `demandQueued`/会话末，materialized 是实际物化数。
- Task 5 补了 1 轮 60 s linger（§4.2），得到菜单后 materialized/WS/free/GPU 的方向性数据；**仍没有测 stutter**。
- 因此 M2.5 的收益表述必须限定为：**菜单时刻的内存占用下降**，不是“启动期总收益”，也不是“战斗/长会话收益”。战斗、读档、分辨率切换下的 burst/stutter 与净收益由 M2.6（DDS + LRU）测量。

---

## 6. 正确性

- **自动**：10 个归档 A/B 会话（5 C + 5 T）每轮 0 `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError`；treatment agent `failed=0 / disabled=0`；Base lazy=true 9.5 s 到菜单、0 异常、`failed=0`。
- **Task 5 linger 会话**：0 `Failed to load texture` / 0 `VerifyError` / 0 `ClassFormatError`；F3 refresh 正常；日志中的 `Weapon spec ... not found in weapon_data.csv` 是包内既有的 mod 数据问题（非纹理、非本组件），网络版本检查 WARN 也是既有现象。
- **manual visual：pending user/controller**。未做 Base + `lazy=true` 的读档 / 战斗 / 分辨率切换目检，也未目检 F3 的 `graphics/intro/bbplus_boss_splash_intro.png`；不标 PASS。
  - 建议步骤：Base 启动加 `-Dhypernova.textures.lazy=true` → 读档 → 进一场战斗 → 切一次分辨率 → 回菜单；检查白块/错位/缺失/黑块，同时看 agent `failed=0` 与 starsector 0 纹理错误。

---

## 7. F3：ready 代理的重注册刷新

**修复前**（Task 4 证据）：每个 260mods treatment 会话 `reregistered=1`，路径固定 `graphics/intro/bbplus_boss_splash_intro.png`，日志为 `re-register seen ... (F3 probe; proxy not refreshed)`；Base 为 0。说明该生命周期路径在菜单启动时确实被触发，代理仍持有旧 `Object`/旧 GL id。

**修复**（`b625743`，`LazyTextures.java`）：

- `onRegister` / `noteEngineHit` 在 `e.ready` 且 `value != e.obj` 时调用 `refreshReady`：
  - `ProxyShape.copy(value, e.obj)`（14 字段，含 `ô00000` GL id）；
  - `putPathCache(path, e.obj)`（`TextureLoader.ÔO0000` 指向代理）；
  - `ProxyEntry.reregistered++`；全局 `reregistered=` 继续进 summary；
  - 同一个真实对象只吸收一次（`lastSource`），避免引擎 map 持续返回该对象时每次查表都做 14 次反射拷贝；
  - 每 path 前 3 次刷新写日志。
- 新增 `LazyRefreshTest`（4 个测试，fixture shape，不依赖游戏类）；`Lazy` 29/29、全量 agent 132 pass + 1 已知 symlink assumption abort + 0 fail、mod 103/103；变异去掉 `copy` → 3 个测试红，恢复后 29/29。`TextureObjectFixture` 增加 `setStringId` 以覆盖字符串 id 拷贝。
- **集成实证**（Task 5 linger，修复后 jar）：`lazy: refreshed ready proxy graphics/intro/bbplus_boss_splash_intro.png from register (F3; reregistered=1, pathReregistered=1)`；`failed=disabled=0`；0 纹理错误。

**残余**：旧 GL id 是否被 `oOoO.Ò00000()` clear 真正删除取决于 FR/游戏实现；若未删除，每次重载会泄漏一个 id。刷新只覆盖“新对象注册”路径，不覆盖“clear 后无人重新注册”的悬空引用；读档/战斗/分辨率仍需 manual visual。

---

## 8. 默认值与回滚

- **默认关闭**：`textures.lazy.enabled=false`（配置缺失/坏配置均为 false）；生产开关只在显式 `-Dhypernova.textures.lazy=true` 或配置 `true` 时开启。Task 5 未改默认。
- **回滚**（任一即可）：
  1. 配置 `textures.lazy.enabled=false`；
  2. 启动参数 `-Dhypernova.textures.lazy=false`；
  3. 删除启动文件中的 `-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar` 行（`python tools/install_agent.py --action uninstall ...`）。
- skip 文件可以保留；关闭后不读取、不跳过、不注册代理，行为回到 M2。回滚不改游戏存档/设置。

---

## 9. 已知限制 / 偏差

1. **口径修正**：Task 4 brief 的 `materialized≈7.3k` 与实际 85–91 不符；7.3k 是 `demandQueued`（会话末查表需求），不是物化数。本文件按实际口径记录。
2. **post-menu burst/stutter**：Task 4 未测；Task 5 只补了 60 s linger 的计数/内存，仍未测 frame-time/P99。不要宣称“无卡顿”。
3. **n=5 / 系统级 GPU**：内存结论是定性方向，不是统计显著；GPU 采样含其它进程。
4. **无淘汰**：M2.5 不设 cap；A 场景物化后在 B 场景不卸载；长会话收益递减（60 s 菜单空闲已见 WS +219.5 MB）。PNG 物化 4 B/px，理论上可反超 BC7 baseline。
5. **版本耦合**：0.98a-RC8 + FR 0.9.7rc2；`wiring armed` 四钩子/shape gate 失败会 fail-open（disabled），但新版本仍需重新验证。
6. **Task 3 残余**：manifest/skip 非事务；`build-mod.sh` 不建 `dist/`；`install-manifest.sh` 忽略多余参数；`tests/tools` 两个既有 `test_smoke_check` 失败与本里程碑无关。
7. **Task 4 工具残余**（review M3–M5/W2/W3）：C/T 接线与聚合无测试；`run_round` 的 `check=True` 单轮失败会中止；归档是累积快照不是单会话切片；N4 的 `loadAsync=false` 只在 fail-open 路径检查（正常 `queue()` 仍忽略返回值，版本漂移 residual）。
8. **环境漂移**：同 boot 内 menu 46–74 s 波动；跨任务/跨 boot 的绝对时间不可直接比较。

---

## 10. 证据文件

- Task 1：`docs/m25-spike.md`、`build/m25/probe-260-p{1..7}.json`、`build/m25/logs/260-*-p*.log`
- Task 2：`build/m25/internal-{base,260}-lazy3.json`、`build/m25/logs/{base,260}-*-lazy3.log`、`.superpowers/sdd/2026-11-01-m25-lazy-textures-addendum/task-2-report.md`、`task-2-review.md`、`task-2-fix-review.md`
- Task 3：`.superpowers/sdd/.../task-3-report.md`、`task-3-review.md`；`tests/tools/test_install_manifest.py`（8 passed）
- Task 4：`build/m25/ab-result.json`、`build/m25/ab-{c,t}{1..3}.json`、`build/m25/extra-{c,t}{4,5}.json`、`build/m25/logs/ab-*.log`、`build/m25/correctness-base-lazy.json`、`.superpowers/sdd/.../task-4-report.md`、`task-4-review.md`
- Task 5：`build/m25/post-menu-t-lazy.json`、`build/m25/post-menu-gpu-series.txt`、`build/m25/post-menu-smoke.out`、`build/m25/post-menu-agent.offset`、`build/m25/installed-backup/`、`.superpowers/sdd/.../task-5-report.md`
- 测试：agent `run-agent-tests.sh`（133 found / 132 pass / 1 symlink assumption abort / 0 fail）；mod `run-tests.sh`（103/103）
- 相关文档：`技术笔记-纹理按需加载.md` §7/§10、`大饼-DDS按需物化与LRU.md`
