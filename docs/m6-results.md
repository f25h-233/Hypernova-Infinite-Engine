# M6 兼容性审计结果（单环境：260mods）

> 审计日期：2026-11-03
> 范围：汉化测试版 / ChineseInputFix / 字体 / UI / 纹理 mod 的兼容性与 manifest 正确性。
> **M6 只验收单环境（Starsector-098-260mods，agent-only）。** MixinFR + JRE 17
> 与 FR 0.9.7 + Java 28 的两套组合路线属于 M7，不在本文结论内。

## 1. 结论

**自动化部分完成；用户实机 gate 未执行（§4 全部 `pending`），因此不写“M6 通过”。**

- 构建与测试：Java 主测试 115/115；agent 测试 211 个中 210 通过、1 个已知
  Windows symlink 用例跳过；Python `tests/tools` 460 passed。
- 260mods 的 manifest / skip 已重新生成并通过审计：`installed.ok=true`，
  generation 配对，无宿主污染；fail-open 4/4 场景通过。
- 当前真实日志扫描：五类纹理错误 0，`observations_total=14`（均为
  ChineseInputFix 存在性观察），`complete=true`。
- 菜单 smoke（probe + lazy/dds 临时开启）rc0，`session.json ok=true`，
  `frame_probe.source=agent`，`texture_errors_total=0`，`log_audit.total=0`。
- **菜单 smoke 不是战役/战斗/读档/分辨率/中文输入/字体视觉验收。** 这些项
  仍待用户按 `docs/m6-manual-acceptance.md` 执行。

## 2. 环境

| 项 | 值 |
|---|---|
| 日期 | 2026-11-03 |
| OS | Windows 11 Home China 10.0.26200，Git Bash |
| 游戏根 | `Starsector-098-260mods`（Starsector 0.98a-RC8） |
| 启动档 | `Miko_Lite.txt`；smoke 使用 `jdk-28+13` |
| Fast Rendering | 0.9.7rc2 |
| 启用 mod 数 | 256（矩阵扫描 256/256） |
| Hypernova 形态 | **agent-only**：`enabled_mods.json` 不含 `hypernova_infinite_engine` |
| ChineseInputFix | 2.0.0，**存在但未启用**（`enabled=false`） |
| CJK / 语言 | `cjk_mode=true`，`strings.cjk_ratio=1.0`（229/229），`locale_override=en_US` |
| 默认字体 | `graphics/fonts/insignia15LTaa.fnt` |
| 字体 mod | 4 个：`ApproLight`、`BoxUtil`、`lw_console`、`szb` |
| UI mod | 11 个：`BoxUtil`、`CjyToyBox`、`aotd_sop`、`aotd_theory_of_toolbox`、`aotd_vok`、`assortment_of_things`、`demandIndicators`、`exoticatechnologies`、`lunalib`、`pt_qolpack`、`szb` |
| 基线快照 | `SS098_Hypernova_Compat_AuditTest/backups/baseline-2026-11-03/`（不入库） |

基线快照的 4 个文件（`enabled_mods.json`、`hypernova.json`、`Miko_Lite.txt`、
`settings.json`）在审计结束时的 SHA256 与快照完全一致；本次自动化未修改用户环境。

## 3. 自动化证据

### 3.1 Gate 套件

