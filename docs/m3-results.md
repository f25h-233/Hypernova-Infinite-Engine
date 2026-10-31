# M3（0–50 s 桶）结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…）
> 基线：M-1f warm 中位 60.6 s；G-01' ≤48.5 s

## 1. 同日 control 相位（miko-lite-phase，3 轮）

| 轮 | menu_s | crawl files | crawl ms | initFileLoaders ms | initSpecStore ms | initMods ms | preload |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 73.6 | 229754 | 5146 | n/a | n/a | n/a | hit |
| 2 | 73.1 | 229754 | 5567 | n/a | n/a | n/a | hit |
| 3 | 68.1 | 229754 | 4591 | n/a | n/a | n/a | hit |
| 中位 | 73.1 | 229754 | 5146 | n/a | n/a | n/a | hit |

> 说明：本轮安装的 agent jar（2026-10-31 11:26）早于 Task 1 的 timeline 代码，`timeline` 为空是预期的；按 Task 2 逃逸舱，用 `crawl.ms` 代理 `initFileLoaders`（FR 中 `initFileLoaders` = crawl + DDS init，侦察实测 DDS 62 ms）。`initSpecStore` / `initMods` 待 Task 5 装新 jar 后复核。

## 2. 归因

- 目录枚举：crawl 229,754 files，4,591 / 5,146 / 5,567 ms，中位 **5,146 ms**（约为 menu 的 7.0%）。三轮文件数完全一致，说明枚举成本稳定、可被索引直接削减。
- spec/JSON 解析：本轮 timeline 为空（旧 jar），`initSpecStore` 未测得，不用猜测值填充。
- mod init：同上，`initMods` 未测得，待 Task 5 新 jar 复核。
- 结论：crawl 中位 5,146 ms ≥ 2,000 ms，代理的 `initFileLoaders` 同样 ≥ 2,000 ms → **GO Task 3/4/5**。同日 control 中位 73.1 s，比 M-1f 的 60.6 s 慢 12.5 s（Review Focus #6 的同日漂移）；后续 A/B 只与同日 control 比，G-01' 另报相对 60.6 s 的口径。

## 3. 杠杆与 A/B

### 3.1 索引构建（单独一轮，不计入 A/B）

`python -I tools/smoke_run.py --profile miko-lite --rounds 1 --json-out build/m3-index-build.json`

- agent 日志：`file index: written entries=223536, dirs=17067`；索引落盘
  `saves/hypernova/file-index.idx.gz`（3,332,575 B）。
- 本轮 menu **83.2 s**（含首次全量写索引），按约定排除，不参与中位数。

### 3.2 同日 A/B（`miko-lite`，warm，control → treatment 各 3 轮）

| 轮 | control menu_s<br>（`-Dhypernova.fileIndex=false`） | treatment menu_s<br>（默认开启） |
|---|---:|---:|
| 1 | 68.1 | 61.6 |
| 2 | 69.1 | 62.6 |
| 3 | 67.1 | 61.6 |
| **中位** | **68.1** | **61.6** |

- `delta_s = 6.5`，`delta_pct = 9.54%`（相对同日 control；`build/m3-ab-summary.json`）。
- 索引命中证据：treatment 三轮均为
  `file index: loaded mod_entries=223536, total_entries=229499, dirs=17067, bytes=3332575`，
  无 `full crawl`。`total_entries` 比写入多 5,963 条，为 volatile roots
  （saves / enabled_mods / mikohome 等）每轮重扫，符合设计。
- 相对 M-1f 基线 60.6 s：treatment 61.6 s（+1.0 s），control 68.1 s（+7.5 s）；
  同日漂移按 Review Focus #6 单列，不与 A/B 收益混用。
- 6.5 s ≥ 1.0 s，未触发反向顺序复核，判定杠杆有效。

### 3.3 门禁

| 门禁 | 结果 |
|---|---|
| Java 17 测试 | 90 found / 89 successful / 1 aborted（既有 symlink 环境限制）/ 0 failed |
| Java ABI audit | `ok=true`，自有 class 40 个全为 major 61，`java21_api_hits=[]` |
| textures | `normal_before_menu=0`、`patched=true`、`mismatch_line=null`、`fr_present=true`、`failed_texture_lines=0`、`gate_ok=true` |
| base | `ok=true`，menu 8.6 s；`file index: written entries=15243, dirs=474`（首次构建，机制可用） |
| no-FR | pending (controller) |

回滚开关：`-Dhypernova.fileIndex=false`（系统属性优先）或
`data/config/hypernova/hypernova.json` 的 `"fileIndex": { "enabled": false }`。

## 4. 停止条件 / 目标修订

（Task 6 填充）
