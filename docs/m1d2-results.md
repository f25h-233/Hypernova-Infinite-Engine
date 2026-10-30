# M-1d-2 实测结果：缓存 key 清单化

> 日期：2026-10-30
> 环境：Starsector 0.98a + 260mods、Miko Lite（JDK 28）、Lite 内存档（`Miko_Lite.txt`）、`scripts.enabled=true`、热缓存
> 结论：**门禁通过**。3 次热启动 key `took` 中位数 **458 ms**（目标 <1,000 ms）；未变更安装的 key id 保持 `6646f5b61e39bf0e0b1e38e99c723d19`。

## 1. 结论

- 3 次热启动 key 耗时：**452 / 458 / 481 ms**，中位数 **458 ms**，最大值 481 ms。
- 目标 <1,000 ms：**达到**；硬线 <3,000 ms：远低于，无需 `-Dhypernova.keyThreads=1` 对照重跑。
- `scan` 分项 **263 / 278 / 302 ms**，对比旧 `collectFiles` 的 **2,155 ms**（开工前实测），下降约 **86%–88%**。
- key id 三次均为 `6646f5b61e39bf0e0b1e38e99c723d19`，与改造前一致 → 未变更安装没有产生缓存失效。
- `preload` 命中：`entries=2119`，`bytes=8,814,944`，耗时 6–7 ms；`rehash=false`。

## 2. 环境与口径

- 时间：2026-10-30 22:53–22:58（本地 UTC+8；日志 UTC 14:53–14:58，最后一条 14:58:17.995Z）。
- 安装：`Starsector-098-260mods`，冒烟 profile `miko-lite`；启动文件 `Miko_Lite.txt` 当前为 **CRLF**（任务开始前既如此，`install_agent.py` 报 `no vmparams change`，未手工改动）；agent 行位于 `-javaagent:fr.agent.jar` **之前**。
- 内存：计划要求 ≥20 GB；实测任务开始 **16.3 GB**、冒烟前 **17.1 GB**。Controller 在用户关闭应用后接受继续（本机总内存 31.2 GB、无其他重进程）；key 门禁 458 ms 相对 1,000 ms 余量足够，内存噪声不足以改变结论；菜单时间仍不作门禁。
- 计时来源：`saves/hypernova/scripts-agent.log` 的 `cache key ready (background) ... took N ms` 与 `cache key breakdown: ...`；主菜单时间来自 `tools/smoke_run.py` 的 `menu_s`（日志 `Playing music ... main_menu` 锚点）。
- 旧基线（15 次）与新实测（3 次）来自**同一天、同一安装**，但旧基线是改造前的 jar，**不是同一会话内的 A/B**；两者只能作同安装前后对照，不能当作无波动的净收益。

## 3. 旧基线（改造前，15 次启动：14 次 preload 命中 + 1 次 `scripts cache cold`）

来自同一份 `scripts-agent.log` 的既有记录（2026-10-30，改造前 jar）：

| 序号 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `took` (ms) | 8,807 | 3,336 | 4,284 | 6,612 | 7,606 | 3,772 | 14,402 | 8,005 | 14,197 | 12,965 | 6,992 | 11,931 | 5,609 | 13,473 | 4,227 |

- 中位数 **7,606 ms**；最小 / 最大 **3,336 / 14,402 ms**。
- 同一安装、同一天；旧实现每次对 12,330 个文件做 `Files.walk` + 多次 stat。

## 4. 新实测（3 次热启动）

### 4.1 key 耗时与分项

| 轮 | key id | `took` (ms) | files | scan (ms) | load (ms) | refresh (ms) | canonical (ms) | save (ms) | total (ms) | rehash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `6646f5b61e39bf0e0b1e38e99c723d19` | **458** | 12,330 | 263 | 108 | 20 | 57 | 0 | 454 | false |
| 2 | `6646f5b61e39bf0e0b1e38e99c723d19` | **452** | 12,330 | 278 | 110 | 19 | 36 | 0 | 449 | false |
| 3 | `6646f5b61e39bf0e0b1e38e99c723d19` | **481** | 12,330 | 302 | 108 | 18 | 44 | 0 | 476 | false |

