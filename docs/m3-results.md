# M3（0–50 s 桶）结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…）
> 基线：M-1f warm 中位 60.6 s；旧 G-01' ≤48.5 s；**最终 G-01'' = ≤50 s（2026-10-31 修订）**

## 1. 相位证据

### 1.1 历史 control 轮（`phase` 档，timeline 修复前）

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

### 1.2 C1 修复后的真实相位（pre-reboot，miko-lite，2026-10-31 17:43）

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
  file index 只削减 `initFileLoaders` 的 crawl 部分（同日 `miko-lite` A/B −6.5 s）。
  “0–50 s 内是否还有安全杠杆”的停止条件裁决见 §4（2026-10-31 已裁决：G-01'' = ≤50 s）。


## 3. 杠杆与 A/B

### 3.1 索引构建（pre-reboot，两轮 warm 构建，不计入 A/B）

- 原始构建：`python -I tools/smoke_run.py --profile miko-lite --rounds 1 --json-out build/m3-index-build.json`
- v2 格式戳重建：同一命令，`--json-out build/m3-timeline-rebuild.json`

- **两轮独立的 warm 构建**，均为完整 crawl + 写入：
  - 原始构建（`build/m3-index-build.json`，agent 日志 08:41）：menu **83.2 s**，
    `file index: written entries=223536, dirs=17067`；索引落盘
    `saves/hypernova/file-index.idx.gz`（3,332,575 B）。
  - v2 格式戳重建（`build/m3-timeline-rebuild.json`，agent 日志 09:41）：menu **83.2 s**，
    `file index: absent, corrupt, or FR version/shape mismatch; full crawl` →
    `written entries=223536, dirs=17067`。
- 两轮都按约定排除，不参与 A/B 中位数；一次性构建成本 = 较同日 control 中位 68.1 s
  慢 **+15.1 s**。
- 排除冷缓存解释：两轮均 `preload=hit`（2,113 条；8 ms / 25 ms），
  `read_bytes_menu` 805,074,400（原始）/ 804,205,637（重建），与 control 三轮的
  802,191,527 / 803,356,488 / 804,566,658 基本一致。因此 +15.1 s 不是 scripts
  冷启动或 OS 缓存差异的大头；两轮独立 warm 构建给出**相同**的构建成本，且都是
  完整 crawl + 相同 223,536/17,067 写入，进一步支持**最可能**是同步 `save` 路径
  （223,536 entries + 17,067 dirs + key 归一化 + gzip）。但仍没有“关闭 save”的
  对照，所以这是**高概率推断，不是已隔离的结论**。
- 诚实修正：计划预期首次构建只慢 1–2 s，实测 +15.1 s，该预期是错的；两轮构建
  成本一致，说明不是单轮异常（更细的 save 拆分留给下一里程碑）。
- 产品含义：首次安装、更换 mod 列表、修改 mod 目录内容都会触发重建，各慢约 15 s。
  最坏情况是某个 mod 在会话中往自己的目录写文件（日志/缓存/生成配置）→ 下一次启动
  `directory changed [...]` → 全量 crawl + 再写索引；对这类 mod 集合，杠杆从
  “净赚 6.5 s”变成“每次启动净亏约 15 s”。回滚开关见 §3.3。
- 后续方向（不在 M3 范围）：异步/惰性 save，或更快的 key 生成路径，可削减这项
  一次性成本。

### 3.2 同日 A/B（pre-reboot，`miko-lite`，warm，control → treatment 各 3 轮）

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
| Java 17 测试 | **97 found / 96 successful / 1 aborted**（既有 Windows symlink 权限限制）/ **0 failed**（Task 7 first-wins 修复后的完整 agent 套件） |
| Java ABI audit | `ok=true`，自有 class 40 个全为 major 61，`java21_api_hits=[]` |
| textures | `normal_before_menu=0`、`patched=true`、`mismatch_line=null`、`fr_present=true`、`failed_texture_lines=0`、`gate_ok=true` |
| base | `ok=true`，menu 8.6 s；`file index: written entries=15243, dirs=474`（首次构建，机制可用） |
| no-FR | **通过**：menu **1267.9 s**；`fr_present=false`、`fr_missing_disabled=true`、`normal_before_menu=0`（`cleaned` 口径）、`patched=true`、`failed_texture_lines=0`、`gate_ok=true`；agent 未注册 `file index` |

回滚开关：`-Dhypernova.fileIndex=false`（系统属性优先）或
`data/config/hypernova/hypernova.json` 的 `"fileIndex": { "enabled": false }`。

### 3.4 干净重跑（post-reboot）与无 Hypernova 基线

> §3.1–§3.3 是 pre-reboot 结果；以下是重启后干净环境的 A/B 与“移除 agent、保留 FR/VOpt”
> 基线。干净轮仍为 `miko-lite` warm。

#### 3.4.1 干净 A/B

| 轮次 | control menu_s | treatment menu_s | delta |
|---|---:|---:|---:|
| 首轮 3+3 | 53.6 / 51.6 / 49.1，中位 **51.6** | 47.6 / 47.6 / 46.6，中位 **47.6** | 4.0 s / 7.75% |
| 确认 3+3（control warm-up） | 50.1 / 50.1 / 48.1，中位 **50.1** | 47.6 / 48.1 / 48.1，中位 **48.1** | 2.0 s / 3.99% |

