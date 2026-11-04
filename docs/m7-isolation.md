# M7 单变量隔离：MixinFR vs Java 17 / FR 0.9.5（2026-11-04）

> 实验根：`D:\github\Hypernova-Infinite-Engine\SS098_Hypernova_Compat_AuditTest\install\optimized-2026.10.15`
> 目标：判断 A 路线（MixinFR 1.2.5 + FR 0.9.5 + JRE 17）全量慢，是
> **MixinFR** 的问题，还是 **Java 17 / FR 0.9.5** 的问题。
> 方法：FR 0.9.5 单 JVM、无 MixinFR/Parallel；C1=Java 28，C2=JRE 17；
> 每组冷/热1/热2 三次；另补一次 **A−Parallel**（MixinFR 1.2.5 + JRE 17，
> 无 Parallel/Prepatcher）作严格对照；串行启动、按 PID 结束、精确主菜单锚点。

## 1. 判定

| 组 | 配置 | 到菜单（3 次） | 中位 | 每 miss 耗时（中位） | 判定 |
|---|---|---|---|---|---|
| C1 | FR 0.9.5 + Hypernova + VOpt，**Java 28**，无 MixinFR/Parallel | 108.213 / 108.210 / 102.188 s | 108.21 s | **5.23 ms** | 正常 |
| C2 | 同 C1，**JRE 17** | 114.219 / 102.190 / 102.165 s | 102.19 s | **5.73 ms** | 正常 |
| A | MixinFR 1.2.5 + FR 0.9.5 + JRE 17 + Parallel + Hypernova + VOpt | 1400 s 预算内未到菜单 | — | **99.84 ms**（最终 1400 s 证据） | 慢 |
| A−Parallel | MixinFR 1.2.5 + FR 0.9.5 + JRE 17，**无 Parallel/Prepatcher** + Hypernova + VOpt | 900 s 预算内未到菜单（stage=scripts） | — | **108.77 ms**（900 s 快照，8,016 miss） | 慢 |

**结论：C1/C2 均正常，A 与 A−Parallel 慢约 17–21 倍；慢因是 MixinFR，
不是 Java 17、FR 0.9.5 或 Parallel。** C1 与 C2 只差 Java 版本和 5 个
JDK28-only 参数，二者都正常，直接排除“Java 17 慢”；C2 与 A 共用 JRE 17 +
FR 0.9.5，C2 正常，排除“FR 0.9.5 在 JRE17 下慢”；A−Parallel 去掉 Parallel
后仍以 ~109 ms/miss 慢，排除“Parallel 慢”。剩余主要差异是 MixinFR。

## 2. 配置与方法

### 2.1 两组参数

| 项 | C1 | C2 |
|---|---|---|
| Java | Temurin `28-beta+13-ea`（`Starsector-098-260mods/jdk-28+13`） | Zulu `17.0.10`（实验根 `jre`） |
| FR | 0.9.5 `fr.jar` + `fr.agent.jar`（260mods 备份，sha256 `7ee51ee9…` / `8b9c7871…`） | 同 C1 |
| Hypernova | `build/agent/hypernova.agent.jar`（297,244 B）+ `build/java/hypernova.jar` | 同 C1 |
| VOpt | `VramOptimizer` 1.0.45（enabled） | 同 C1 |
| MixinFR / Parallel | 无 | 无 |
| 内存 | `-Xms4096m -Xmx10240m -XX:MaxDirectMemorySize=6G` | 同 C1 |
| 参数集 | Miko_Lite 派生（G1GC、8 项 add-opens 等，含 JDK28-only 5 项） | 同 C1，去掉 `UseCompactObjectHeaders`、`HotCodeHeap`、`AlwaysPreTouchStacks`、`enable-final-field-mutation`、`ErrorLogSecondaryErrorDetails` |
| agent 顺序 | Hypernova → FR | 同 C1 |
| classpath | `fr.jar` 首位 + FR 0.9.5 原 `fr.vmparams` 的 stock jar 列表 | 同 C1 |
| 启动 | `-DlaunchDirect=true -DstartRes=1707x1067 -DstartFS=false -DstartSound=true` | 同 C1 |

- **A−Parallel（单次）**：MixinFR 1.2.5（`vendor/MixinFR-1.2.5/MixinFR` →
  `mods/MixinFR`，mod id `MixinLib`）+ Hypernova + VOpt；无 StarsectorParallel、
  无 Prepatcher；JRE 17；参数与 C2 相同，另加 `--enable-preview`
  （MixinFR/route-a 兼容项）；agent 顺序 MixinLib-bridge → Hypernova；
  classpath 为 stock（无 `fr.jar`，MixinFR 自带 FR 0.9.5）；enabled 254
  （C2 的 256 − 3 个声明 jar 缺失 mod + `MixinLib`；`jc_sf` 仍禁用）。

