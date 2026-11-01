# M2.7 结果：有界 LRU 默认开启资格（default-on readiness）

- **日期**：2026-11-02（本地；实机会话 UTC 2026-11-01 20:11–21:03）。
- **宿主/配置**：Windows 11 中国区；`Starsector-098-260mods`（`miko-lite`，JDK 28 启动档）+
  `Starsector-098-Base`；HEAD `8e6be81`（Task 7 后）。
- **验证方式**：仅**菜单锚点**（`Playing music with id [miscallenous_main_menu.ogg]`）+
  agent summary + `starsector.log` 会话切片。**不是战斗/读档/分辨率/长会话验收**。
- **状态**：**代码侧 default-on gates 已关闭；默认仍 off**
  （`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`）。
  **用户战斗/读档/分辨率/手动目检、A→B 长会话净 VRAM、>200 ms 卡顿仍 pending**，
  清单见 `docs/m27-manual-acceptance.md`。**未 push。**

### R-M27-9（门禁修复，必须和 M2.6 数字分开读）

Task 1 后预算只比较**可淘汰字节**（`live - startup - foreign`）。260mods 菜单的整个可淘汰集合
约 **0.52–0.65 MiB**（550,084–681,660 B；0.55–0.68 是十进制 MB），因此 `budgetMb=1`
（1 MiB = 1,048,576 B）会让 `evictPass` 在预算内早退，
`evictPasses=0` 是**结构性正确结果**，不是自动淘汰路径失效。M2.6 的 `evictPasses=69` 是旧
“总 `LIVE_BYTES`”口径下的 churn，不能与 M2.7 直接比较。

Task 7（`8e6be81`）新增内部诊断属性
`-Dhypernova.textures.lazy.eviction.budgetBytes=<bytes>`（**不是用户配置**；默认行为不变），
并在 summary 增加 `budgetBytes`。用 **256 KiB** 覆盖后，自动 pass 可达并通过门禁。
1 MiB 的 no-pass 证据保留在 `build/m27/fix-auto-1mb.json`。

---

## 1. 结论

1. **预算口径已修**（`2d17977`）：`LIVE_BYTES` 仍是总报告口径；预算只比较
   `evictable = live - startup - foreign`。实机 summary 同时输出
   `startupBytes`/`foreignBytes`/`evictableBytes`/`budgetBytes`，恒等式在 selftest、A/B、
   linger120 全部成立。菜单/默认预算下 `evictPasses=0` 符合预期。
2. **R-M27-9 门禁修复已验证**（`8e6be81`）：1 MiB 下 `evictableBytes` 最大 615,034 <
   1,048,576，`evictPasses=0`（结构性 no-pass）；256 KiB 下 `evictPasses=361`、
   `evicted=1803`、`rematerialized=1776`、`evictPassMsMax=7 ms`、0 errors，自动 pass 与
   selftest 同时成立。
3. **淘汰安全**（`ae56ac8` + `e828055`）：`evictOne` 去掉 `force` 并在 `synchronized(e)` 内
   二次校验（W-5）；二次失败停车到共享占位（W-10），实机 `failedParked=0`；
   `oldIdDeleted` 现在包含成功的淘汰删除；DDS commit/handler/path-cache 用
   `synchronized(loader)` 做 FR 漂移防御（W-7）。
4. **DDS fallback 可诊断**（`37899bf` + `bc886c8`）：10 个 `ddsFb*` 原因计数；
   最后稳定 summary 的 sum(`ddsFb*`) == `ddsFallback`（本轮所有门禁均相等）。
   自 M2.7 起 `BRIDGE` 也计入 `ddsFallback` 总数；M2.6/M2.7 的 `ddsFallback` 只在
   `ddsDisabled=0` 时可直接比较。
5. **发行/agent 门禁**（`40dd39c`）：release zip 校验 manifest/skip generation、README、
   无宿主 `lazy-skip-v2.txt`、agent jar 逐 entry 一致；`build-mod.sh` 强制重建 agent jar
   并检查新鲜度。M2.5 W5（mod 集）为 documented + fail-open，W6（jar 新鲜度）为 fixed。
