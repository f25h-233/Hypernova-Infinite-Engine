# M7 路线 A 独立调试报告（2026-11-04）

> 实验根：`SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15`
> 启动串行、按 PID 结束、精确锚点
> `Playing music with id [miscallenous_main_menu.ogg]`。
> **没有 push；没有改 `tools/m7_stack.py` / `tests/`；没有改 260mods 源文件。**
>
> **口径更正（协调方 2026-11-04）**：`Compiling script [X]` 是 FR
> `ScriptStore.loadScript` 在 `loadClass` 之前打的**队列日志**；类在 mod jar
> 中命中也会打印。它不是编译计数。本报告已删除旧版
> “13.9k 脚本全部源码编译”的归因，改用 Hypernova `find span` 的
> `misses`/`breakdown_sourced` 与 `scripts cache written entries`。

## 1. 结论

| 配置 | 结果 | 到菜单 |
|---|---|---|
| 全量 254 baseline（600 s 预算，早期；无 Hypernova/Parallel） | timeout-not-menu | —（停在 rules/scripts；队列行 13,944） |
| **全量 256 A（1400 s 预算）** | **timeout-not-menu** | **—**；1400 s 时已进入纹理加载（法线缓存） |
| 12-mod 子集 baseline | 到达主菜单 | **15.6 s** |
| 12-mod 子集 + Hypernova | 到达主菜单 | **17.9 s** |
| 12-mod 子集 + Hypernova + Parallel | 到达主菜单 | **15.6 s** |

- **全量 256 在 1400 s 仍未到菜单，但已经明显推进**：约 1303 s 完成
  rules/scripts/hull JSON，转入 GraphicsLib 法线缓存纹理加载；1400 s 截止时
  仍在 `Loading image [cache/..._normal.png]`。无 Fatal/OOM。
- 1400 s 是**预算边界**问题，不是脚本崩溃。之前的 1354 s 记录与本轮
  “1400 s 仍在纹理加载”一致；更长预算（1600–1800 s）值得单独测，本轮按
  指示停在 1400 s。
- **真实指标**（1400 s，Hypernova）：`finds=12,842`、`hits=68`、
  `misses=12,774`、`sourceless=3`、`sourced=12,771`；缓存唯一类
  `entries=1,871`。队列行 `Compiling script=14,919`，比真实
  `sourced` 多约 2,148（~14%），且队列行包含 jar 命中；**不能把队列行当编译数**。
- 12-mod 子集是当前**最小快速路径**；其 15.6–17.9 s 依赖已保留的
  `startup-optimization` 热缓存（2.1 GB）。冷缓存未重测。
- Parallel C1 `CombatAiHotspotMixin` 仍 `NOT-INJECTED`（FR 重写
  `CombatEngine`）；子集运行中 pool 已启动（`sparallel-worker-1..11`），
  其余 5 个 hotspot mixin 日志级 `APPLY`。

## 2. 全量 A 1400 s 实测

### 2.1 配置

- 256 个启用 mod：原始 256 去掉 3 个声明 jar 缺失的 mod
  （`missingshipsweapons`、`CRS_Mod_Core`、`StopGapMeasures3`），再加
  `MixinLib`、`hypernova_infinite_engine`、`starsectorparallel`。
- JRE 17.0.10；MixinFR 1.2.5（MixinLib bridge）+ VramOpt 1.0.45 +
  Hypernova 0.1.0 + StarsectorParallel 0.1.0；**无 Mikihime 风格参数**。
- 内存 `-Xms8G -Xmx10G -XX:MaxDirectMemorySize=10G`。
- 为隔离写入，`mods/GraphicsLib`、`mods/shaderLib` 已改为**私有副本**
  （`GraphicsLib` 121 MB → 运行后 378 MB；`shaderLib` 502 MB），
  260mods 源目录保持 131 MB / 502 MB，未再写入。

### 2.2 每 100 s 时间线

| t(s) | 阶段 | 队列 `Compiling script` | `Loading rule` | HN finds | HN hits | HN misses | sourced | cache entries |
|---|---|---|---|---|---|---|---|---|
| 103 | rules | 117 | 3,536 | 39 | 0 | 39 | 39 | 43 |
| 204 | scripts | 277 | 10,159 | 245 | 0 | 245 | 245 | 150 |
| 305 | scripts | 1,774 | 12,803 | 990 | 21 | 969 | 969 | 538 |
| 407 | scripts | 6,147 | 13,036 | 1,904 | 21 | 1,883 | 1,883 | 538 |
| 508 | scripts | 11,655 | 13,245 | 2,666 | 22 | 2,644 | 2,644 | 1,415 |
| 609 | rules | 14,569 | 15,772 | 3,932 | 57 | 3,875 | 3,875 | 1,871 |
| 710 | rules | 14,630 | 17,517 | 5,096 | 57 | 5,039 | 5,039 | 1,871 |
| 811 | rules | 14,694 | 19,573 | 6,234 | 57 | 6,177 | 6,177 | 1,871 |
| 911 | scripts | 14,712 | 19,641 | 7,779 | 57 | 7,722 | 7,722 | 1,871 |
| 1,012 | rules | 14,741 | 20,155 | 8,949 | 57 | 8,892 | 8,892 | 1,871 |
| 1,114 | rules | 14,814 | 21,745 | 10,537 | 57 | 10,480 | 10,480 | 1,871 |
| 1,215 | rules | 14,828 | 22,529 | 11,793 | 57 | 11,736 | 11,736 | 1,871 |
| 1,316 | textures | 0* | 0* | 12,834 | 60 | 12,774 | 12,771 | 1,871 |
| 1,401 | textures | 0* | 0* | 12,842 | 68 | 12,774 | 12,771 | 1,871 |