### 2.2 冷/热定义（修订后）

- 首次尝试“删空 `mods/GraphicsLib/cache` + `mods/shaderLib/cache`”导致
  44,822 条 `normal.png not found or failed to load`、进程 WorkingSet
  16.1 GB、可用物理 4.4 GB、页面文件用量 4.85 GB、白屏，记为
  `invalid (paging/blank)`，不计入。
- 最终冷跑定义：**保留/恢复法线缓存基线**（本次基线为 44,072 文件 /
  1.7 GB，快照在 `evidence/isolation/cache-baseline/GraphicsLib`），
  只清 `starsector-core/cache/mixinfr` 与 Hypernova 脚本缓存；
  始终保留 `starsector-core/cache/startup-optimization`（2.1 GB 字体缓存）
  与 `mods/DDSCache`；运行前确认两个 cache 目录存在且可写。
- 热跑：不清任何缓存。
- 启动前写 `SS098_Hypernova_Compat_AuditTest/evidence/.game-lock`，结束释放；
  只按 PID 结束（`taskkill //PID`，必要时 `//F`），未使用 `/IM java.exe`。
- 每次上限 600 s；600 s 时若仍在 rules/scripts 延到 900 s；C1/C2 六次均在
  115 s 内到菜单，未触发延长；A−Parallel 按允许上限用到 900 s。

## 3. 六次有效结果

| 组 | 相位 | 到菜单 (s) | wall (s) | `find span` (ms) | finds | hits | misses | ms/miss | 脚本缓存 preload |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| C1 | cold | 108.213 | 111.723 | 65,603 | 12,851 | 59 | 12,792 | 5.13 | 否 |
| C1 | warm1 | 108.210 | 111.926 | 58,186 | 12,851 | 1,735 | 11,116 | 5.23 | 是（2,113 条/6 ms） |
| C1 | warm2 | 102.188 | 105.802 | 65,678 | 12,877 | 1,761 | 11,116 | 5.91 | 是 |
| C2 | cold | 114.219 | 117.766 | 64,750 | 12,841 | 53 | 12,788 | 5.06 | 否 |
| C2 | warm1 | 102.190 | 105.969 | 63,923 | 12,877 | 1,761 | 11,116 | 5.75 | 是 |
| C2 | warm2 | 102.165 | 105.511 | 63,692 | 12,877 | 1,761 | 11,116 | 5.73 | 是 |

| 组 | 到菜单 中位/最小/最大 (s) | `find span` 中位/最小/最大 (ms) | ms/miss 中位/最小/最大 |
|---|---|---|---|
| C1 | **108.21 / 102.188 / 108.213** | 65,603 / 58,186 / 65,678 | **5.23** / 5.13 / 5.91 |
| C2 | **102.19 / 102.165 / 114.219** | 63,923 / 63,692 / 64,750 | **5.73** / 5.06 / 5.75 |

要点：冷跑与热跑的菜单时间几乎一致（C1 108.2/108.2/102.2；C2
114.2/102.2/102.2），说明在该基线法线缓存下，菜单时间主要由固定纹理/资源
阶段决定；脚本侧变量是 `find span`，两组都在 58–66 s。

### 3.1 A−Parallel（单次严格对照）

| 指标 | 值 |
|---|---|
| 到菜单 | **未到**（900 s 超时，stage=scripts） |
| wall | 904.9 s |
| `find span` | 871,879 ms；finds 8,078 / hits 62 / misses 8,016 |
| ms/miss | **108.77** |
| sourced | 8,016（sourceless 0） |
| `Loading rule` | 19,681 |
| `Compiling script` | 14,419 |
| `JavaSourceIClassLoader` / `Janino` | 0 / 0 |
| Fatal / OOM | 0 / 0 |

900 s 快照时脚本仍在加载（8,016/约 12.8k miss），因此总 miss 数低于 A 的
12,774；可比的每 miss 耗时与 A 的 99.84 同量级，仍为 C1/C2 的约 20 倍。

## 4. 脚本侧指标