6. **默认预算 selftest 回归通过**：`selftest=1/evicted=1/rematerialized=1`，
   `startupBytes=5,522,052`、`foreignBytes=8,388,608`、
   `evictableBytes=550,084`（恒等式成立），0 errors，gates 全 true。
7. **counterbalanced 菜单 A/B n=3 完成**（split 2+1）：C 中位 **71.6 s**、T 中位
   **69.6 s**、paired 中位 **−2.0 s**（−4.5/−1.0/−2.0）。**不写时间收益**：delta 落在
   历史噪声/边界内，无显著性检验。逐进程 GPU dedicated **3/3 treatment 更低**
   （927.0 vs 496.6/494.5/496.5 MB）；`ddsHit` 中位 27、`ddsFallback` 2（全 META）。
   所有 A/B 会话 0 Failed/Verify/Class/Async/Corrupted。
8. **linger120 回归通过**：默认 256 MB 预算下 `evictPasses=0`（可淘汰 4,383,781 B <<
   268,435,456 B，符合预期）；`startupBytes` 未增长（仍 5,522,052），
   `evictableBytes` 恒等式成立；0 errors；`evictPassMsMax=0`（无 pass）。
9. **默认/回滚不变**：两侧 `hypernova.json` 没有 `textures.lazy` 键；A/B 开关全部走 `-D`；
   回滚仍是配置 false / `-Dhypernova.textures.lazy=false` / 删除 agent 行。
10. **未 push**；Tasks 1–5、7 与本 docs 提交均留在本地。

---

## 2. 代码变化与测试

| Task | Commit | 测试（报告口径） | 关键行为 |
|---|---|---|---|
| 1 预算口径 | `2d17977` | LazyEviction 17/17；LazyRefresh 6/6；full agent 176 found / 175 pass / 1 known abort / 0 fail；pytest 287 | `evictableBytes(live,startup,foreign)`、`ByteClass`、`startupBytes`/`foreignBytes`/`evictableBytes`/`emptyEvictPasses`/`evictPassMsTotal`/`evictPassMsMax`；startup/foreign 不计入预算 |
| 2 淘汰安全 | `ae56ac8` + `e828055` | LazyEviction 20/20（含 R-M27-6 纯门）；LazyRefresh 6/6；full agent 179 found / 178 pass / 1 abort / 0 fail；pytest 287 | `evictOne(e)` 无 force、`synchronized(e)` 二次校验；`parkFailedProxy`；`failedParked`；`oldIdDeleted` 含淘汰删除；`synchronized(loader)` |
| 3 DDS 原因 | `37899bf` + `bc886c8` | LazyEviction 22/22；full agent 181 found / 180 pass / 1 abort / 0 fail；pytest 298（共享 main 时点） | 10 个 `DdsFallbackReason` + `ddsFb*`；sum == `ddsFallback`；`ddsDimMismatch` 语义不变 |
| 4 发行门禁 | `40dd39c` | pytest 293（287 + 6 release_check）；`build-mod.sh` OK | `release_check.py`、`README-install.txt`、强制重建/新鲜度/zip 校验 |
| 5 A/B 工具 | `196e090` + `7de2cc6` | pytest 298 → 299（12 个 m26_ab 测试） | 缺日志/超时 fail-closed、`--no-dds`、`--counterbalance`、per-run 路径 |
| 7 诊断预算 | `8e6be81` | full agent 182 found / 181 pass / 1 known abort / 0 fail；pytest 299 | `budgetBytes(long,long)` 纯函数、诊断属性 `budgetBytes`、summary 新键 |
| 6 文档 | 本提交 | 回归见 §7 | `docs/m27-results.md`、`docs/m27-manual-acceptance.md`、m26 §7.15/技术笔记/大饼回写 |

已知 abort 仍是 Windows 无符号链接权限导致的 `KeyScannerTest` symlink 用例；不是失败。
默认值、配置键、`hypernova.json`、`enabled_mods.json` 均未改。

---

## 3. 实机门禁

### 3.1 1 MiB（R-M27-9 前的结构性 no-pass，HEAD `7de2cc6`）

