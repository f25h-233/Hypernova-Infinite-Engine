# M4 结果：验收 & 发布硬化

- **日期**：2026-11-03（M4 代码/工具侧于 2026-11-02 完成；本文件记录 Task 5 的端到端验证）
- **状态**：代码/工具侧完成；A→B/stutter 用户 gate **未执行（user gate，需用户按
  `docs/m4-manual-acceptance.md` 跑）**。
- **默认**：未改任何默认开关；frame probe 默认 off。

## 1. 结论

1. frame-time probe 默认 off，`-Dhypernova.frameProbe=true` 开启；关闭时只做一次
   null 检查；在 `FrameAdvanceGate.completed(...)` 之后采样，并按引擎帧 `amount`
   去重（同一引擎帧的双入口不重复计数）。
2. 会话报告工具把 frame probe、lazy summary、五类纹理错误、GPU CSV 合并为一份 JSON。
3. A/B 工具修复：treatment stats 在 treatment 轮结束时立即抓取、`--rounds>=1`、
   timeout 按 pid 文件清理。
4. release_check 要求主 jar；build-mod 任意失败清 zip。
5. A→B/stutter：**未执行**。本文件不包含任何人工长会话、GPU 曲线或 stutter
   数字；见第 5 节。

## 2. 验证

以下命令按顺序执行，均在仓库根目录。

| 命令 | rc | 结果 |
|---|---|---|
| `bash tools/java/run-tests.sh` | 0 | 115 tests found / 115 successful / 0 aborted / 0 failed |
| `bash tools/java/run-agent-tests.sh` | 0 | 197 tests found / 196 successful / 1 aborted / 0 failed（abort 为已知 Windows symlink 用例） |
| `python -I -m pytest tests/tools -q` | 0 | 390 passed in 17.39s |
| `bash tools/java/build-mod.sh` | 0 | 主 jar 与 `hypernova-0.1.0.zip` 构建成功；末尾三条 OK |
| `bash tools/java/install-manifest.sh Starsector-098-260mods` | 0 | `verified: installed jar matches build output` |
| `python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite` | 0 | `installed: ...hypernova.agent.jar`；`no vmparams change: Starsector-098-260mods\Miko_Lite.txt` |

`build-mod.sh` 末尾输出（节选）：

```text
OK: D:/github/Hypernova-Infinite-Engine/build/java/hypernova.jar
full: L1=185 L2=509 L3=2614 baked=3285/3285 unresolved=0
OK: D:\github\Hypernova-Infinite-Engine\build\java\hypernova-0.1.0.zip
OK: /d/github/Hypernova-Infinite-Engine/dist/manifest-v1.json (dist artifact, not tracked)
OK: /d/github/Hypernova-Infinite-Engine/build/java/hypernova-mod
OK: /d/github/Hypernova-Infinite-Engine/build/java/hypernova-0.1.0.zip
```

`install-manifest.sh` 输出（节选）：

```text
full: L1=6624 L2=18525 L3=55445 baked=80286/80286 unresolved=0
installed: ...Starsector-098-260mods\mods\hypernova_infinite_engine\data\config\hypernova\manifest-v1.json
skip=73447
skip_v2=73447
installed: Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/{manifest-v1.json,lazy-skip-v1.txt}
verified: installed jar matches build output
```

### SHA256

| 工件 | SHA256 |
|---|---|
| `build/java/hypernova.jar` | `12e57a726c80b50069d39abaf288615a21ce889e6b56e8e57e3391c8856a92b1` |
| `Starsector-098-260mods/mods/hypernova_infinite_engine/jars/hypernova.jar` | `12e57a726c80b50069d39abaf288615a21ce889e6b56e8e57e3391c8856a92b1` |
| `build/agent/hypernova.agent.jar` | `ebcf48c1358c054be6a95f0eaff933b8c14937731b806c402d42b27ebea37f36` |
| `Starsector-098-260mods/mods/hypernova_infinite_engine/jars/hypernova.agent.jar` | `ebcf48c1358c054be6a95f0eaff933b8c14937731b806c402d42b27ebea37f36` |

主 jar（构建 vs 安装）与 agent jar（构建 vs 安装）的 SHA256 均一致。

