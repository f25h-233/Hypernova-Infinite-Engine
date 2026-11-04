# M7 B 路线调试报告（Java 28 / FR 0.9.7rc2）

> 2026-11-04。独立调试根：
> `SS098_Hypernova_Compat_AuditTest/install/optimized-b-debug`。
> 未修改 `tools/m7_stack.py`、`tests/`、主实验根。全文只记录“到主菜单”的
> 自动证据；战役/战斗/读档/中文输入/字体视觉仍是用户 gate，**未宣称通过**。

## 1. 最终推荐配置

| 项 | 值 |
|---|---|
| 根 | `SS098_Hypernova_Compat_AuditTest/install/optimized-b-debug` |
| Java | 根内 `jdk-28+13`（Temurin 28-beta+13） |
| FR | 0.9.7rc2（`starsector-core/fr.jar`，classpath 首位） |
| VOpt | 1.0.45（加载日志 `VOpt Loaded`） |
| Hypernova | 0.1.0（agent + lazy/file-index/scripts-cache 全部注册） |
| ChineseInputFix | 启用；日志 v2.2，窗口子类化成功 |
| Prepatcher | 0.18.4；`12 classes / 17 patches / 4 skipped`（热跑） |
| 参数 | `route-b.vmparams` = **完整 Mikihime JDK28 47 项**（源 `Miko_Lite.txt`；内存两项统一为 `-Xms8G -Xmx10G`）+ FR/VOpt/Hypernova/CIF/Prepatcher；无精简回滚 |
| enabled | 258 = 255（`jc_sf` 禁用）+ Hypernova + Prepatcher + CIF |
| 目录 | `mods/GraphicsLib` 为**私有真实副本**（非 junction，避免法线缓存写回 260mods）；其余 mod 仍是 junction |
| 环境前提 | AoTD 核心 `starfarer.api.jar` 替换（`ad41a688…`）；260mods LunaSettings 75 份；`mods/DDSCache` 空目录 |

**到主菜单（完整 Mikihime 47 项，热缓存，连续 3 次）**：
`68.2 / 57.1 / 59.2 s`，中位 **59.2 s**。此前完整 47 项控制组为 `67.7 s`，
本次复测确认可复现且更低。目标 `105.8 s` 已满足。
**冷启动（首次或改 enabled 集合后）**：参考 `465.0 s`（同组件、精简参数冷跑；
冷成本由 30,043 张法线 PNG 与 2.1 GB startup 缓存主导，完整 Mikihime 未单独
重复冷跑）。

启动命令：

```bat
cd /d SS098_Hypernova_Compat_AuditTest\install\optimized-b-debug\starsector-core
..\jdk-28+13\bin\java.exe -DlaunchDirect=true -DstartRes=1707x1067 ^
  -DstartFS=false -DstartSound=true @..\route-b.vmparams
```

## 2. 对照组

| # | 参数 / 组件 | 缓存 | 菜单 | 关键日志 |
|---|---|---|---|---|
| B（历史） | 8G/10G，Mikihime off，无 CIF/Prepatcher | 热 | **105.8 s** | 0 张法线；脚本缓存 `preloaded=18`；`Cached 234175 files` |
| B+（历史） | 8G/10G + 47 项 Mikihime，CIF + Prepatcher | 冷 | **355.3 s** | 30,043 张法线；法线生成 80.1→337.7 s；全量 file index |
| B0 冷跑 | 8G/10G，Mikihime off，CIF + Prepatcher | 冷 | **465.0 s** | 30,043 张法线；`Cached 228439/12876ms`；file index 写 222,319；Prepatcher 16/21/4 @102.9 s；VOpt @439.9 s |
| B0 热跑 1 | 同上 | 热 | **77.7 s** | 0 张法线；脚本缓存 21 ms；`Cached 234428/10336ms` |
| B0 热跑 2 | 同上，GraphicsLib 已改私有副本 | 热 | **95.8 s** | 0 张法线；脚本缓存 23 ms；VOpt @70.3 s |
| B0 热跑 3 | 同上 | 热 | **83.2 s** | 0 张法线；脚本缓存命中 |
| B0 热跑 5 | 同上（最终确认） | 热 | **94.3 s** | 0 张法线；脚本缓存 9 ms；Prepatcher 12/17/4 @67.2 s；VOpt/CIF @71.6 s；anchor 92.6 s |
| **B 最终 热跑 1** | 完整 Mikihime 47 + 8G/10G + CIF/Prepatcher | 热 | **68.2 s** | 0 张法线；脚本缓存命中；Prepatcher @46.3 s；VOpt/CIF @50.3/50.4 s；anchor 67.4 s；errors=[] |
| **B 最终 热跑 2** | 同上 | 热 | **57.1 s** | 0 张法线；脚本缓存命中；Prepatcher @37.0 s；VOpt/CIF @40.3 s；anchor 56.7 s；errors=[] |
| **B 最终 热跑 3** | 同上 | 热 | **59.2 s** | 0 张法线；脚本缓存命中；Prepatcher @38.4 s；VOpt/CIF @41.8 s；anchor 58.6 s；errors=[] |
| B+ 47 项控制 | 完整 Mikihime，CIF + Prepatcher | 热 | **67.7 s** | 0 张法线；脚本缓存 24 ms；`UseCompactObjectHeaders` 等全部被 Java 28 接受 |
| 去 Prepatcher | 其余同 B0 | 冷 | 300 s 超时 | 法线重新生成中；脚本 key `d62f2bb8…` |
| 去 CIF | 其余同 B0 | 冷 | 300 s 超时 | 法线重新生成中；脚本 key `e765134b…` |