命令：`tools/smoke_run.py --profile miko-lite --rounds 1 --linger 30`，`lazy=true`、
`dds=true`、`eviction=true`、`budgetMb=1`、`graceMs=0`、`sceneDelayMs=100`、`selftest=true`。

证据：`build/m27/fix-auto-1mb.json`、agent log 最后 session（15 条 summary）。

| Counter | 值 |
|---|---:|
| `menu_s` / `wall_s` | 97.7 / 152.6 |
| `selftest` | 1 |
| `evictPasses` | **0** |
| `evicted` / `rematerialized` | 1 / 1（**selftest 直调**，非自动 pass） |
| `placeholder` | 15165 |
| `failed` / `disabled` / `dimMismatch` / `failedParked` | 0 / 0 / 0 / 0 |
| `evictPassMsTotal` / `evictPassMsMax` | 0 / 0 |
| `liveBytes` | 14,525,694 |
| `startupBytes` | 5,522,052 |
| `foreignBytes` | 8,388,608 |
| `evictableBytes` | **615,034**（max over 15 summaries = 615,034） |
| `budget`（`budgetMb=1`） | **1,048,576** |
| `ddsHit` / `ddsFallback` | 86 / 2（Meta=2） |
| `ddsDisabled` / `ddsDimMismatch` | 0 / 0 |
| `oldIdDeleted` / `evictSkipped` | 1 / 0 |
| 0 Failed/Verify/Class/Async/Corrupted | 0/0/0/0/0 |
| `lazy: eviction pass` log 行 | **0** |

结论：`615,034 < 1,048,576` → `evictPass` 早退、不 arm、不计数。这是 Task 1 预算口径下的
**正确 no-pass**，也是 R-M27-9 要修复的门禁 recipe；不是淘汰缺陷。

### 3.2 256 KiB 诊断预算（R-M27-9 gate repair，HEAD `8e6be81`）

命令：同 3.1，但用
`-Dhypernova.textures.lazy.eviction.budgetBytes=262144` 替代 `budgetMb=1`；其余不变。

证据：`build/m27/fix-auto.json`、agent log 最后 session（11 条 summary）、
`starsector.log` 会话切片（跨旋转的两段合计 **2,264,147 B**，≈2.26 MB；与 2,264,095 B 的
52 B 差来自提取边界/换行处理）。

下表是 **最后 10 s summary 快照**（20:37:55.647），不是进程退出总计。进程为强制退出，
没有 shutdown summary；全会话 log 在该快照后另有 25 条 `lazy: eviction pass` 行
（+147 evictions / +8,173,976 B），因此退出时约 **386 passes / ~1,950 evictions**。

| Counter | 值 |
|---|---:|
| `menu_s` / `wall_s` | 60.2 / 114.2 |
| `selftest` | 1 |
| `budgetBytes` | **262,144** |
| `evictPasses` | **361** |
| `evicted` / `rematerialized` | **1,803 / 1,776** |
| `placeholder` | 15165 |
| `failed` / `disabled` / `dimMismatch` / `failedParked` | 0 / 0 / 0 / 0 |
| `evictPassMsTotal` / `evictPassMsMax` | 641 / **7 ms** |
| `emptyEvictPasses` | 0 |
| `liveBytes` | 14,364,522 |
| `startupBytes` | 5,522,052 |
| `foreignBytes` | 8,388,608 |
| `evictableBytes` | 453,862（max over 11 summaries = 798,544） |
| `ddsHit` / `ddsFallback` | 1,110 / 724（**全部 META**；`ddsDisabled=0`） |
| `oldIdDeleted` / `evictSkipped` | 1,803 / 0（成功淘汰删除全部计数） |
| 0 Failed/Verify/Class/Async/Corrupted | 0/0/0/0/0 |
| `lazy: eviction pass` log 行 | **386**（全会话 log 行数，不是 summary 值；快照 361 + 之后 25） |

读法：

- 256 KiB 低于菜单可淘汰集合，自动 pass 可达；最后 summary 的
  `evictableBytes=453,862 > 262,144` 说明快照处于 churn 中，不是失败。