以上为 Task 5 验证时点快照；`run-agent-tests.sh`/`build-agent.sh` 会重建
agent jar，后续运行前需重新 `install_agent.py` 才能保证 build 与安装一致。

## 3. 实机 smoke

命令：

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 20 \
  --jvm-arg=-Dhypernova.frameProbe=true \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --json-out build/m4/smoke-probe.json
```

结果：rc=0，主菜单到达，正常 forced 退出。

| 指标 | 值 |
|---|---|
| `ok` | `true` |
| `menu_s` | 63.1 |
| `wall_s` | 108.5 |
| `stop` | `forced` |
| `gpu_process_dedicated_mb` (menu) | 496.5 |
| `HYPERNOVA_FRAME` 行数（最后会话切片） | 0 |
| session anchor | found=true，anchor_count=2 |

报告命令：

```bash
python -I tools/m4_session_report.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m4/smoke-report.json --text
```

结果：rc=0；`build/m4/smoke-report.json`：

| 项 | 值 |
|---|---|
| `frame_probe.present` | `false`（本次主 mod 未启用/未实例化；即使启用，菜单无 `Global.getSector()` 也不会产帧行） |
| `lazy.present` | `true`（anchor_count=2，summary line=186） |
| `texture_errors_total` | 0（五类全 0） |
| `lazy.summary.failed / disabled / dimMismatch / failedParked` | 0 / 0 / 0 / 0 |
| `lazy.summary.main` | `main` |
| `lazy.summary.dds / ddsHit / ddsFallback` | 1 / 31 / 2 |
| `lazy.summary.liveBytes / evictableBytes` | 14658304 / 747644 |
| `lazy.summary.budgetBytes` | 268435456 |
| `health` | 除 `frame_probe_present` 与 `frame_probe_complete` 外全 true（后者在无帧行时必然为 false） |

**重要限制（实测发现）**：`Starsector-098-260mods/mods/enabled_mods.json` 的
`enabledMods`（256 个）**不包含** `hypernova_infinite_engine`，因此本次 miko-lite
smoke 中 Hypernova 主 mod 的 `HypernovaPlugin`/`FrameTimeProbe` 根本没有被实例化，
日志里也没有 `Hypernova frame probe enabled`。这次 smoke 证明的是：

- probe 参数开启后启动仍能到主菜单、正常退出（没有引入启动崩溃）；
- agent 侧 lazy/DDS 路径健康、纹理错误为 0。

它**不能**证明“主 mod 的 probe 在实机加载后正常工作”。主 mod 的接线由 Java 测试
（`FrameTimeProbeTest`、`AssemblyWiringTest.frameProbeRunsAfterGateAndOnlyWhenPresent`）
覆盖；真正的实机帧行属于 A→B 用户 gate。`Starsector-098-Base` 虽然启用了主 mod，
但其当前安装的 `hypernova.jar` 是旧构建（SHA256 `42c9fa60...`，与本次构建
`12e57a72...` 不一致），本轮没有改用它。

## 4. A/B 工具实跑

命令：

```bash
python -I tools/m26_ab.py --profile miko-lite --rounds 1 \
  --out build/m4/ab-fix.json
