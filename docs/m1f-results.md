# M-1f FR 0.9.7rc2 迁移与重新基线结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）；
>      Base（11 mods，含 hypernova）、Zulu JRE 17.0.10
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…，fr.agent.jar SHA-256 3caea920…）

## 1. 结论

| 门禁 | 结果 | 证据 |
|---|---|---|
| FR 0.9.7rc2 到主菜单 | 通过 | `build/m1f-first.json`、`build/m1f-rounds-warm.json` |
| scripts cache preload | 通过 | `build/m1f-textures-agent.log`、`build/m1f-rounds-warm.json` |
| textures patched | 通过 | `build/m1f-textures-measure.json`（`normal_before_menu=0`, `gate_ok=true`） |
| 主线程断言/崩溃 | 通过 | `build/m1f-binding.log`（`Hypernova main thread bound at advance: Thread-3`，无 `IllegalStateException`） |
| VOpt 0.9.7 DDSIntegration | 通过 | `VOpt Loaded` + `Suitable FR Version found`；无 `Failed to initialize VRAM Optimizer` |
| no-FR 臂 | 通过 | `build/m1f-nofr-on-measure.json`（`gate_ok=true`） |
| Java 17 | 通过 | `build/m1f-java-audit.json`、`build/m1f-jre17-*.log`、`build/m1f-base-jre17.json` |

**M-1f 基线：warm 3 轮中位 60.6 s**（60.1–61.1；`build/m1f-rounds-warm.json`）。
**G-01' 目标：≤ 48.5 s**（相对基线下降 ≥20%）。

## 2. 安装与回滚

- 安装：`python -I tools/fr_install.py --game <game> --action install`；只写 `fr.jar`、`fr.agent.jar`、`fr.version.txt`。
- 备份：`fr.jar.bak-hypernova-v0.9.5`（0.9.5 SHA-256 `7ee51ee9…`）、`fr.agent.jar.bak-hypernova-v0.9.5`（0.9.5 SHA-256 `8b9c7871…`）；两个环境安装后均为 `v0.9.7rc2`。
- 启动档未改：`Miko_Lite.txt` / `Miko_Lite_nofr.txt` 的 SHA-256 前后一致（`build/m1f-launch-before.sha256`，`sha256sum -c` 两行 `OK`）；Base `fr.vmparams` 的 agent/FR token 顺序未变。
- 回滚：`python -I tools/fr_install.py --game <game> --action rollback --to v0.9.5`。

## 3. 线程绑定证据

- 0.9.7 的 `onApplicationLoad` 线程：`Hypernova init thread: Thread-7-FR-Main-Loader`（`build/m1f-binding.log`）。
- 绑定：`Hypernova main thread bound at advance: Thread-3`（首次 advance 在主菜单；`onGameLoad` 时已 first-wins no-op）。
- 自检：`selfcheck: LOADED graphics/fonts/orbitron20aa_0.png`、`selfcheck: RESULT 1/1 PASS`；自检在主菜单首次 advance，早于读档。
- 读档后 telemetry：80 条事件全部在 `Thread-3`（1 条 `loaded` + **79 条 `hit`（`ensureLoaded` 路径）**；`Starsector-098-Base/saves/common/hypernova/telemetry.jsonl.data`）；`attachCampaign: done` 在 29,224 ms，调度器最终 `loaded=79, failed=0`。
- 无 `IllegalStateException` / `ensureLoaded requires bindMainThread`。手动验收后 `startup_probe_paths` 已恢复为 `0`。

## 4. 260mods warm 基线

| 轮 | menu_s | read_bytes_menu | key ms | preload | stop |
|---|---:|---:|---:|---|---|
| 1 | 61.1 | 802,681,434 | 454 | hit entries=2113, 7 ms | forced |
| 2 | 60.6 | 803,158,922 | 469 | hit entries=2113, 7 ms | forced |
| 3 | 60.1 | 805,039,674 | 477 | hit entries=2113, 8 ms | forced |
| 中位 | 60.6 | 803,158,922 | 469 | entries=2113, bytes=8,781,716 | — |