- `evictPassMsTotal=641 ms` / `Max=7 ms` 是**菜单主线程 pass** 旁证，**不是逐帧 P99**；
  >200 ms 卡顿仍需手动验收。
- `evictPass` 日志的 `live=` 是 **evictable bytes**（不是总 `liveBytes`）。
- `emptyEvictPasses` 不统计 `live <= budget` 的早退；本轮 0 表示没有“进入 pass 但 0 victim”。
- `ddsFallback=724` 全部 META 是强制 churn 下重复物化“无 DDS 元数据 → PNG 回退”的累积，
  `ddsDisabled=0`，不是淘汰缺陷；不得把它与 M2.6 的 2 直接比较（R-M27-8）。

### 3.3 默认预算 selftest 回归

命令：`tools/m26_ab.py --profile miko-lite --rounds 1 --linger 20 --eviction --selftest
--out build/m27/selftest.json`（默认预算 256 MB）。

证据：`build/m27/selftest.json`、`build/m26/logs/ab-c1.log` / `ab-t1.log`。

| Counter | Control | Treatment |
|---|---:|---:|
| `menu_s` | 70.6 | 71.1 |
| `ws_menu_mb` | 11145.1 | 10915.1 |
| `gpu_process_dedicated_mb` | 927.0 | 496.6 |
| `failed/verify/class/async/corrupted` | 0/0/0/0/0 | 0/0/0/0/0 |

Treatment `lazy_median`：

| Counter | 值 |
|---|---:|
| `selftest` / `evicted` / `rematerialized` | 1 / 1 / 1 |
| `budgetBytes` | 268,435,456（默认 256 MB） |
| `evictPasses` / `emptyEvictPasses` / `evictPassMsMax` | 0 / 0 / 0（默认预算无压力，符合预期） |
| `startupBytes` | 5,522,052 |
| `foreignBytes` | 8,388,608 |
| `evictableBytes` | 550,084 |
| `liveBytes` | 14,460,744 |
| `evictable == live-startup-foreign` | 14,460,744 − 5,522,052 − 8,388,608 = **550,084** |
| `ddsHit` / `ddsFallback` | 27 / 2（Meta=2） |
| `ddsDisabled` / `ddsDimMismatch` | 0 / 0 |
| `failed` / `disabled` / `dimMismatch` / `failedParked` | 0 / 0 / 0 / 0 |
| `placeholder` / `oldIdDeleted` | 15165 / 1 |

`gates` 全 true：`all_rounds_ok`、`logs_present`、`no_texture_errors`、
`treatment_failed_zero`、`treatment_disabled_zero`、`treatment_dim_mismatch_zero`、
`treatment_dds_disabled_zero`、`treatment_dds_hit_positive`、`selftest_ok`。

### 3.4 linger120（默认预算）

命令：`tools/smoke_run.py --profile miko-lite --rounds 1 --linger 120`，`lazy=true`、
`dds=true`、`eviction=true`（默认 256 MB / grace 10 s / sceneDelay 2 s）。

证据：`build/m27/linger120.json`、agent log 最后 session（20 条 summary）。

| Counter | 值 |
|---|---:|
| `menu_s` / `wall_s` | 67.6 / 206.7 |
| `evictPasses` / `evicted` / `rematerialized` | **0 / 0 / 0**（默认预算无压力，符合预期） |
| `emptyEvictPasses` / `evictPassMsMax` | 0 / 0 |
| `budgetBytes` | 268,435,456 |
| `liveBytes` | 18,294,441 |
| `startupBytes` | **5,522,052**（未因 linger 增长） |
| `foreignBytes` | 8,388,608 |
| `evictableBytes` | 4,383,781（恒等式成立） |
| `materialized` / `ddsHit` | 336 / 269 |
| `ddsFallback` | 2（Meta=2） |
| `ddsDisabled` / `ddsDimMismatch` | 0 / 0 |
| `failed/disabled/dimMismatch/failedParked` | 0/0/0/0 |
| `placeholder` / `oldIdDeleted` | 0 / 0（无淘汰） |
| 0 Failed/Verify/Class/Async/Corrupted | 0/0/0/0/0 |
| `lazy: eviction pass` log 行 | 0 |