| 指标 | C1（Java 28） | C2（JRE 17） | A（MixinFR+Parallel） | A−Parallel（MixinFR） |
|---|---|---|---|---|
| `Compiling script` 队列行 | 14,769（三次相同） | 14,769（三次相同） | 14,919（最终 1400 s） | 14,419（900 s 快照） |
| `Loading rule` 行 | **0** | **0** | 25,992（旧日志；任务给定口径 23,528） | 19,681（900 s 快照） |
| `JavaSourceIClassLoader` 行 | **0** | **0** | 0 | **0** |
| `Janino` 行 | 3（同一段 MagicLib 成就告警栈，非编译） | 3（同） | 0 | **0** |
| Fatal / OOM | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| AoTD“市场测试失败” | 0 | 0 | 0 | 0 |

- `Compiling script` 是 FR `ScriptStore.loadScript` 在 `loadClass` 前的
  **队列日志**，jar 命中也会打印，不是编译计数（见 `docs/m7-a-debug.md`）。
- 独立 FR 0.9.5 进程没有输出 `Loading rule` 行；A 的 25,992 行来自
  MixinFR 路径。该行数不能跨这两套加载路径直接比较。
- `Janino` 3 行是 `MagicAchievementManager` 对空 class 名的
  `ClassNotFoundException` 栈；`JavaSourceIClassLoader` 为 0，未发生真实
  的 Janino 源码编译。

### 4.1 A 参考（不重跑，引用 `docs/m7-a-debug.md` / `evidence/a-debug`）

| 项 | A 最终 1400 s 证据 | 任务给定口径 |
|---|---|---|
| 到菜单 | 1402.9 s 预算内未到；结束在 textures | 1400 s 未到 |
| `find span` | 1,275,342 ms；finds 12,842 / hits 68 / misses 12,774 | ~12,156 finds / ~12,090 misses |
| ms/miss | **99.84** | ~72 |
| `Loading rule` | 25,992（旧日志） | 23,528 |
| `Compiling script` | 14,919 | — |
| Fatal / OOM | 0 / 0 | 0 / 0 |

两种口径下，A 的每类耗时都是 C1/C2 的约 17–21 倍（按任务口径约 13–21 倍）。
C1/C2 的 14,769 条队列行与 A 的 14,919 条接近，说明慢的不是“脚本数量”，
而是**每类查找/加载成本**。

A−Parallel（无 Parallel/Prepatcher）在 900 s 时仍在 scripts，8,016 miss 用
871,879 ms，即 **108.77 ms/miss**；与 A 的 99.84 同量级，仍为 C1/C2 的
约 19–21 倍。Parallel 因此被排除；MixinFR 路径是唯一剩下的主变量。

## 5. 环境前提与偏差（对 C1/C2/A−Parallel 一视同仁）

1. **`mods/DDSCache` 缺失**：首次 C1 在 DDS 初始化 22.3 s 直接
   `NoSuchFileException: ..\mods\DDSCache`（FR 0.9.5
   `DDSIntegration.findDDSMetadata`）。已创建空目录；冷跑不清除。
2. **LunaSettings 全量损坏**：实验根 `saves/common/LunaSettings` 原有
   257 个文件全部为同一份 1521 B 内容；IndEvo 在 81.4 s
   `LunaSettings.getInt(...) == null` → `ExceptionInInitializerError`。
   已备份到 `evidence/isolation/lunasettings-corrupt-backup/`，并从 260mods
   恢复 75 份真实设置。
3. **`jc_sf`（SF-幽灵部队）自检失败**：
   - 上游包 `D:\download\[C][势力]幽灵部队 1.1.3.zip` 解压到
     `evidence/sf-upstream/`，`SF-幽灵部队` **1,395 文件 / 33,112,567 B**；
   - 与 260mods 源逐文件 SHA-256 对比 **0 差异**（含 `mod_info.json`、
     `jc_asm.jar`、README、`settings.json`、`LunaSettings.csv`），即本地源
     就是上游原包；
   - 上游包在实验根仍报“幽灵部队模组文件损坏”；**JRE 17 与 Java 28 均复现**
     （JRE17 诊断 `diag-jre17-jcsf` 在 123.8 s 报同一错误）；A 路线
     （MixinFR）当时通过；
   - 因此这不是文件损坏，也不是 Java 版本差异。为让对照跑通，C1/C2/
     A−Parallel 均从 `enabled_mods.json` 移除 `jc_sf`（目录保留）。**A 参考
     启用 `jc_sf`**，这是本实验与 A 的唯一内容模组差异；它不改变每类耗时结论。
4. **AoTD 核心 jar**：`aotd_theory_of_toolbox` 要求把
   `mods/Ashes of  The Domain - Theory of Toolbox/0.98a/starfarer.api.jar`
   （sha256 `ad41a688…`）替换 `starsector-core/starfarer.api.jar`；否则
   374.9 s 报“市场测试失败”。已在全部对照组应用；收尾恢复原版
   `769c8e94…`。