| # | 命令 | rc | 关键读数 |
|---|---|---:|---|
| 1 | `bash tools/java/run-tests.sh` | 0 | 115 tests / 0 failed |
| 2 | `bash tools/java/run-agent-tests.sh` | 0 | 211 found / 210 successful / 1 aborted（已知 Windows symlink 用例） |
| 3 | `python -I -m pytest tests/tools -q` | 0 | 460 passed in 24.77s |
| 4 | `bash tools/java/build-mod.sh` | 0 | L1=185 L2=509 L3=2614，baked=3285/3285，unresolved=0 |
| 5 | `bash tools/java/install-manifest.sh Starsector-098-260mods` | 0 | L1=6624 L2=18525 L3=55445，baked=80286/80286，unresolved=0；skip v1/v2=73447 |
| 6 | `m6_audit_matrix.py` | 0 | 256/256 mods，parse_errors=0，duplicate_ids=4，默认 lazy/eviction/scene_unload=false |
| 7 | `m6_manifest_audit.py` + fail-open | 0 | `installed.ok=true`，skip generation 配对，host_pollution 无；`fail_open.ok=true`（4/4 场景） |
| 8 | `m6_log_audit.py` | 0 | 五类错误 0，`observations_total=14`，`complete=true` |

manifest 审计读数：

- manifest：L1=6624 / L2=18525 / L3=55445，size=9,110,366 bytes，
  SHA256 `e61084a315e5073c6f0973d576be95c664bf8ecf701a3d0771ec6d174ca0aaba`。
- `lazy-skip-v1.txt` / `lazy-skip-v2.txt`：各 73,447 条，generation 均为
  `e61084a3…aaba`，与 manifest 一致；`generation_checked=true`。
- `installed.defaults`：`lazy=false`、`eviction=false`、`scene_unload=false`、
  `textures_enabled=true`（显式）。
- `host_pollution.found=[]`；`installed.findings=[]`。
- fail-open 场景：`bad_metadata`、`broken_mods`、`missing_dds`、
  `missing_skip_rerun` 全部 `ok=true`。
- 说明：fail-open 工作目录每次用 `mktemp -d` 在仓库外创建；旧的
  `evidence/fail-open`（仓库内）会被工具拒绝。`--fail-open-out` 写回
  `evidence/fail-open.json`。

矩阵读数：

- `mods.enabled_count=256`，`scanned_count=256`，`parse_errors={}`。
- `duplicate_ids` 4 组：`lw_console`、`lw_lazylib`、`particleengine`、
  `shaderLib`（同一 mod 的两种 id 写法，非新问题）。
- `chinese_input_fix={present:true, enabled:false, version:"2.0.0"}`。
- `hypernova={enabled:true, textures_enabled:true, lazy:false,
  eviction:false, scene_unload:false}`（`enabled` 是主 mod 配置值；主 mod
  本身未在 `enabled_mods.json` 中启用，agent-only）。

日志读数：

- `starsector.log` / `scripts-agent.log`：五类错误均为 0
  （`Failed to load texture`、`VerifyError`、`ClassFormatError`、
  `AsyncException`、`isStateCorrupted`）。
- `observations_total=14`，全部是 `ChineseInputFix` 存在性观察；`IME=0`。
  观察项不参与失败判定。

### 3.2 菜单 smoke（真实进程，probe + lazy/dds）

命令见 `SS098_Hypernova_Compat_AuditTest/scripts/run-m6-audit.sh`。结果：

- smoke `rc=0`；主菜单 87.3 s；总墙钟 133.4 s；`stop=forced`
  （smoke 脚本的正常退出路径，不是崩溃）。
- `session.json ok=true`：`anchor_found=true`、
  `frame_probe.present=true`、`frame_probe.source=agent`、
  `lazy.present=true`、`texture_errors_total=0`、`log_audit.complete=true`、
  `log_audit.total=0`。
- frame probe：`frames=3000`，`p99Ms=54`，`maxMs=984`，`over200=2`，
  `longGaps=1`（只作菜单观察，不是性能验收）。
- lazy summary：`index=73447`、`demand=21351`、`proxies=45784`、
  `skipped=45784`、`queuedSkip=45785`、`ddsHit=19`、`ddsFallback=2`、
  `dimMismatch=0`、`failed=0`、`misses=0`、`materialized=86`、
  `liveBytes=14,446,800`（预算 268,435,456）。