读法：120 s 后 `evictableBytes` 从菜单约 0.55 MB 增长到 **4.38 MB**，但仍远小于
256 MB，故 `evictPasses=0` 是预期；`startupBytes` 没有把 `evictableBytes` 推高。
没有出现异常大的 `evictPassMsMax`（无 pass）。

---

## 4. counterbalanced 菜单 A/B（n=3）

**运行方式与 split（必须读）**：单次 `--rounds 3 --counterbalance` 预计约 11 min，
超过单次 Bash 10 min 上限，因此拆成 **2+1**：

- `build/m27/ab-part1.json`：rounds 1–2（order **C→T**、**T→C**）；
- `build/m27/ab-part2.json`：round 3（order **C→T**）；
- 合计 **n=3**，六次会话，顺序 **C→T / T→C / C→T**，未改变 n。

Flags：`lazy=true`、`dds=true`、`eviction=false`、`selftest=false`（默认预算；与 M2.6
菜单 A/B 同口径）。`build/m27/ab.json` 是按同一 `median` 定义从两个 part 文件 +
三个 treatment summary 合并的聚合证据（含 `split` 元数据）。

### 4.1 逐轮

| # | Order | C menu | T menu | paired Δ | C GPU ded | T GPU ded | C WS | T WS | T `ddsHit` | T `ddsFallback` | T `evictableBytes` |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | C→T | 73.6 | 69.1 | −4.5 | 927.0 | 496.6 | 11130.9 | 10959.1 | 27 | 2 | 551,768 |
| 2 | T→C | 70.6 | 69.6 | −1.0 | 927.0 | 494.5 | 11158.9 | 10949.7 | 25 | 2 | 549,548 |
| 3 | C→T | 71.6 | 69.6 | −2.0 | 927.0 | 496.5 | 11144.9 | 11011.5 | 28 | 2 | 681,660 |

- **C 中位 71.6 s；T 中位 69.6 s；delta −2.0 s；paired −4.5/−1.0/−2.0，paired 中位 −2.0 s。**
- **不写时间收益**：delta 在历史噪声/边界内（M2.6 修后为 +2.0 s 边界），无随机化/显著性检验。
- **逐进程 GPU dedicated：T 3/3 更低**（927.0 vs 496.6/494.5/496.5 MB）；WS 也 3/3 更低
  （约 −0.17 GB）。这是菜单时刻快照，不是长会话净 VRAM。
- `ddsHit` 27/25/28，`ddsFallback` 2/2/2（全部 META），`ddsDisabled=0`，
  `ddsDimMismatch=0`；`failed/disabled/dimMismatch/failedParked=0`。
- A/B 默认预算下 `evictPasses=0`（`eviction=false`）；本 A/B 不评价淘汰路径，淘汰证据在 §3.2。

### 4.2 `lazy_median`（三次 treatment summary 的中位）

| Key | 中位 |
|---|---:|
| `budgetBytes` | 268,435,456 |
| `startupBytes` / `foreignBytes` / `evictableBytes` | 5,522,052 / 8,388,608 / 551,768 |
| `liveBytes` | 14,462,428 |
| `dds` / `ddsHit` / `ddsFallback` | 1 / 27 / 2 |
| `ddsFbMeta` / 其余 `ddsFb*` | 2 / 0 |
| `ddsDisabled` / `ddsDimMismatch` | 0 / 0 |
| `failed` / `disabled` / `dimMismatch` / `failedParked` | 0 / 0 / 0 / 0 |
| `evictPasses` / `evicted` / `rematerialized` | 0 / 0 / 0（`eviction=false`） |
| `materialized` / `drained` / `skipped` / `proxies` | 94 / 45,784 / 45,784 / 45,784 |
| `index` / `queue` / `wouldSkip` | 73,447 / 52,604 / 45,785 |

### 4.3 A/B gates 与工具限制（必须披露）