```

结果：rc=0。

| 项 | 值 |
|---|---|
| `control_median` | 74.6 s |
| `treatment_median` | 65.6 s |
| `delta_s` | -9.0 s |
| `paired_deltas_s` | [-9.0] |
| `paired_median_s` | -9.0 |
| `lazy_rows` | 1 |
| `gates.all_rounds_ok` | true |
| `gates.treatment_stats_present` | **true** |
| `gates.logs_present` | true |
| `gates.no_texture_errors` | true |
| `gates.treatment_failed_zero` | true |
| `gates.treatment_disabled_zero` | true |
| `gates.treatment_dim_mismatch_zero` | true |
| `gates.treatment_dds_disabled_zero` | true |
| `gates.treatment_dds_hit_positive` | **true** |
| `gates.selftest_ok` | true（本轮未请求 `--selftest`） |

`lazy_median`（treatment，单轮）：

| 键 | 值 |
|---|---|
| `queue` | 52604 |
| `hits` / `misses` | 7369 / 0 |
| `dds` / `ddsHit` / `ddsFallback` | 1 / 25 / 2 |
| `failed` / `disabled` / `dimMismatch` / `failedParked` | 0 / 0 / 0 / 0 |
| `liveBytes` / `evictableBytes` | 14457136 / 546476 |
| `budgetBytes` | 268435456 |
| `main` / `loading` | `null` / `null`（见下） |

`main` 与 `loading` 在 `lazy_median` 中为 `null`，因为中位数只聚合整数值，而底层
summary 是字符串：`main=main`、`loading=Thread-4-FR-Main-Loader`。原始 treatment
summary 中这两项已正确记录，不是 lazy 健康失败。

**口径**：`--rounds 1` 只有一对 control/treatment。−9.0 s 的菜单差值是单轮噪声级
观测，**不能**当作收益结论；本轮不宣称启动或显存收益。

## 5. A→B / stutter user gate

**未执行（user gate，需用户按 `docs/m4-manual-acceptance.md` 跑）。**

**前置限制（必须）**：frame probe 依赖 textures 模块（`HypernovaPlugin`）。
`Starsector-098-260mods` 默认是 agent-only（`enabled_mods.json` 不含
`hypernova_infinite_engine`），不启用主 mod 就不会产生 `HYPERNOVA_FRAME` 行。
用户 gate 必须先在 260mods 临时启用该模块（备份/启用/恢复步骤见
`docs/m4-manual-acceptance.md` §1），或改用已启用模块的 `Starsector-098-Base`
（先刷新主 jar/agent，报告用 Base 路径；mod 数少）。外部帧时间工具只能补
stutter 观察，**不能**填 `frame_probe.present=true`，也不能替代 Hypernova probe。

**I-5 口径（最终 review）**：probe 依赖主 mod（textures 模块）；260mods 默认
agent-only，无法产生 `HYPERNOVA_FRAME`。临时启用模块后，测到的是
“textures 模块 + agent”，**不能**与 M2.6/M2.8 的 agent-only 数字直接比较，
也不能把差异归因于 lazy/DDS 单独一项。M5 决策若要保持 agent-only，必须使用
外部帧时间工具或 agent-side probe 的替代证据；不能用 agent-only 环境冒充
frame probe。

本轮没有：

- 真实存档的 A→B 各 10 min 长会话；
- `build/m4/gpu-a.csv` / `gpu-b.csv` 或 `gpu.dedicated_mb.median` 的 A/B 对比；
- `frame_probe.present=true` 的实机帧行；
- `over200` / `maxMs` / `p99Ms` / `longGaps` 的人工验收读数；
- 崩溃/白块/错位的人工观察。

不要在 M5 默认开启决策中把这些项目当作“已通过”。执行前需确认：

1. 使用**已启用 `hypernova_infinite_engine`** 的游戏环境（`Starsector-098-Base`
   已启用；`Starsector-098-260mods` 当前未启用）；
2. 该环境的主 jar 已刷新到当前构建（`install-manifest.sh` 或等价安装），
   否则 probe 仍是旧 class；
3. 按 `docs/m4-manual-acceptance.md` 使用临时启动参数，不改发行默认值。

## 6. 限制

- **frame probe 前置**：必须启用 textures 模块（`HypernovaPlugin`）；260mods
  默认 agent-only，不启用就不会有 `HYPERNOVA_FRAME`。用户 gate 需按
  `docs/m4-manual-acceptance.md` §1 临时启用/恢复，或改用 Base 的
  `fr.vmparams` 路径；外部工具只补 stutter，不能填 frame probe。
- **I-5 可比性**：启用模块后的数据是“textures 模块 + agent”，不能与
  M2.6/M2.8 的 agent-only 数字直接比较，也不能单独归因于 lazy/DDS。
- summary 每 10 s 一条，最后一条最多旧 10 s；
- `p99Ms` 是 1 ms 桶估算，不是逐帧原始值；
- `longGaps` 只排除 >5 s，短暂停仍会算作大帧；
- 260mods 大地图/mod 环境问题不归因 Hypernova；
- 本轮不默认开启、不宣称显存收益；
- miko-lite smoke 未加载 Hypernova 主 mod，probe 实机加载未被本轮 smoke 覆盖
  （详见第 3 节）；
- A/B 只有单轮（`--rounds 1`），差值不作为收益证据。

## 7. 下一步

M6（汉化/中文输入兼容审计）→ M5（默认开启 canary + 发行）。