- 进程内存（菜单时刻，仅供记录）：ws=9474.8 MB、private=13135.4 MB、
  GPU process dedicated/shared=496.6/36.2 MB。**不据此宣称任何收益或回归。**
- 本组 `log_audit` 只看到 2 条 `ChineseInputFix` 观察词（菜单加载 mod 列表），
  无错误。

### 3.3 证据文件

| 文件 | 内容 |
|---|---|
| `SS098_Hypernova_Compat_AuditTest/evidence/matrix.json` | 环境/字体/UI/CJK/默认值矩阵 |
| `SS098_Hypernova_Compat_AuditTest/evidence/manifest-audit.json` | installed + fail_open 汇总 |
| `SS098_Hypernova_Compat_AuditTest/evidence/fail-open.json` | fail-open 4 场景明细 |
| `SS098_Hypernova_Compat_AuditTest/evidence/log-audit-current.json` | 当前日志错误/观察扫描 |
| `SS098_Hypernova_Compat_AuditTest/evidence/menu-smoke.json` | smoke 原始读数 |
| `SS098_Hypernova_Compat_AuditTest/menu-smoke/session.json` | `m6_session end` 合并后的菜单会话证据 |
| `SS098_Hypernova_Compat_AuditTest/menu-smoke/logs/` | 轮转的 pre/rotated 日志（不入库） |

> 路径口径：`m6_session.py` 的产物按实现落在 `<evidence-root>/<label>`。
> 本次传入 `--evidence-root SS098_Hypernova_Compat_AuditTest`，所以会话证据
> 实际在 `SS098_Hypernova_Compat_AuditTest/menu-smoke/`；runbook 中写的
> `evidence/<label>/` 是文档口径差异，不影响读数。

## 4. 用户实机 gate

以下照抄 `docs/m6-manual-acceptance.md` §6 判定表；**未执行项保持 `pending`，
不填 `pass`。** 菜单 smoke 只覆盖主菜单，不能替代本表任何一项。

| 出口 | 场景/证据 | 通过条件 | 结果 | 证据路径 |
|---|---|---|---|---|
| 1. 汉化测试版可用 | A/B/D/E 组菜单、战役、战斗、读档画面 | 无豆腐块、无缺字、无错位；A/B `session.json` `ok=true` | pending | `evidence/A-campaign/`、`evidence/B-combat/`、`evidence/E-visual/screens/` |
| 2. ChineseInputFix 中文输入 | D 组改名/搜索/对话输入 | 每个场景至少 2 个中文字成功输入，不失败、不崩；`session.json` `ok=true` | pending | `evidence/D-ime/`、`evidence/D-ime/env.md` |
| 3. 字体/UI/纹理 mod 无五类错误 | A–E 全部 `session.json` | `texture_errors_total=0` 且 `log_audit.total=0` | pending | `evidence/<label>/session.json` |
| 4. manifest/skip generation 与 fail-open | `m6_manifest_audit.py` 自动证据 | `installed.ok=true`、skip v1/v2 generation 一致、无宿主 `lazy-skip-*`、默认全 off；`fail_open.ok=true` | **pass（自动化）** | `evidence/manifest-audit.json`、`evidence/fail-open.json` |
| 5. 分辨率/全屏/alt-tab | C 组 | 切换与 alt-tab 后不崩、可继续操作、无纹理错误；`session.json` `ok=true` | pending | `evidence/C-resolution/` |

> 出口 4 本表按自动化证据已可判定为 pass；其余出口 1–3、5 必须由用户实机执行。

分组记录：

| 组 | 结果（pass/fail/pending） | 备注（场景/异常/对照） |
|---|---|---|
| A 战役 | pending | 未执行 |
| B 战斗 | pending | 未执行；必须真正进入战斗后返回战役 |
| C 分辨率/alt-tab | pending | 未执行 |
| D 中文输入 | pending | 未执行；ChineseInputFix 当前未启用，需按 runbook §2 临时启用并在 §7 恢复 |
| E 字体/UI 视觉 | pending | 未执行；豆腐块/缺字/错位只能人工看 |