`build/m27/ab.json` 的 gates 全 true：`all_rounds_ok`、`logs_present`、
`no_texture_errors`、`treatment_failed_zero`、`treatment_disabled_zero`、
`treatment_dim_mismatch_zero`、`treatment_dds_disabled_zero`、
`treatment_dds_hit_positive`、`selftest_ok`。

**工具限制**：`tools/m26_ab.py` 在每轮**两侧都跑完后**从 agent log 取 lazy summary；
第 2 轮是 T→C，最后一个是 control（lazy=false，无 summary），所以
`ab-part1.json` 的 `lazy_median=null`、`treatment_dds_hit_positive=false`。这是
`stats_from_text` 的抓取时点问题，不是 DDS 失败。三个 treatment session 的
summary（`scripts-agent.log`）分别给出 `ddsHit=27/25/28`、`ddsFallback=2/2/2`、
`ddsDisabled=0`，因此合并后的 `ab.json` 把该 gate 记为 true。建议后续修
`m26_ab.py`：treatment 跑完立即抓一次 stats，不要等 control。

**错误计数**：六个归档会话切片（`build/m27/logs-part1/`、`logs-part2/`）各自
0 `Failed to load texture`、0 `VerifyError`、0 `ClassFormatError`、0 `AsyncException`、
0 `isStateCorrupted`；每片都有 1 个 FR anchor + 1 个 menu anchor。

---

## 5. 默认开启资格矩阵

| Gate | 状态 | 证据 |
|---|---|---|
| 预算口径（startup/foreign 排除） | **fixed** | Task 1 `2d17977`；实机 `startupBytes`/`foreignBytes`/`evictableBytes`；恒等式在 selftest/A/B/linger120 成立 |
| R-M27-9 预算门禁 recipe | **fixed/closed** | `8e6be81`；1 MiB no-pass（615,034 < 1,048,576）+ 256 KiB pass（`evictPasses=361`、`evicted=1803`、`rematerialized=1776`、`evictPassMsMax=7 ms`） |
| W-5 pick→evict TOCTOU | **fixed** | Task 2 `ae56ac8`/`e828055`；`evictOne` 无 force + `synchronized(e)` 二次校验；单测 |
| W-10 失败物化 id=0 | **fixed** | Task 2 `parkFailedProxy` + `failedParked`；实机 0；残余：`blank.png` 缺失时失败代理仍可能绑定 id 0（安装器断言 blank.png） |
| W-4 ddsFallback 盲区 | **closed（可诊断）** | Task 3 `37899bf`/`bc886c8`；10 个 `ddsFb*`，sum == `ddsFallback`；R-M27-8：`BRIDGE` 计入总数，M2.6/M2.7 仅在 `ddsDisabled=0` 时可直接比较 |
| W-7 DDS commit 监视器 | **defensive fixed** | Task 2 `synchronized(loader)`；**R-M27-7：仍存在潜在 loader→e 反向路径**（FR `commitAndCacheTexture` → `oOoO.super` → `onRegister`），不得声称“无反向锁路径” |
| 30 s empty-pass backoff | **open/unexercised** | 所有实机 emptyEvictPasses=0；Task 1 预算口径消除了 startup-bytes 空转根因；真实长会话空 pass/backoff 行为仍需用户/压力验收 |
| M2.5 W5 发行包 mod 集 | **documented + fail-open** | Task 4 `40dd39c`；`README-install.txt` + `release_check`；generation/尺寸不符 fail-open |
| M2.5 W6 agent jar 新鲜度 | **fixed** | Task 4 `40dd39c`；`build-mod.sh` 强制重建/新鲜度/release_check；`install_agent.py` 先复制 jar 再早退 |
| refcount / REQ-R1-10 | **not implementable**（无全局注册表） | owned-only + 失败停车 + 文档；本轮不实现 |
| 第三方 id 缓存（W-3） | **residual** | owned-only + 文档；mod 若把 GL id 拷进自有结构，淘汰后仍可能持有已删 id |
| GL context 重建（W-2） | **user gate** | 分辨率/全屏/alt-tab 手动验收；context 重建可能作废占位 id |
| 战斗/读档/分辨率/手动目检 | **user gate** | `docs/m27-manual-acceptance.md` |
| A→B 长会话净 VRAM | **user gate** | 手动；本轮只有菜单时刻 GPU 快照 |
| >200 ms 卡顿 | **user gate** | 手动 + `evictPassMsMax` 仅菜单主线程旁证 |
| 默认预算 selftest | **pass** | `selftest=1/evicted=1/rematerialized=1`；`startupBytes=5,522,052`；恒等式；0 errors |
| counterbalanced A/B n=3 | **pass（带工具 caveat）** | C 71.6 / T 69.6 / paired −2.0（边界，不称收益）；GPU ded T 3/3 更低；`ddsHit` 中位 27；0 errors；§4.3 工具限制 |
| linger120 默认预算 | **pass** | 0 errors；`evictPasses=0`（预期）；`startupBytes` 未增长；恒等式 |