- `cache_control` = `none`；不宣称相对 M-1e 的净收益。
- 第一轮预热（scripts cache cold）不计入基线：`build/m1f-first.json` 为 81.1 s / `preload_cold`。

## 5. 门禁细节

### 5.1 textures

- `normal_before_menu` = 0（M-1e 基线 30,378）；`patched=true`；`mismatch_line=null`；`gate_ok=true`。
- `m1b_measure` 的 `menu_s` 是日志 `Playing music` 锚点口径（60.3 s；比 smoke 进程口径可能小 0.3 s 左右），不是差异；基线以 `build/m1f-rounds-warm.json` 的 60.6 s 为准。

### 5.2 scripts

- 首轮 cold：`build/m1f-first.json` 的 `agent.preload_cold`（`preloaded=0`），随后三次 `scripts cache written`（entries 1,574 → 1,887 → **2,113**）。
- warm 轮：`scripts cache preloaded: entries=2113, bytes=8781716, in 7–8 ms`。
- `bytecodeCache field not found` = 0；`transform failed` = 0；`miss breakdown` 稳定（total=11,264）。
- `script phase ended:` 不是当前 agent 的输出，不作为证据。

### 5.3 VOpt

- `VOpt Loaded`；`Suitable FR Version found, skipping DDS file handling`；`Failed to initialize VRAM Optimizer` = 0。VOpt 仍为 **v1.0.45**。
- FR 的 `Initialized VramOptimizer UploadDDSTexture method.` 是 INFO，被 `mikohime.properties` 的
  `com.genir.renderer.overrides.loading=WARN` 过滤，所以日志里看不到；反射失败会抛 RuntimeException 崩启动，
  游戏正常到菜单即为集成成功。该行**不作为**证据。

### 5.4 no-FR 臂

- `normal_before_menu=0`；`fr_present=false`；`fr_missing_disabled=true`；`failed_texture_lines=0`；`patched=true`；`gate_ok=true`。整轮 `menu_s=1354.0 s`（`build/m1f-nofr-on-measure.json`；smoke JSON 为 1354.1 s），仅记录，不宣称收益。
- `m1b_measure` 的 `cleaned` 口径只计 `cache/*_normal.png`（本次 0 条）；另有 **21 条非 cache** 的 `Cleaned buffer for texture graphics/..._normal.png` 行，不计入门禁（M-1e no-FR-on 同样为 7 cache + 21 非 cache，属既有行为，非回归）。
- arm B 未重跑：260mods 集合未变，30,378 为 M-1e 冻结的同一环境基线（Ruling M1f-2）。

## 6. Java 17

- 审计 `ok=true`，`java21_api_hits=[]`；agent 64 found / 63 successful / 1 aborted / 0 failed；mod 100/100。
- FR 0.9.7rc2 的 425 个 class（`fr.jar` 406 + `fr.agent.jar` 19）全部 major 61 / minor 0，无 Java 21+ API 命中。
- Base JRE17 + FR 0.9.7rc2 冒烟通过（`menu_s=14.0 s`；`build/m1f-base-jre17.json`）。

## 7. 已知限制

- 0.9.7rc2 是 prerelease；回滚档为 0.9.5。
- 工具锚点前缀是 `Fast Rendering: v0.9.`；FR 升到 v0.10 时需要同步改 `tools/smoke_run.py` 与 `tools/m1b_measure.py`，否则 `session_offset` 返回 0、`fr_present=False`（门禁会 fail-closed，不会误报通过）。
- 菜单冒烟不调用 `ensureLoaded`；线程绑定的真实证据来自 Base 手动读档。
- 260mods 为 agent-only；运行期 mod 的验证在 Base。
- 不宣称菜单时间收益；数字只作为新基线。
- `tests/tools/test_smoke_check.py` 的 2 个既有失败与 M-1f 无关。