5. **SF 目录**：原为指向 260mods 的 junction（`find -type f` 为 0）；已改为
   上游实体副本（1,395 文件 / 35 MB）。
6. **内存**：`-Xms4G -Xmx10G -XX:MaxDirectMemorySize=6G`（A 为 8G/10G），
   两组相同；用于避免上一轮白屏/换页。

## 6. 口径与限制

- **Parallel 已隔离（A−Parallel）**：A−Parallel 去掉 StarsectorParallel 与
  Prepatcher，保留 MixinFR 1.2.5 + Hypernova + VOpt + JRE17，仍 900 s 未到
  菜单；8,016 miss 用 871.9 s（**108.77 ms/miss**），与 A 的 99.84 ms/miss
  同量级，C1/C2 为 5.2–5.7 ms/miss。12-mod 子集“+Hypernova 17.9 s /
  +Hypernova+Parallel 15.6 s”也一致：**Parallel 不是慢因，MixinFR 是**。
- **A 的 `Loading rule`**：A 走 MixinFR 路径才有该行；独立 FR 0.9.5 为 0。
  两套加载路径的规则日志不可直接对比，但 `find span` 是同一 Hypernova
  指标，可对比。
- **冷跑不是空法线缓存**：为规避 clean-cache 白屏/换页，冷跑使用 44,072
  文件基线；真正的“空缓存冷跑”在本机 32 GB 内存下不稳定，已记为 invalid。
- **jc_sf 差异**：A 启用、对照禁用；去掉的是内容模组，队列行从 A 的
  14,919 变为 14,769（约 −1%），不影响“每 miss 5 ms vs 100 ms”的判断。

## 7. 无效运行（保留日志，不计入三次）

| 运行 | wall (s) | 原因 | 处理 |
|---|---:|---|---|
| `c1-cold-attempt1-dds-crash` | 231.1 | 缺 `mods/DDSCache`，DDS 初始化 22.3 s 抛 `NoSuchFileException` | 创建空 DDSCache 后重跑 |
| `c1-cold-attempt2-luna-npe` | 306.4 | LunaSettings 257×1521 B 损坏，IndEvo 81.4 s NPE | 恢复 75 份真实设置后重跑 |
| `c1-cold-invalid-paging` | 471.5 | 删空法线缓存 → 44,822 条 normal-map 错误；WorkingSet 16.1 GB、可用物理 4.4 GB、页面文件 4.85 GB、白屏；无 OOM/Fatal | 按 PID 22956 结束；改冷跑定义 |
| `c1-cold-invalid-jc_sf-fatal` | 288.4 | `jc_sf` 自检 96.2 s 失败 | 换上游包重跑 |
| `c1-cold-invalid-jc_sf-upstream` | 291.4 | 上游包仍自检失败（105.2 s） | 对比证明源未损坏；禁用 jc_sf |
| `c1-cold-invalid-aotd` | 507.6 | AoTD 374.9 s 报“市场测试失败” | 替换核心 jar 后重跑 |
| `diag-jre17-jcsf` | ~200 | 诊断：JRE17 也在 123.8 s 报 jc_sf 自检失败 | 仅诊断，不计入 |

## 8. 现场恢复

- `starsector-core/starfarer.api.jar` 已恢复原版 `769c8e94…`；`.orig` 已删除。
- 临时 `starsector-core/fr.jar`、`fr.agent.jar`、`m7-isolation-c1/c2.vmparams`、
  `m7-isolation-a-minus-parallel.vmparams` 已删除。
- `mods/MixinFR`、`mods/hypernova_infinite_engine` 已删除；
  `mods/enabled_mods.json` 已恢复为实验前 256 项（含 `jc_sf`，不含
  Hypernova/MixinLib）。
- `vmparams` sha256 仍为 `8f88ab53…`（未改）。
- 无游戏进程、无 `.game-lock`；未 push。
- 保留：`mods/SF-幽灵部队` 上游实体副本（1,395/35 MB）、空 `mods/DDSCache`、
  75 份真实 LunaSettings、`mods/GraphicsLib/cache` 44,072 文件、
  `mods/shaderLib/cache` 已从 260mods 恢复 11,803 文件/447 MB。
- 证据：`SS098_Hypernova_Compat_AuditTest/evidence/isolation/`（六次
  `result.json`、A−Parallel 日志与 `result.json`、基线缓存快照、
  LunaSettings 损坏备份、上游包对比）。