---

## 6. 剩余 user gates

以下**未做，不标 PASS**：

1. **战斗 5–10 min**：0 `Failed to load texture` / `VerifyError` / `ClassFormatError` /
   `AsyncException` / `isStateCorrupted`；记录 `evictPasses/evicted/rematerialized/
   evictPassMsMax/failedParked/ddsFallback` 及原因分解；主观记录 >200 ms 卡顿次数。
2. **读档/存档**：读档两次、存档一次；无白块/错位/崩溃；记录 `dimMismatch`、`reregistered`。
3. **分辨率/全屏/alt-tab**：1707×1067 → 2560×1440 → 返回；确认占位纹理不残留（W-2）；
   若 lazy 因 `dimMismatch` 自动禁用，记为 fail-open，不是崩溃。
4. **A→B 长会话**：A 场景 10 min → B 场景 10 min；记录逐进程 GPU dedicated 曲线与
   `liveBytes`/`evictableBytes` 漂移；本轮菜单快照不能替代。
5. **>200 ms stutter**：逐帧/P99 未测；`evictPassMsMax=7 ms` 只是 256 KiB 压力下菜单
   主线程 pass 的旁证。
6. **W-2/W-3/refcount**：GL context 重建占位、第三方 id 缓存、引用计数仍 open/residual；
   见矩阵。

---

## 7. 默认 / 回滚 / 文件