用户执行前的准备与回滚命令见 `docs/m6-manual-acceptance.md` §1–§3、§7；
环境快照已存在（`backups/baseline-2026-11-03/`），不要覆盖。

## 5. 失败归因与对照

- 本次自动化 gate、日志扫描、菜单 smoke 均无失败项。
- 260mods 已知问题（Star Wars 新开局 NPE、超大舰队卡顿、Exotica 改装空 cast、
  生涯大地图卡顿）**不是 Hypernova 回归**；若用户 gate 在这些场景失败，先按
  runbook §5 用 `Miko_Lite_noagent.txt`（无 Hypernova agent）对照。
- 对照判定只看 `texture_errors_total` 与 `log_audit.total`；对照会话没有
  Hypernova，`frame_probe`/`lazy` 按设计缺失，`m6_session end` 的 `ok=false`
  是预期行为，不能当成失败证据。
- 已知 deferred minor：日志审计的错误模式未包含 `font file not found`
  （Task 4 复审记录）；当前真实日志 0 命中，本次不计为失败。是否加回模式
  留待后续工具修订。
- 菜单 smoke 的 `stop=forced` 是 smoke 脚本在 linger 后的正常强制退出路径，
  不是游戏崩溃；本次未观察到 `AsyncException` / 状态损坏。

## 6. 默认值与回滚

- **`hypernova.json` 未改**。发行默认保持：
  `textures.lazy=false`（无 `lazy` 块）、`eviction=false`、
  `scene_unload=false`；frame probe 默认 off。
  `textures.enabled=true`、`fileIndex.enabled=true`、`scripts.enabled=true`
  是原有发行默认，不是本次打开的。
- **ChineseInputFix 未启用**：本次自动化没有临时启用它，审计结束时
  `enabled_mods.json` 中仍为 false。用户 gate 需要按 runbook §2 临时启用，
  结束后必须按 §7 恢复。
- `enabled_mods.json`、`Miko_Lite.txt`、`settings.json` 的 SHA256 与
  `backups/baseline-2026-11-03/manifest.json` 完全一致；未改用户环境。
- 回滚（用户 gate 之后）：

  ```bash
  python -I tools/m6_env_snapshot.py restore \
    --snapshot SS098_Hypernova_Compat_AuditTest/backups/baseline-2026-11-03 \
    --force
  ```

  复核 `ChineseInputFix` 与 `hypernova_infinite_engine` 都为 false；
  删除或停用 `SS098_Hypernova_Compat_AuditTest/vmparams/Miko_Lite_m6_probe.txt`。
- 临时 `-D`（probe/lazy/dds）只存在于 smoke/runbook 的启动参数，未写入
  `Miko_Lite.txt`；不影响默认值。

## 7. 限制与下一步

- **菜单 smoke 不代表战役/战斗/读档/分辨率/中文输入/字体视觉**；A–E 组
  用户 gate 仍未执行。
- A→B / stutter 用户验收仍未执行（继承 M4/M4.1 的 open 项），本文不作结论。
- 本文的帧时间、内存、GPU 读数只是单次菜单观测，**不宣称显存收益、启动收益
  或性能改善**。
- **M6 未验证组合路线**：MixinFR + JRE 17（路线 A）与 FR 0.9.7rc2 + Java 28
  （路线 B）属于 M7；M7 计划已存在
  （`docs/superpowers/plans/2026-11-03-m7-unified-stack.md`），当前等待
  MixinFR 1.2.5 与 StarsectorParallel 0.1.0 等用户工件，尚未执行/收口。
- 下一步：用户按 `docs/m6-manual-acceptance.md` 完成 A–E 组并回填本文件 §4；
  全部 pass（或失败项完成 no-Hypernova 对照并归因）后，才进入 M5 的默认开启
  canary 与发行决策。