- `took` 排序：452 / 458 / 481 → **中位数 458 ms**。
- 分项中位数：scan **278**、load **108**、refresh **19**、canonical **44**、save **0**、total 中位数 **454 ms（449–476）**。
- `save=0` 说明清单无变化时跳过了 3.3 MB JSON 重写（Task 2 的 `saveNeeded()` 路径生效）。
- `took` 与 `total` 的 3–5 ms 差是 `compute` 外层计时与内部分项计时的边界差，不是异常。

### 4.2 预载与 key id

- 三次 `scripts cache preloaded` 均为：`key=6646f5b61e39bf0e0b1e38e99c723d19, entries=2119, bytes=8814944, in 6–7 ms`。
- 任务书预期的 `entries=2113` 是更早的包；日志显示 2026-10-30 21:35–21:36（本地）已有会话在**同一 key** 下把包写成 `2116 → 2117 → 2119` 条（`scripts cache written`），本次冒烟没有重写包（`classes.pack` mtime 仍为 21:36）。因此 **2119 是本次实测值**，不是本任务造成的缓存变化，也不是安装变更（key id 未变）。
- key id 与冒烟前日志最后一条一致（`6646f5b61e39bf0e0b1e38e99c723d19`），未变更安装成立。

## 5. 分项基准（`tools/java/key-bench.sh`，真实安装）

工具在真实 260mods 文件树上直接调用生产类，`cacheRoot` 是 `key-manifest.json` 的临时副本，不写真实缓存。Base JRE 17，5 轮取中位数。

### 5.1 `threads=4`

```text
iter 0: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=227 load=118 refresh=13 canon=48 save=121 total=527
iter 1: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=119 load=72 refresh=10 canon=9 save=0 total=210
iter 2: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=103 load=70 refresh=11 canon=10 save=0 total=194
iter 3: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=93 load=76 refresh=7 canon=12 save=0 total=188
iter 4: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=97 load=69 refresh=4 canon=8 save=0 total=178
median: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=103 load=72 refresh=10 canon=10 save=0 total=194
```

- 第 0 轮 `save=121 ms`：临时副本的条目数（12,330）与基准扫描集（12,308）不同，fresh 清单写了一次；后续轮次 `save=0`。

### 5.2 `threads=1`

```text
iter 0: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=239 load=110 refresh=12 canon=36 save=0 total=397
iter 1: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=194 load=79 refresh=10 canon=10 save=0 total=293
iter 2: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=196 load=75 refresh=11 canon=12 save=0 total=294
iter 3: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=185 load=75 refresh=8 canon=13 save=0 total=281
iter 4: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=180 load=77 refresh=6 canon=11 save=0 total=274
median: files=12308 key=03ac59faf608e2b1d5fe4e8a27c41c19 scan=194 load=77 refresh=10 canon=12 save=0 total=293
```

### 5.3 与游戏内口径的差异（必读）

- 基准 `files=12308`，游戏内 `files=12330`，差 **22**。`KeyBench` 的 `java.class.path` 只有构建 classpath（`build/agent/classes`、Base `json.jar`、`build/keybench/classes`），`ScriptCacheKey.classpathOrder()` 在 `gameRoot` 下过滤后得到 0 个游戏 jar；游戏进程由 `Miko_Lite.txt` 提供 23 个 classpath 条目，其中 `fr.jar` 与显式条目重复，净增 22。与 cwd 或启动文件解析无关。基准因此少扫 22 个文件，耗时略低；**游戏内 12,330 / total 中位数 454 ms（449–476）是准口径**。
- 复查时重跑得到 `threads=4` total **308 ms**、`threads=1` total **469 ms**（files/key 不变），说明 194/293 是单次样本、不是稳定常数；两者都远低于 brief 阈值。
- 基准 `key=03ac59faf608e2b1d5fe4e8a27c41c19` 与游戏 key 不同，因为基准的 canonical 只拼 `path|size|sha256`，**不含** `java=` / `classpath=` / `enabled=` 头部（见 `KeyBench` 源码），且文件集少 22 个。基准 key 只用于确认各轮稳定，不作为安装 key。