说明：去 Prepatcher/去 CIF 不是干净的“组件开销”对照——移除任一组件都会
改变 enabled 集合，从而改变 Hypernova 脚本/法线缓存 key，触发全量法线重建。

## 3. 慢因结论（有证据）

1. **B+ 的 355.3 s 是冷法线缓存，不是 Mikihime 参数。**
   B+ 日志有 30,043 条 `Auto-generated normal map`（`.log.1` 6,547 +
   `.log` 23,496），生成区间 80.1→337.7 s；B 的 105.8 s 日志为 **0 条**。
   B 的 105.8 s 来自此前同组件集合的多次 B 运行把法线缓存预热。
2. **同一 B0 配置、同一根：冷 465.0 s，热 77.7–94.3 s。** 两者的
   vmparams/组件完全相同，唯一变化是法线与 startup 缓存；差异不是参数。
3. **缓存 key 跟 enabled mod 集合走。** 观测到
   `ed4e838c…`（B0 258 全套）、`79296e0c…`（B+ 全套）、`d62f2bb8…`
   （去 Prepatcher）、`e765134b…`（去 CIF）；每个新 key 都触发一次全量
   法线重建。B+ 在补齐 CIF + Prepatcher 后第一次启动，正好落在这个冷路径上。
4. **Mikihime 47 项不是拖慢项，热跑反而更快。** 最终完整 47 项连续 3 次
   `68.2 / 57.1 / 59.2 s`（中位 59.2），预演控制 `67.7 s`；均低于 B0
   精简参数热跑区间。`AlwaysPreTouch`、`UseCompactObjectHeaders` 未单独
   做单变量对照；本文不把它们列为已证实的慢因。
5. **无错误证据**：`m6_log_audit total=0 ok=true complete=true`；
   CIF observations 91；lazy probe `misses=0 failed=0 degraded=0`；
   `errors=[]`。
6. B+ 355.3 与 B0 冷 465.0 的差值是两次冷跑的运行条件差异（机器负载/
   磁盘），**不是** Mikihime 快慢结论。

## 4. 现场恢复

- `optimized-b-debug` 保留：4.4 GB（2.1 GB startup 缓存 + 1.5 GB
  GraphicsLib 私有副本 + JRE/核心）。热跑可直接复用。
- **260mods 已恢复**：冷跑曾通过 `mods/GraphicsLib` junction 向
  `Starsector-098-260mods/mods/GraphicsLib/cache` 写入 30,043 个 PNG。
  已删除这批文件（清单：
  `evidence/b-debug/260mods-graphicslib-cache-restored.txt`），
  `find Starsector-098-260mods -newermt '2026-11-04 08:30'` 结果为 0。
  同时把调试根的 `mods/GraphicsLib` 从 junction 改为**私有真实副本**，
  后续运行不再写 260mods；完整 Mikihime 3 轮热跑后复查
  `GraphicsLib/cache` 新增仍为 0。10:28 又出现 5 个新 PNG
  （`blinker_*`/`lights_*`），来自 A 主实验根的并发运行；B 调试根使用
  私有 GraphicsLib，不会写 260mods，本任务未删除 A 的写入。
- 主实验根未由本任务写入；检查时其 `vmparams` 仍为 `8f88ab53…`、
  核心 jar 仍为 `769c8e94…`。调试期间曾观察到 A 路线 agent 运行并占用
  `evidence/.game-lock`；本任务未删除其锁，最终检查时已释放；其 enabled
  变化不属于本任务。
- 共享 `scripts/launch-route-b.bat` 已恢复为指向主实验根的原内容
  （完整 Mikihime 重应用后又恢复一次）。
- 回滚 label：`m7-route-b-20261104-095420-314944`（完整 Mikihime 重应用；
  更早一次为 `m7-route-b-20261104-082907-992413`），仅调试根。
- 未 push；未使用 `taskkill /IM java.exe`；所有 B 启动均按 PID 结束。

## 5. 需要回写 `m7_stack.py` 的具体改动

1. **`plan_migrate` / `apply_migrate`（L397/L469）**：不要对写自身缓存的 mod
   使用 junction。至少把 `GraphicsLib` 加入私有复制集合
   （`PRIVATE_COPY_MODS = frozenset({"graphicslib"})`，放在
   `PRESERVED_MOD_IDS` 附近），`apply_migrate` 对其实施 `copytree` 而非
   junction；否则冷跑会改写 260mods。
2. **`plan_route_b`（L1405）**：当 `--enable-cif` / `--prepatcher` 改变
   enabled 集合时，输出冷缓存警告，并在 plan JSON 增加
   `cold_cache_expected=true`（Mikihime 只改 JVM 参数，不改缓存 key）。
   文档应明确 **105.8 s 是热缓存数字**；补齐组件后的第一次启动预期
   300–500 s。
3. **`_route_launcher_path`（L643）**：对非标准根（debug/并行根）不要覆盖
   `audit/scripts/launch-route-b.bat`；增加 `--launcher-out`，或只在
   canonical root 时写共享路径。本次调试覆盖后又手工恢复。
4. **`_apply_mikihime_options`（L1308）+ `_route_b_tokens`（L1331）**：
   显式传 `--xms/--xmx` 时，`_route_b_tokens` 会删掉 Mikihime 的
   `-Xms/-Xmx`（本次最终 vmparams 只有一对 8G/10G）；但内存只来自
   Mikihime、未传 `--xms/--xmx` 时会出现重复（B+ 的 vmparams 有两对）。
   建议在 `_apply_mikihime_options` 里先剔除内存 token，统一由
   `_route_b_tokens` 添加。
5. **`plan_route_b` 预检**：若 `mods/GraphicsLib` 是 junction，给出
   “法线缓存会写入源 260mods” 的 blocking/warn，并建议私有副本。