`*` 约 1,303,556 ms 时 `starsector.log` 轮转到 `.1`；1316 s 后的
`compiling_lines`/`rules` 是新日志的计数，不是归零。旧日志
`starsector.log.1` 最终计数：队列 **14,919**、`Loading rule` **25,992**、
`Loading JSON` **75,574**、`Loading image` **52,322**；新日志另有
JSON 15,200、图片 2,169。

### 2.3 最终阶段与真实指标

- 截止 1400 s：`stage_at_end=textures`；旧日志尾部为
  `Loading JSON from [data/hulls/...]`，新日志尾部为
  `Loading image [cache/..._normal.png]`。**已完成 rules/scripts，正在加载
  GraphicsLib 法线缓存纹理。**
- Hypernova 最终：`find span ... finds=12,842, hits=68, misses=12,774,
  span_ms=1,275,342`；`miss breakdown: total=12,774, sourceless=3,
  sourced=12,771`；`scripts cache written: ... entries=1,871`；cache key
  `923aa15c2f15439c4e812f0197e4c215`；冷 preload=0。
- 队列行 14,919 与 `sourced` 12,771 的差额主要是 jar 命中/重复队列；
  `sourced` 是“有源码且未命中缓存的 findClass 调用数”，`cache entries=1,871`
  是缓存中唯一类数。**精确的唯一源码编译数没有直接暴露**（进程按 PID 结束，
  shutdown hook 未执行），但队列行不是编译数这一结论是确定的。
- 无 Fatal/OOM（两份日志均 0）；本轮未运行五类纹理错误审计。

### 2.4 Parallel C1

- `WARN target is rewritten by Fast Rendering: com.fs.starfarer.combat.CombatEngine
  (mixins [CombatAiHotspotMixin])`
- `APPLY mixin=starsectorparallel.mixin.json:CombatAiHotspotMixin`
- `PROBE target=com.fs.starfarer.combat.CombatEngine loaded=true
  declaredMethods=307 mixinHandlers=0 ... verdict=NOT-INJECTED`
- 本轮全量没有到菜单/战役，其他 5 个 hotspot 的目标类未加载，日志中只有
  1 条 Parallel `APPLY`。C1 结论不变：**NOT-INJECTED**。

## 3. 12-mod 子集（快速路径）

- 子集：`MixinLib, VramOptimizer, lw_lazylib, shaderLib, MagicLib, lunalib,
  lw_console, particleengine, ashlib, BoxUtil, pantera_ANewLevel40,
  Adjusted Sector`。
- baseline：精确锚点 **15.6 s**；队列行 781。
- +Hypernova：**17.9 s**；队列行 783；Hypernova 缓存写入
  **117 个唯一类**（真实指标；队列行/真实类约 6.7×）；
  `lazy: unsupported FR version 0.9.5`、`file index: unsupported FR version
  0.9.5`；`textures normal-cache transformer registered`。
- +Hypernova+Parallel：**15.6 s**；队列行 784；
  `sparallel-worker-1..11`、`[StarsectorParallel] self-test parallel sum = 10`；
  6 个 hotspot mixin 全部 `APPLY`，C1 仍 `NOT-INJECTED`，其余 5 个
  （Market/CampaignFrameFlush/BaseLocation/Commodity/FleetAssignment）
  日志级 `APPLY`。
- 子集运行在菜单后自动读取了 260mods 既有 `save_123_...`，因此 campaign
  类被加载；这是日志级副作用，不是用户实机 gate。

## 4. 归因更正与修复尝试

### 4.1 `Compiling script` 是队列日志

- 旧版报告把 600 s 的 13,944 行当成“13.9k 脚本全部源码编译”，这是错误的。
  本轮 1400 s 的对照数据：507.8 s 时队列行 11,655，而 `sourced=2,644`
  （约 4.4×）；1400 s 时队列行 14,919，`sourced=12,771`（约 1.17×）。
- 队列行随规则加载被触发，包含大量 jar 命中；`find span` 的
  `sourced`/`misses` 和 `scripts cache written entries` 才是可用的真实指标。
- 这并不否定“MixinFR/FR 0.9.5 脚本加载路径很慢”：1400 s 仍停在纹理加载，
  旧日志有 25,992 条规则和 12,771 次 sourced miss。但“13.9k 全部源码编译”
  这个具体归因被撤回。

### 4.2 诊断 agent（未采用）