- 首轮 treatment 中位 47.6 ≤ 48.5；确认轮 48.1 ≤ 48.5，**余量 0.4 s**。
- 干净 file-index 收益区间 **2.0–4.0 s**；pre-reboot 的 6.5 s（§3.2）保留为历史口径，
  不与干净轮混用。

#### 3.4.2 无 Hypernova 基线（移除 agent，保留 FR/VOpt）

- 3 轮 **83.1 / 75.6 / 75.6 s**，warm 中位 **75.6 s**。
- `loading_normal_before_menu=30378`：证明无 Hypernova 时法线图在启动期全量加载；
  `m1b_measure` 报出的 `patched=true` 是旧 agent 日志的残留行，**不属于本轮**。
- **整体 Hypernova 贡献**：无 Hypernova **75.6 s** → 有 Hypernova control **50.1 s**，
  约 **25.5 s**（textures + scripts + file index 合计；不是 file-index 单独收益）。
  file-index 单独：50.1 → 48.1 = **2.0 s**（干净区间 2.0–4.0 s）。

## 4. 停止条件 / 目标修订

- **最终裁决（用户，2026-10-31）：修订 G-01'' = ≤50 s。** 两个干净 post-reboot
  treatment（47.6 s / 48.1 s）均 ≤50 s（余量 2.4 / 1.9 s）；file index 默认开启。
- **干净 A/B 证据（post-reboot，`miko-lite` warm，见 §3.4.1）**：
  - 首轮 3+3：control 中位 **51.6 s** → treatment 中位 **47.6 s**，
    delta **4.0 s / 7.75%**；treatment ≤48.5。
  - 确认 3+3（control warm-up）：control 中位 **50.1 s** → treatment 中位 **48.1 s**，
    delta **2.0 s / 3.99%**；treatment ≤48.5，余量 0.4 s。
- **口径与边界**：
  - 旧 G-01'（≤48.5 s）在两个干净轮上数值达成（47.6 / 48.1），但余量只有
    0.4–0.9 s，且干净环境 control 50.1 s 比 M-1f 基线 60.6 s 快约 10 s；
    pre-reboot 的 61.6 s 未达标。因此不把“≤48.5 s”作为稳定目标，修订为 ≤50 s。
  - 干净 file-index 收益：确认轮 **2.0 s**、首轮 **4.0 s**，区间 **2.0–4.0 s**；
    §3.2 的 pre-reboot **6.5 s** 只作历史口径，不与干净轮混用。
  - 整体 Hypernova 贡献：无 Hypernova warm 中位 **75.6 s**（§3.4.2）→ 有 Hypernova
    control **50.1 s**，约 **25.5 s**（textures + scripts + file index 合计，
    不是 file-index 单独收益）。无 Hypernova 臂保留 FR/VOpt，仅移除 agent；
    `loading_normal_before_menu=30378` 证明法线图仍在启动期全量加载。
- **真实相位（C1 修复后，pre-reboot，menu 65,868 ms）**：`initFileLoaders`
  **4,983 ms**、`initSpecStore` **25,950 ms**、`initMods` **32,581 ms**；闭合校验
  2,354 + 4,983 + 25,950 + 32,581 = **65,868 ms** = `menu_ms`；
  `phases_approximate=[]`（三个相位都来自真实锚点，见 §1.2）。该轮用于相位归因，
  不是干净 A/B 的轮次。
- **pre-reboot 历史结果（保留，不覆盖）**：§3.2 control 中位 **68.1 s** →
  treatment **61.6 s**（**6.5 s / 9.54%**）；旧 G-01'（≤48.5 s）**未达标**，
  当时按规格 §7 M3 触发停止条件：`initSpecStore` + `initMods` = 58,531 ms
  （占 menu 的 **88.9%**），再削约 **12.1 s** 只能动 vanilla spec/JSON
  （107,526 次 `Loading JSON`）与 256 个 mod 的 `onApplicationLoad`
  （约 28 s，含在 `initMods` 内）；没有安全杠杆能在不裁 mod、不改 FR/VOpt、
  不改启动档的前提下再拿 12 s。pre-reboot 外推 60.6 − 6.5 ≈ 54.1 s **未实测**，
  已被干净重跑取代，不再作为结论。该停止条件与“处置待用户”是历史记录，
  已由本节 ≤50 s 裁决取代。
- **一次性成本**：两轮独立的 warm 构建（原始索引 + v2 格式戳重建）均为 **83.2 s**
  （各较 pre-reboot 同日 control 中位 68.1 s 慢 +15.1 s），均完整 crawl 并写入
  223,536 entries / 17,067 dirs；两轮 `preload=hit`、`read_bytes_menu≈804–805 MB`
  与 control 一致，**最可能**是同步 `save` 路径（223,536 条 + 17,067 目录 +
  key 归一化 + gzip）；两轮同价加强了该推断，但仍未单独隔离 save。首次安装/
  更换 mod 列表/修改 mod 目录内容会再次重建，各慢约 15 s；若某个 mod 在会话中
  往自己目录写文件，下一次启动会 `directory changed` → 全量 crawl + 重建，
  对该 mod 集合杠杆变成每次净亏。
- **回滚**：`-Dhypernova.fileIndex=false`（系统属性优先）或
  `data/config/hypernova/hypernova.json` 的 `"fileIndex": { "enabled": false }`。
- **不做**：裁 mod、改 FR/VOpt、改启动档、为凑目标做不安全裁剪。