- **默认值不变**：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`；
  `textures.lazy.dds=true` 仅在 lazy 开启时生效；`selftest=false`。两侧 `hypernova.json`
  没有 `textures.lazy` 键；A/B/门禁开关全部走 `-D`。
- **回滚**（任一即可）：配置 `textures.lazy.enabled=false`（或单独
  `textures.lazy.eviction.enabled=false`）；`-Dhypernova.textures.lazy=false`；删除启动
  文件中的 `-javaagent:.../hypernova.agent.jar` 行。skip v1/v2 可保留。
- **诊断预算**：`-Dhypernova.textures.lazy.eviction.budgetBytes=<bytes>` 只用于内部
  门禁/诊断，不写进用户配置；默认仍是 `budgetMb=256`。
- **代码/测试**：`src/agent/java/hypernova/agent/textures/LazyTextures.java`、
  `LazyTextureConfig` 相关；`tests/agent/java/...`；`tools/{release_check.py,m26_ab.py,
  install_manifest.py,install_agent.py}`；`tools/java/{build-mod.sh,README-install.txt}`。
- **实机证据**（`build/` 不入库）：`build/m27/fix-auto-1mb.json`、`fix-auto.json`、
  `selftest.json`、`ab-part1.json`、`ab-part2.json`、`ab.json`、`linger120.json`；
  `build/m27/logs-part1/`、`logs-part2/`；`build/m26/logs/` 的 selftest 切片；
  `Starsector-098-260mods/saves/hypernova/scripts-agent.log`；
  `Starsector-098-260mods/starsector-core/starsector.log`。
- **本 docs 提交**：`docs(m27): record default-on readiness gates and manual acceptance`；
  不 push。

---

## 8. 限制

1. **菜单 only**：所有自动化证据都只到主菜单锚点；没有战斗/读档/分辨率/长会话/手动目检，
   不标 PASS。
2. **A/B split 2+1**：单次 n=3 超过 10 min 上限；顺序保持 C→T/T→C/C→T、n=3 不变，
   但两次调用之间不是同一进程；`ab.json` 是合并聚合。时间 delta **−2.0 s 仅按边界记录，
   不称收益**。
3. **A/B 工具抓取时点**：T→C 轮最后是 control，`m26_ab.py` 的 `lazy_median=null`，
   `ab-part1.json` 的 `treatment_dds_hit_positive=false` 是工具假阴性；已用三个 treatment
   summary 复核为 true。后续应修工具。
4. **`ddsBytes` 是 1 B/px 估算**（BC7 level 0），不含 mip；`liveBytes`/`evictedBytes`
   是估算值，不是 VRAM 测量。
5. **`evictPassMsMax` 仅菜单主线程 pass 旁证**，不是逐帧 P99；战斗/长会话 stutter 未测。
6. **R-M27-7**：新增 DDS loader 锁沿用既有顺序风险；FR `commitAndCacheTexture` 在 loader
   监视器内调 `oOoO.super` → `onRegister` → `synchronized(e)`，存在**潜在 loader→e**
   反向路径（对 `materializeDds`/`putPathCache` 的 e→loader）。当前生命周期下 latent，
   但文档不得写“无反向锁路径”。
7. **R-M27-8**：`BRIDGE` 自 M2.7 起计入 `ddsFallback` 总数；M2.6/M2.7 的 `ddsFallback`
   只在 `ddsDisabled=0` 时可直接比较；`noteDdsFallback` 的 total/per-reason 两次递增非原子，
   **最后一条稳定 summary** 的 sum 校验可接受瞬时 ±1（本轮实测全部相等）。
8. **计数语义**：`oldIdDeleted` 现在包含成功的淘汰删除；`evictPass` 日志 `live=` 是
   evictable bytes；`emptyEvictPasses` 不统计 `live <= budget` 的早退；`evicted` 是代理
   复位成功条数，不是“VRAM 已释放量”。
9. **1 MiB 结构性 no-pass**：菜单可淘汰集合约 **0.52–0.65 MiB**（550,084–681,660 B；
   0.55–0.68 是十进制 MB）< 1 MiB；默认 256 MB 预算下
   菜单/linger120 `evictPasses=0` 是预期，不是缺陷。自动 pass 只在 256 KiB 诊断覆盖下验证。
10. **W-10 残余**：`blank.png` 缺失时，失败代理仍可能绑定 id 0；安装器两侧断言
    `blank.png` 非空（70 B），但运行期缺失仍是 residual。
11. **refcount/W-3/W-2**：无全局注册表，refcount 不可实现；第三方 id 缓存与 GL context
    重建仍是 residual/user gate。
12. **不开默认、不对外称“可选显存优化”**：在用户战斗/读档/分辨率/手动、A→B、stutter
    全部通过前，保持 experimental / 默认 off。
13. **“0 errors” 是五类模式门禁**：`Failed to load texture` / `VerifyError` /
    `ClassFormatError` / `AsyncException` / `isStateCorrupted`；检查切片中仍有 297 条
    GraphicsLib `TextureData` 基线 WARN/ERROR（mod 加载期噪声），两切片相同，不计入。
14. **空 pass 30 s backoff 未触发**：所有实机会话 `emptyEvictPasses=0`，backoff 分支只有
    代码/单测；真实长会话的空 pass/backoff 行为仍需用户/压力验收。
15. **`ab.json` 是手工聚合**：`tools/m26_ab.py` 当前抓取时点无法重新生成它；provenance 是
    `ab-part1.json` / `ab-part2.json` 原始 JSON + 三个 treatment summary（见 §4.3）。
16. **M-6 `parkFailed` 线程边界**：`parkFailed` 可由 loading thread 进入（materialize catch）；
    `shape.reset` 是反射调用，`syncLoad` 本就是 loading-thread 路径，但这偏离 plan 的
    “placeholder reset only on runtimeMain” 措辞；风险 latent，未加 main-thread gate。