## 6. 门禁判定

| 条件 | 阈值 | 实测 | 判定 |
|---|---|---:|---|
| 3 次 `took` 中位数 | < 1,000 ms（目标） | **458 ms** | **通过** |
| 3 次 `took` 中位数 | < 3,000 ms（硬线） | 458 ms | 通过 |
| key id 不变 | `6646f5b6…` | `6646f5b61e39bf0e0b1e38e99c723d19` | 通过 |
| `scan` 明显小于旧 2,155 ms | — | 263–302 ms | 通过 |
| `rehash` | false | false | 通过 |
| `KEY_AWAIT_MILLIS=8 s` 同步兜底 | 不应触发 | 最大 481 ms | 未触发 |

**结论：门禁通过（目标 <1 s 达标）。** 不使用「1,000–3,000 ms 记录但未达标」分支，也不需要串行对照重跑。

## 7. 顺带观察：主菜单时间（不作为本里程碑门禁）

| 轮 | 主菜单 `menu_s` (s) | 墙钟 (s) | preload | 停止方式 |
|---:|---:|---:|---|---|
| 1 | 83.2 | 108.4 | hit 7 ms / 2,119 条 | forced |
| 2 | 77.6 | 102.3 | hit 6 ms / 2,119 条 | forced |
| 3 | 77.1 | 102.2 | hit 6 ms / 2,119 条 | forced |

- 本次 3 轮：83.2 / 77.6 / 77.1 s，中位 77.6 s。
- 历史同安装（M-1b、热缓存）不是只有 85.5 s：同一 A 配置还出现过 **98.2 s**（`docs/m1b-results.md:46`），战斗检查轮为 **76.9 s**（`docs/m1b-results.md:124`）。
- 因此历史分布约 **76.9–98.2 s**，本次中位 77.6 s **落在旧分布内**；**不宣称主菜单时间有提升**。
- 这不是测错，而是结构性的：key 计算从来不在关键路径上（见下）。
- 这是单会话 3 轮的小样本，且包含后台 key、脚本编译、纹理等所有阶段；不能把差值单独归因于本任务。仅作观察，不构成本里程碑门禁。
- 每轮末尾的 miss breakdown 均为 `total=11264, sourceless=3, sourced=11261`，与 M-1b 记录一致。每轮在 oracle/编译开始前也会输出一条 `total=0` 的早期 breakdown，不参与统计。

### 7.1 key 与 preload 的区间重建

| 本地时间 | key 开始 | key 结束 | took | preload 开始 | preload `in` | key 比 preload 早结束 |
|---|---:|---:|---:|---:|---:|---:|
| 20:18 | 20:18:14.083 | 20:18:27.556 | 13,473 ms | 20:18:45.432 | 9 ms | 17.9 s |
| 21:32 | 21:32:11.844 | 21:32:16.071 | 4,227 ms | 21:32:31.254 | 6 ms | 15.2 s |
| 22:53 | 22:53:09.323 | 22:53:09.781 | 458 ms | 22:53:25.431 | 7 ms | 15.7 s |
| 22:55 | 22:55:01.653 | 22:55:02.105 | 452 ms | 22:55:14.170 | 6 ms | 12.1 s |
| 22:56 | 22:56:47.986 | 22:56:48.467 | 481 ms | 22:57:02.255 | 6 ms | 13.8 s |

- 日志是串行事件流，并发不能靠“行有没有交错”判断，只能靠**区间重建**：key 区间 = `[cache key ready 时间 − took, cache key ready 时间]`；preload 区间 = `[scripts cache preloaded 时间 − in, scripts cache preloaded 时间]`。
- `premain` 到 key 开始只差 **24–44 ms**；key 结束比 preload 开始早 **12.1–17.9 s**（本表 5 行；全日志非 cold 会话为 **8.0–27.0 s**）→ key 线程与游戏初始化重叠，且在 FR loader 需要它之前完成。
- `preload` 的 `in N ms` 从 `awaitKey` **之前**开始计时，包含“等待 key + 加载 pack”；本次 key 早已完成，所以 6–9 ms 实际是 pack 加载。若 key 未就绪，这个数会包含等待。要直接看线程身份，需要给 `AgentLog` 加线程名（本任务未做，列为后续可观测性项）。

