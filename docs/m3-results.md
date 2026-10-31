# M3（0–50 s 桶）结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…）
> 基线：M-1f warm 中位 60.6 s；G-01' ≤48.5 s

## 1. 相位证据

### 1.1 历史 control 轮（timeline 修复前）

| 轮 | menu_s | crawl files | crawl ms | initFileLoaders ms | initSpecStore ms | initMods ms | preload |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 73.6 | 229754 | 5146 | n/a | n/a | n/a | hit |
| 2 | 73.1 | 229754 | 5567 | n/a | n/a | n/a | hit |
| 3 | 68.1 | 229754 | 4591 | n/a | n/a | n/a | hit |
| 中位 | 73.1 | 229754 | 5146 | n/a | n/a | n/a | hit |

> 说明：这三轮安装的 agent jar（2026-10-31 11:26）确实早于 Task 1 的 timeline 代码；
> 但“换上新 jar 就会好”是错的——Task 5 装的新 jar 仍是 **0 条 mark**。真正根因是
> 旧 transformer 的目标 `com/genir/renderer/overrides/loading/ResourceLoaderState`
> 被 FR 的 `BytecodeFileTransformer` 以 `mergeClass` 方式并入游戏类
> `com.fs.starfarer.loading.ResourceLoaderState`，donor 类本身从不加载
> （C1，final-review 已核实）。所以当时只能用 `crawl.ms` 代理 `initFileLoaders`。

### 1.2 C1 修复后的真实相位（miko-lite，2026-10-31 17:43）

- 证据：`build/m3-timeline-run.json`（menu 66.6 s，`file index: loaded ...`）；
  `build/m3-timeline-proof.json`（`tools/m3_phase.py` 输出）。
- 环境：FR 0.9.7rc2；file index 格式 2，首轮重建后本轮命中（`loaded`，无 crawl 行）。
- 本轮是**一次真实运行**，不是中位数；锚点全部来自实际执行的类。

| timeline anchor | rel_ms | 来源 |
|---|---:|---|
| `loader.start` | 2,354 | `FileLoaderFast.<init>` 入口 |
| `loader.end` | 5,423 | `FileLoaderFast.<init>` RETURN 前 |
| `dds.start` | 5,424 | `DDSIntegration.initialize` 入口 |
| `dds.end` | 7,337 | `DDSIntegration.initialize` RETURN 前 |
| `script.loader` | 5,439 | `ScriptCacheHook.preload` |
| `script.first` | 7,744 | 首次 `ScriptCacheHook.onFindClass` |
| `mods.start` | 33,287 | `MarkovNames.loadIfNeeded`（合并后 `initMods` 的第一条语句） |
| menu | 65,868 | game log 主菜单锚点（相对 FR session） |

| phase | ms | 口径 |
|---|---:|---|
| `initFileLoaders` | 4,983 | `loader.start` → `dds.end` |
| `initSpecStore` | 25,950 | `dds.end` → `mods.start`（含 script/texture worker 等待） |
| `initMods` | 32,581 | `mods.start` → menu |
| `scriptSpanMs` | 42,520 | menu 前最后一个 `find span` 的 first→last |

- 闭合校验：2,354 + 4,983 + 25,950 + 32,581 = 65,868 ms = `menu_ms`。
- `phases_approximate = []`：三个相位都用了真实锚点，没有用 fallback 数值。
- 为什么 `mods.start` 不是 `FileLoader.initModLoading`：`FileLoader` 也是
  `mergeClass` donor（`BytecodeFileTransformer` 的 `com/fs/util/C` case），其自身
  类不会加载；`initModLoading` 只在合并后的游戏类里执行，前置注册的 transformer
  看不到它。`MarkovNames.loadIfNeeded()` 是合并后 `initMods` 的第一条实际执行语句，
  因此用它做锚点。premain 日志会明确写出：
  `timeline: donor target not executed (mergeClass donor, not a class load) ...`。

## 2. 归因

- **`initSpecStore` 25,950 ms**（menu 的 39.4%）：spec/JSON/资源加载 + script/texture
  worker 的等待；这是 0–50 s 桶内最大的单块。
- **`initMods` 32,581 ms**（49.5%）：`ScriptStore.loadModClasses()` +
  所有 `ModPlugin.onApplicationLoad`。
- **`initFileLoaders` 4,983 ms**（7.6%）：索引命中路径；本轮没有 `Cached ... files`
  行（命中时 FR 不 crawl），历史 control 的 crawl 中位为 5,146 ms。DDS 初始化
  1,913 ms（5,424→7,337）包含在 `initFileLoaders` 内。
- **`scriptSpanMs` 42,520 ms**：`find span` 的 first=7,744 ms，最后一个 menu 前
  span 的 last≈50,264 ms（相对 agent 起点），即脚本查找活动横跨 `initSpecStore`
  与 `initMods`，不是独立相位。
- 结论：修复后的真实相位表明 0–50 s 主要由 `initSpecStore` + `initMods` 占据；
  file index 只削减 `initFileLoaders` 的 crawl 部分（同日 A/B −6.5 s）。
  “0–50 s 内是否还有安全杠杆”的停止条件裁决见 §4（需用户裁决，不由本次修复代替）。


## 3. 杠杆与 A/B

### 3.1 索引构建（单独一轮，不计入 A/B）

`python -I tools/smoke_run.py --profile miko-lite --rounds 1 --json-out build/m3-index-build.json`

- agent 日志：`file index: written entries=223536, dirs=17067`；索引落盘
  `saves/hypernova/file-index.idx.gz`（3,332,575 B）。
- 本轮 menu **83.2 s**：一次性构建成本（较同日 control 中位 68.1 s 慢 **+15.1 s**），
  按约定排除，不参与 A/B 中位数。
- 排除冷缓存解释：本轮 `preload=hit`（2,113 条，8 ms），
  `read_bytes_menu=805,074,400`，与 control 三轮的 802,191,527 / 803,356,488 /
  804,566,658 基本一致。因此 +15.1 s 不是 scripts 冷启动或 OS 缓存差异，而是
  索引 `save` 路径本身（223,536 entries + 17,067 dirs + key 归一化 + gzip）。
- 诚实修正：计划预期首次构建只慢 1–2 s，实测 +15.1 s，该预期是错的；更细的拆分
  （例如在同一 warm 机器上做第二次构建）留给 Task 6 / 下一里程碑。
- 后续方向（不在 M3 范围）：异步/惰性 save，或更快的 key 生成路径，可削减这项
  一次性成本。

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
| no-FR | **通过**：menu **1267.9 s**；`fr_present=false`、`fr_missing_disabled=true`、`normal_before_menu=0`（`cleaned` 口径）、`patched=true`、`failed_texture_lines=0`、`gate_ok=true`；agent 未注册 `file index` |

回滚开关：`-Dhypernova.fileIndex=false`（系统属性优先）或
`data/config/hypernova/hypernova.json` 的 `"fileIndex": { "enabled": false }`。

## 4. 停止条件 / 目标修订

（Task 6 填充）