- 写了 `scripts/a_debug_agent/`，做过两种尝试：
  1. 强制 `com.fs.starfarer.loading.scripts.B` 的父加载器为 MixinLib
     `TargetClassLoader`；
  2. 同时把 MixinLib `StarsectorTransformer.transform` 改为恒等函数，
     恢复被清空的 ScriptStore URL 列表。
- 结果：agent 日志显示 patch 生效，但 600 s 预算下仍 timeout（队列行
  14,468 / 14,584），未改变阶段；未纳入最终配置。

### 4.3 缩小 mod 集（成功）

- 12-mod 子集 15.6 s 到主菜单；是当前最小快速路径。
- 但这是**缩小 mod 集**的结论，不是“全量 256 可玩”的证明。

### 4.4 GraphicsLib 隔离

- 1400 s 运行前把 `mods/GraphicsLib`（原 junction）和 `mods/shaderLib`
  复制为私有目录；运行后私有 `GraphicsLib` 从 121 MB 增至 378 MB，
  说明写入落在实验根，260mods 源保持 131 MB / 3998 个文件。
- 复制过程中曾产生 `260mods/mods/GraphicsLib/GraphicsLib` 嵌套副本，已立即
  删除并核对源目录大小恢复到 131 MB；之后未再写 260mods。

### 4.5 DDSCache / 法线缓存

- 实验根没有 `mods/DDSCache`；FR 0.9.5 的 `fr.jar` 引用它，但本轮日志没有
  DDSCache 缺失 Fatal，也没有五类纹理错误。
- 1400 s 已经进入 `cache/*_normal.png` 纹理加载，说明法线缓存（私有
  GraphicsLib）存在且被使用；没有把 3.9 GB DDSCache junction/复制进来
  （junction 会写 260mods；复制也不会解决 rules/scripts 的耗时）。

## 5. 现场恢复

- rollback：`m7-route-a-20261104-110831-312607`，`ok=true restored=1 deleted=12`。
- `vmparams` sha256 = `8f88ab53…`；`settings.json` sha256 = `96f3f6aa…`；
  `mods/enabled_mods.json` = 原始 **256** 项，sha256 = `ed362f35…`。
- 无 `mods/MixinFR`、`mods/StarsectorParallel`、
  `mods/hypernova_infinite_engine`；无 `route-a.vmparams` /
  `launch-route-a.bat`；`saves/`、`starsector.log`、`mixinlib*.log` 已清理。
- `mods/GraphicsLib`、`mods/shaderLib` 保留为**私有副本**
  （378 MB / 502 MB；`mods/` 259 项）；260mods 源 131 MB / 502 MB 未改。
- `starsector-core/cache/startup-optimization` 保留（2.1 GB）；删除它会使
  子集也回到冷缓存，启动时间需重测。

## 6. 需要回写 `tools/m7_stack.py` 的改动

1. **Route A 内存参数**：生成的 `route-a.vmparams` 仍是 2 GB；256 mod 需要
   `--xms/--xmx`（本次手工 8G/10G + `MaxDirectMemorySize=10G`）。
2. **3 个缺失声明 jar 的 mod 预检**：`missingshipsweapons`、`CRS_Mod_Core`、
   `StopGapMeasures3` 会让 MixinFR `LaunchSnapshot` fail-closed；apply 应
   自动排除或明确报错。
3. **主菜单锚点**：必须匹配完整
   `Playing music with id [miscallenous_main_menu.ogg]`；
   `Creating streaming player for music with id [...]` 是资源预加载假阳性。
4. **指标口径**：任何报告/工具不要把 `Compiling script` 当编译计数；
   使用 Hypernova `find span` 的 `sourced`/`misses` 和
   `scripts cache written entries`，并注明 `sourced` 是调用数、cache 是唯一类数。
5. **预算**：600 s 上限会误判 A；本轮 1400 s 已进入纹理加载但未到菜单。
   增加 `--timeout 1400/1800` 的验收选项，或明确要求“缩小 mod 集/预热缓存”。
6. **GraphicsLib 隔离**：migrate 对会写缓存的 mod（GraphicsLib/shaderLib）
   默认复制而不是 junction，避免写 260mods；文档标注 junction 写风险。
7. **分组件 apply**：`route-a --apply` 一次装 MixinFR/Parallel/Hypernova；
   建议增加 `--components` 以便按步骤验证。
8. **回滚/缓存**：rollback 不管 `starsector-core/cache`、`fr-resource-cache`
   和私有 GraphicsLib 缓存；建议列为可选清理项或在文档说明。

## 7. 证据

- 1400 s：`evidence/a-debug/a-full-1400/`（`starsector.log`、`.1`、
  `mixinlib.log`、`scripts-agent.log`）、`a-full-1400.timeline.jsonl`、
  `a-full-1400.json`。
- 子集：`a1f-subset12-baseline/`、`a2f-subset12-hypernova/`、
  `a3f-subset12-parallel/`（含 `a3f-...threads.txt`）。
- 配置：`route-a-apply3.json`、`enabled_mods.original.json`、
  `enabled_mods.subset12.json`。
- 诊断 agent：`SS098_Hypernova_Compat_AuditTest/scripts/a_debug_agent/`（未采用）。