## 8. 回滚 / 开关

- `-Dhypernova.keyThreads=1`：串行扫描（加在启动参数文件主类行之前，保持该文件原有行尾）。
- `-Dhypernova.rehash=true`：强制全量重算 sha256（绕过 size+mtime 复用）。
- 删除 `saves/hypernova/scripts-cache/key-manifest.json`：下次启动全量重建清单（本次会写一份新清单）。
- 移除启动参数文件中的 `-javaagent:.../hypernova.agent.jar` 行（或 `python tools/install_agent.py --action uninstall ...`）：完全停用 agent。

## 9. 已知限制

- **size+mtime 均未变的内容修改会复用旧 sha256**：这是 spec 记录的已知风险；racy-clean 只保证 `mtime >= savedAt` 的文件重算，`-Dhypernova.rehash=true` 是兜底。本次实测 `rehash=false`，说明 3 轮都走了复用路径，这是预期行为。
- **未采用目录 mtime 剪枝**：NTFS 上修改文件内容不改变父目录 mtime（只有增删/改名才变），目录 mtime 不能检测内容修改；逐文件 `BasicFileAttributes`（串行 443 ms 量级）已足够便宜，再持久化目录清单只会多一个真值来源，没有收益。
- **`KEY_AWAIT_MILLIS=8 s` 超时后同步重算的路径仍在**：它是**性能/可用性兜底**，不是正确性兜底；后台 key 失败时主线程会无超时地同步重跑一次 `compute`。新 key 最大 481 ms，使该路径不触发；若未来文件树显著变大，它仍能保证本次启动可用。
- **扫描 fail-closed 的范围**：`KeyScanner` 的 `walkTree` 源根（`src/`、`jars/`、`data/scripts/`）不可读、或并行扫描任务失败 → 抛异常、本次缓存禁用。**发现级列举**（`mods` 根目录列举、单 mod 根级 `*.jar` 列举、`mod_info.json` 探测）失败仍按旧 `scanModFolders` 行为记日志并跳过该目录——风险低（游戏自身同样读不到该 mod），但不在 fail-closed 保证内；下个里程碑加注入 seam 后收紧。
- **基准与游戏内口径差异**：见 §5.3（12,308 vs 12,330；基准 key 不含头部）。
- **旧基线不是同会话 A/B**：15 次旧值与 3 次新值来自同一天同一安装，但旧值由改造前 jar 产生，中间有安装/构建与系统状态变化；只能作前后对照。
- **测试环境限制**：Windows 当前账户无创建符号链接特权，`KeyScannerTest.symlinkToFileFollowsLegacySemantics` 以 assumption 中止（不是失败）；`tests/tools/test_smoke_check.py` 的 2 条 M-1d 遗留失败仍在，记为 deferred，非本任务引入。
- **旧格式 object 清单不会被升级**：`savedAt>0` 但无 `jvmJava`/`jvmClasspath` 的旧格式清单，在输入不变时不会被升级；`CacheTool key --verify` 会持续报 `jvm_match: n/a`。只影响诊断证据，不影响 key 正确性；任一次输入变化后自愈。
- **`CacheTool` 把 `jvm_match: n/a` 当通过**：与自身 javadoc 矛盾——M-1d 已知遗留，不在本里程碑修。

## 10. 测试结果（2026-10-30）

| 套件 | 结果 |
|---|---|
| `bash tools/java/run-agent-tests.sh` | 64 发现，63 通过，0 失败，1 中止（符号链接特权 assumption） |
| `bash tools/java/run-tests.sh` | 95/95 通过 |
| `python -m pytest tests/tools -q` | 142 通过，2 失败（`test_jar_provenance_detects_mismatch`、`test_provenance_mismatch_fails_without_skip`，已知 M-1d 遗留，deferred） |
