# M3.1（索引 save 异步化）结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2；agent jar `8a4f4f4d`（sha256 前 8 位）；索引格式 v2（未改）

## 1. 改动
- `FileIndexHook.save` 改为 daemon 线程调度（快照 + `.tmp` + 原子 rename + MIN_PRIORITY）。
- 目录 mtime 晚于 crawl 结束时间 → 放弃本次写盘（fail-open）。
- `dirs` 增加目录自身路径（空叶子目录失效硬化）。
- 未改 `FileIndex.VERSION` / 序列化布局 / transformer / 回滚开关。

## 2. 首次构建 A/B（同日 `miko-lite` warm，交错 3+3，warm-up 不计）
| 轮 | control menu_s（`fileIndex=false`） | treatment menu_s（每轮删索引） |
|---|---:|---:|
| 1 | 56.6 | 57.6 |
| 2 | 55.6 | 57.6 |
| 3 | 55.1 | 57.1 |
| 中位 | **55.6** | **57.6** |

- `delta_s = -2.0`（`tools/m3_ab.py` 口径：control 中位 − treatment 中位；负值 = treatment 更慢；`delta_pct = -3.6%`）。等价地，首次构建相对同日 control 的一阶成本为 **+2.0 s**（55.6 → 57.6 s）。M3 同步 save 的历史一次性成本为 **+15.1 s**（68.1 → 83.2 s；**pre-reboot、不同 boot/时段（与 M3 同日）**，仅作历史量级参照，不与本轮绝对值直接可比；同一脚本口径下即 −15.1）。**判定**：按 ≤2.0 s 判据字面成立（2.0 ≤ 2.0），但三轮 treatment 全部慢于对应 control（+1.0 / +2.0 / +2.0），0.1 s 分辨率下不能确认严格达标；最终裁决见 Task 4。
- 每轮 treatment 均 `save scheduled` → `written`，无 `save failed` / `save skipped` / `save already in progress`。三份 `written` 行：`entries=223536, dirs=17389, ms=11602` / `ms=11697` / `ms=11328`（warm-up treatment 为 `ms=10699`，恢复轮 `ms=12193`）。
- 时间线（premain 时钟）：crawl 决策约 +1.7 s；`save scheduled` 约 +5.7 s；`written` 中位 **+17.3 s**（范围 16.8–17.5；主菜单约 +57.6 s 是 smoke_run 的**进程时钟**，不是 premain 时钟）。`timeline: mods.start` 约 +29.1–30.1 s，writer 在 mod 加载开始前约 12 s 就已结束，实际重叠的是 dds/script/find 阶段，**不是** `initMods`。
- **+2.0 s 的归因（假设，未隔离）**：主要嫌疑是异步 writer 与启动早期阶段（dds/script/find）的 CPU/GC 竞争；另一候选是 crawler 线程上的快照成本（`locationKeys` + `collector.toArray()`）。本轮没有“关闭 writer”的对照，不能定论。
- 重建索引 3,337,599 B（Step 1 实删的旧索引为 3,332,609 B；M3 文档的 3,332,575 B 是 pre-reboot 构建口径）；`dirs` 17,389（M3 17,067，来自目录自身路径硬化），entries 不变 223,536。
- warm-up 两轮（不计入中位）：control 67.2 s、treatment 58.1 s（首轮噪声大，故按计划排除）。
- **环境漂移（同日同 boot，不同 uptime）**：M3 的干净 control 中位 50.1 s 取自今日 reboot 后不久；本轮 control 中位 55.6 s 是同一 boot 数小时后（机器上有 Edge/WebView2、QQ、Steam++、Huorong 等后台负载；22:29 事后快照 15.5 GB 空闲 / 31.2 GB，⚠️ 非 A/B 窗口 21:37–21:57 的同步记录）。两者差 +5.5 s 的**归因是环境漂移（未隔离）**；control 走 `fileIndex=false`、不注册 `FileIndexTransformer`，本次代码改动只在 save 路径，没有代码回归的机理；`read_bytes_menu` 两轮均约 805 MB，I/O 体量相同。因此只使用本轮**交错** C/T 的差值，不与 M3 的绝对值直接比较。

## 3. 3/3 命中
| 轮 | menu_s | `file index: loaded` | `full crawl` |
|---|---:|---:|---:|
| 1 | 55.1 | 1 | 0 |
| 2 | 54.6 | 1 | 0 |
| 3 | 57.6 | 1 | 0 |

- 构建轮（3 轮前）：`written entries=223536, dirs=17389, ms=11182`；三命中轮均为 `loaded mod_entries=223536, total_entries=229499, dirs=17389, bytes=3337599`，`ok=true`。

## 4. 早退 fail-open
- kill 前日志：`file index: save scheduled entries=229754`（premain 后 +6.4 s）；进程在启动后 12.3 s 被 `taskkill /F` 结束，其后**没有** `written`。
- kill 后：`file-index.idx.gz` 不存在；`.tmp` 也不存在（本步 `ls` 输出未单独落盘，结论另由 `task-3-report.md` 记录 + `FileIndex.write` 只在 entries 构建完成后才创建 `.tmp` 的代码路径支撑）。
- 恢复轮：`file index: absent, corrupt, or FR version/shape mismatch; full crawl` → `save scheduled` → `written entries=223536, dirs=17389, ms=12193`；主菜单 `ok=true`，menu 61.1 s，索引恢复到 3,337,599 B。

## 5. 门禁
| 门禁 | 结果 |
|---|---|
| Java 17 测试 | 101 found / 100 successful / 1 aborted / 0 failed（`build/m31-java-tests.log`） |
| ABI audit | ok=true, java21_api_hits=[]（classes 40/40 major 61；jar 77 类 = 40×61 + 37×49(ASM)） |
| textures | normal_before_menu=0 / patched=true / mismatch_line=null / gate_ok=true |
| Base | build → hit，两轮 ok（第 1 轮 8.5 s，`written entries=15243, dirs=475, ms=1244`；第 2 轮 8.0 s，`loaded`） |
| no-FR | 本轮跳过（裁决）。无 FR 时 `frPresent()` 为 false（`frVersion()` 归一化为 unknown、`supportedFrVersion()` 为 false），agent 不进入 FR 分支、`FileIndexTransformer` 不注册，save 路径不可达；M3 的 no-FR 门禁已覆盖注册逻辑；JRE17 全量 + Base + 260mods 已覆盖类加载。为省 ~22 分钟未重跑。 |
| 回滚 | control（`-Dhypernova.fileIndex=false`）3 轮正常（56.6 / 55.6 / 55.1 s，均 ok，无任何 `file index:` 行） |

## 6. 边界与已知限制
- 异步窗口内目录被写 → 本次不落盘（下次重建）；比同步 save 的静默接受更保守。
- 爬取过程中（crawlEnd 之前的）写入仍是既有盲区，M3.1 不改变该窗口。
- 已有 v2 索引不会被强制重建；空叶子硬化在下次重建后生效。
- 异步窗口内目录被写：若某个 mod 在启动早期反复写自己的目录，可能**每轮重建都 skip**（不只是“下次一次”）；日志每轮出现 `save skipped; directory changed after crawl`。本轮 0 次。
