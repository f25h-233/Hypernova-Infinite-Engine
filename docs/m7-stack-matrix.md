# M7 两路线兼容矩阵

> 适用：Starsector 0.98a-RC8（Windows），汉化优化测试版 v2026.10.15。
> 日期：2026-11-04。
>
> **Task 7 实机验证尚未执行。** 本文件里的“实测”只指已有的真实运行 / 日志 /
> 自动化证据；路线 A、B 的运行时结论一律是 `dry-run 结构` 或 `推断`，不能读成
> “已通过”。用户实机 gate 见 Task 7 生成的 `docs/m7-results.md`。

## 0. 状态口径

| 状态 | 含义 |
|---|---|
| `实测（证据）` | 本机真实启动、日志或自动化结果；括号里写证据文件或日志。 |
| `dry-run 结构` | `tools/m7_stack.py` 的 plan/apply 代码、测试与真实根 dry-run 已验证；没有启动游戏。 |
| `推断` | 来自上游 release notes / README / 论坛帖 / 源码门禁；本机未复现。 |
| `不支持` | 上游明确不支持，或本机 / 源码硬门禁拒绝。 |

`待验证` 不是一种状态，而是 Task 7 的执行项；在它跑完之前，任何运行时收益
和兼容结论都不写成“已实测”。

## 1. 路线总表

| 路线 | Java | FR | MixinFR | Parallel | VramOpt | Hypernova | 汉化优化版 | 高清字体 | IME | Prepatcher | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A**：MixinFR + JRE 17 + Parallel | JRE **17.0.10**（`jre/release`；启动器显式 `..\jre\bin\java.exe`；运行时待验证） | **0.9.5**（MixinFR 内置） | **1.2.5**（mod id `MixinLib`；含 `MixinFRImeFix.jar`） | **0.1.0**（依赖 MixinLib） | **1.0.45**（由 256-mod 迁移带入） | **0.1.0** agent + mod；`lazy` / DDS / file-index 受 FR 0.9.5 门禁关闭；scripts / normal-cache 待实机 | **推断**（上游声明：MixinFR README 明确 2026.10.15） | **推断**（上游声明：1.2.4 重定向、1.2.5 修竖条；待实机看 `REMAP-OK`） | **推断**（上游声明：`MixinFRImeFix`）；备选 `disable-ime` + ChineseInputFix | **不支持**（0.18.4 在 MixinLib 下 20/34 `SKIPPED_LOADER`；Java 27+ fatal） | `dry-run 结构`（Task 4，commit `581eb51`；实机待 Task 7） |
| **B**：FR 0.9.7rc2 + Java 28 | Temurin **28-beta+13-ea**（`jdk-28+13`；启动器显式；运行时待验证） | **0.9.7rc2** | 无 | 无（缺 MixinLib 依赖） | **1.0.45** | **0.1.0** agent + mod；`lazy` / DDS / file-index 可用（M6 **260mods 单环境 agent-only**，非 M7 根；M7 待 Task 7） | **推断**（21835 明确说优化版自带启动加速，与 plain FR 会打架；M7 目标根是优化版） | **不支持**（plain FR 不重定向矢量字体；上游 21705 说明） | 无 `MixinFRImeFix`；用 `disable-ime` + ChineseInputFix | **推断**（可选 0.18.4；实验；Java 28 未声明） | `dry-run 结构`（Task 3，commit `80666a9`；实机待 Task 7） |
| **B + Prepatcher**（可选） | 28（Prepatcher **未声明** Java 28） | 0.9.7rc2 | 无 | 无 | 1.0.45 | 0.1.0 | 同上（实验） | 不支持 | ChineseInputFix | **0.18.4**；agent 顺序 Hypernova → FR → Prepatcher；`SKIPPED_LOADER` 需实机看 | `dry-run 结构`（Task 3 Prepatcher 计划；实机待 Task 7） |

### 表注

1. **A 的 Hypernova 是“部分生效”**。MixinFR 1.2.5 内置 FR **0.9.5**；Hypernova 的
   `FileIndexHook.supportedFrVersion()` 只接受 `0.9.7rc2` / `0.9.7`
   （`src/agent/java/hypernova/agent/FileIndexHook.java`）。因此路线 A 的
   `-Dhypernova.textures.lazy=true` 等 token 会被 agent 判为“unsupported FR
   version”，`lazy` / file-index 关闭。`scripts` 缓存只要求 FR 存在，理论上仍可
   注册；`textures normal-cache` 是否生效以 `scripts-agent.log` 为准。**不要**
   把路线 A 当成 Hypernova 全功能栈。
2. **B 的 Hypernova 组合有 M6 实机证据**。M6 在 `Starsector-098-260mods`
   （agent-only，Java 28 + FR 0.9.7rc2 + VOpt 1.0.45）跑过菜单 smoke：
   `lazy.present=true`、`ddsHit=19`、`texture_errors_total=0`
   （`docs/m6-results.md` §3.2）。这证明组件组合可行，**不等于** M7 的新安装
   根、mod-enabled 形态已通过 Task 7。
3. **B 与“汉化优化版”的关系是本矩阵最大的风险点**。论坛 21835（用户本人教程）
   明确建议不要直接把优化测试版汉化与 plain FR 同用；两者都带启动加速。
   M7 的 B 是在优化测试根上的实验，Task 7 之前只能写 `dry-run 结构` /
   `推断`。若只要 21835 的稳定栈，应使用非优化 / 传统汉化安装。
4. **A 不支持 Java 28**。MixinFR 与 StarsectorParallel 官方都只支持游戏自带
   JRE 17；强制 28 的结果是静默跳过或硬失败，不是“可能也行”。
5. **Prepatcher 是路线 B 的可选项，不是路线 A 的补丁**。路线 A 的
   `plan_route_a` 会在检测到 `mods/StarsectorPrepatcher` 或其 agent 时直接拒绝。

## 2. 逐项证据

| 事实 | 路线 | 状态 | 证据 |
|---|---|---|---|
| 实验根是优化测试版 2026.10.15；JRE 17.0.10；`dyn_font=true`；`ssime.dll` 存在 | A/B | `实测`（Task 1 / `m7-env.json`） | `docs/m7-environment.md`；`SS098_Hypernova_Compat_AuditTest/evidence/m7-env.json` |
| 上游称 MixinFR **1.2.5** 支持游戏自带 JRE 17、支持启动优化版 2026.09.04 / 2026.10.15、内置 IME 修复；1.2.4 修高清字体重定向，1.2.5 修文字压成竖条 | A | `推断`（上游声明；本机未复测） | `https://www.fossic.org/thread-21705-1-1.html`；`MixinFR/README.md`；`MixinFR/CHANGELOG.md` 1.2.4 / 1.2.5 |
| 上游称 StarsectorParallel **0.1.0** 依赖 MixinLib、使用游戏自带 JRE 17；传统汉化（ZYT）与启动优化版（YHCS）均已实测 | A | `推断`（上游声明；本机只做 dry-run） | `https://www.fossic.org/thread-21836-1-1.html`；`StarsectorParallel/README.md`；`mod_info.json` |
| Prepatcher 0.18.4 × MixinFR：`TargetClassLoader` 下 **20/34** 精确目标 `SKIPPED_LOADER`；Java 27+ 还会 `FatalCompatibilityException` | A（排除） | `实测`（2026-10-29） | `docs/audit-2026-10-31-coremod-ecosystem.md` §7.1（E2，20/34 静默跳过）；目标摘要：`coreui/A/*`、`CampaignState`、`Market` 等全跳过（Task 4 plan/brief、2026-10-29 实测记录）；Task 4 `plan_route_a` 的 `prepatcher.excluded` |
| Prepatcher 0.18.4 官方声明 Java 17 与 Miko Java 27+22；**Java 28 未声明**，只做能力检查 | B（可选） | `推断`（上游声明；本机未复测） | Prepatcher 0.18.4 release notes / 包内 `docs/COMPATIBILITY.md`；`https://github.com/kirpoly/StarsectorPrepatcher` |
| Hypernova + FR 0.9.7rc2 + Java 28 + VOpt 1.0.45 在 260mods 菜单 smoke 跑通 | B | `实测`（M6 单环境；不是 M7 安装根） | `docs/m6-results.md` §3.2；`SS098_Hypernova_Compat_AuditTest/evidence/menu-smoke.json`；`starsector.log` `Java version: 28-beta (64-bit)` |
| Hypernova 的 FR 绑定功能只接受 FR 0.9.7rc2 / 0.9.7；0.9.5 会关闭 lazy / file-index | A | `推断`（源码门禁；待实机日志确认） | `src/agent/java/hypernova/agent/FileIndexHook.java` 第 66–75 行；`plan_route_a` 的 `bundled_fr_version=0.9.5` |
| VOpt 1.0.45 + FR 0.9.7rc2 实机集成：`VOpt Loaded`、`Suitable FR Version found`、`Failed to initialize VRAM Optimizer=0` | B | `实测`（M1f） | `docs/m1f-results.md` §5.3 |
| 路线 A 安装结构：JRE 17 启动器、两个 agent（MixinLib → Hypernova）、8 项复制、enabled 顺序 Hypernova → MixinLib → starsectorparallel、根 `vmparams` 不改 | A | `dry-run 结构` | Task 4 报告；commit `581eb51`；`python -I tools/m7_stack.py route-a … --text` |
| 路线 B 安装结构：token-less argfile、显式 `jdk-28+13` 启动器、15 项复制、agent 顺序 Hypernova → FR → [Prepatcher]、根 `vmparams` 不改 | B | `dry-run 结构` | Task 3 报告；commit `80666a9`；`SS098.../evidence/m7-route-b-plan.json` |
| 路线 A/B 真实启动、菜单、战役、战斗、读档、分辨率、中文输入、字体视觉 | A/B | `推断`（未验证；Task 7 待跑） | Task 7 `docs/m7-results.md`（尚未生成） |

## 3. 能力取舍

| 能力 | 路线 A | 路线 B | 说明 |
|---|---|---|---|
| 逻辑侧多线程（StarsectorParallel） | 有 | 无 | Parallel 依赖 MixinLib；B 不装 MixinFR |
| Java 28 | 不支持 | 有 | A 固定 JRE 17；B 用 Temurin 28+13 |
| FR 渲染 / 加载加速 | 有（内置 FR 0.9.5） | 有（FR 0.9.7rc2） | 两者不要混装 |
| Hypernova `lazy` / DDS / file-index | 无（FR 0.9.5 门禁） | 有 | 想要完整 Hypernova 纹理链，选 B |
| Hypernova scripts / normal-cache | 待实机 | 有（M6 证据） | A 的 agent 仍会加载，但 FR 相关功能受限 |
| 优化测试版高清字体 | 有（MixinFR 重定向） | 无（plain FR 不重定向） | 1.2.5 修复竖条；仍待实机看 `REMAP-OK` |
| 优化测试版 IME | MixinFRImeFix | `disable-ime` + CIF | 一次只留一条输入路径 |
| Prepatcher | 不支持 | 可选（实验） | Java 28 未声明 |
| 游戏自带 JRE 17，无需另装 JDK | 是 | 否 | B 需要 `jdk-28+13` |

**结论：M7 目前没有一条路线同时给全 Parallel + 完整 Hypernova 纹理链 +
高清字体 + IME 修复。** A 偏“汉化优化版体验 + 多线程”，B 偏“Java 28 +
完整 Hypernova / 21835 稳定栈”。按你最在意的能力二选一，不要在同一安装根上
叠加。

## 4. 版本与依赖

| 组件 | 版本 | mod id / 形态 | 依赖 / 备注 | 官方来源 |
|---|---|---|---|---|
| 汉化优化测试版 | 2026.10.15 | 安装器 | 0.98a-RC8；`branch=startup-optimization`；JRE 17.0.10 | 汉化包仓库 `https://github.com/TruthOriginem/Starsector-Localization-CN`；发布/安装器以远星论坛（fossic）汉化发布帖为准 |
| MixinFR | 1.2.5 | `MixinLib`（mod） | 内置 MixinLib 1.1.0 + FR 0.9.5；JRE 17；含 `MixinFRImeFix.jar` | `https://www.fossic.org/thread-21705-1-1.html`（附件需登录） |
| StarsectorParallel | 0.1.0 | `starsectorparallel`（mod） | 依赖 `MixinLib`；JRE 17；YHCS 已测 | `https://www.fossic.org/thread-21836-1-1.html`（附件需登录） |
| Fast Rendering | 0.9.7rc2 | `fr.jar` + `fr.agent.jar` | 仅路线 B；与 VOpt 1.0.45 集成 | Fast Rendering（genir）发布页 `https://github.com/Halke1986/starsector-render`（21835 与 Prepatcher README 均引用） |
| VramOptimizer | 1.0.45 | `VramOptimizer`（mod） | 锁 1.0.45；不要升到 1.0.46+ | `https://github.com/DeCEll-1/VramOptimizer/releases/tag/v1.0.45` |
| Hypernova Infinite Engine | 0.1.0 | `hypernova_infinite_engine`（mod + agent） | 发行默认 lazy/eviction/scene_unload/frame probe 全关；FR 0.9.7rc2/0.9.7 才支持 file-index/lazy | `https://github.com/f25h-233/Hypernova-Infinite-Engine` |
| ChineseInputFix | 2.0.0 | `ChineseInputFix`（mod） | IME 备选；路线 B 建议启用 | `https://www.fossic.org/thread-20561-1-1.html`（作者 Chesand）；本仓库不打包 |
| StarsectorPrepatcher | 0.18.4 | `starsector_prepatcher`（mod + agent） | 仅路线 B 可选；Java 17 / Miko 27+22；Java 28 未声明 | `https://github.com/kirpoly/StarsectorPrepatcher`（包内 README 指向该仓库） |
| Temurin JDK | 28+13-ea-beta | `jdk-28+13` | 仅路线 B；启动器显式调用 | `https://github.com/adoptium/temurin28-binaries/releases/tag/jdk-28+13-ea-beta` |

> 版本核对：MixinFR 看 `mods/MixinFR/mod_info.json` 的 `version=1.2.5`；
> Parallel 看 `mods/StarsectorParallel/mod_info.json` 的 `0.1.0`；FR 看
> `starsector-core/fr.version.txt` 的 `v0.9.7rc2`；VOpt 看
> `mods/VramOptimizer/VOpt_VERSION.txt` 的 `VOpt v1.0.45`；Prepatcher 看
> `mods/StarsectorPrepatcher/mod_info.json` 的 `0.18.4`。

## 5. 禁止组合

| 组合 | 结果 | 原因 |
|---|---|---|
| A + FR 0.9.7rc2 | 工具拒绝 | MixinFR 已内置 FR 0.9.5；再叠加会双重注入 / 类补丁冲突 |
| A + StarsectorPrepatcher | 工具拒绝 | 0.18.4 在 MixinLib 下 20/34 `SKIPPED_LOADER`；Java 27+ fatal |
| B + MixinFR / MixinLib / StarsectorParallel | 工具拒绝 | 路线 B 不使用 MixinLib；两份 FR/Mixin 补丁会冲突 |
| Java 28 + MixinFR / Parallel | 不支持 | 官方只支持游戏自带 JRE 17 |
| A、B 共用同一安装根且不回滚 | 禁止 | 两套路线严格隔离；先 `rollback` 再装另一套 |
| 路线 A 后再运行 MixinFR 的 `install.bat` | 禁止 | 会再往根 `vmparams` 写一份 agent，制造两套启动配置；路线 A 的 agent 已在 `route-a.vmparams` 里 |
| 路线 B 用 `starsector.exe` / `fr.bat` 启动 | 不是路线 B | 两者都硬编码 JRE 17；必须用 `launch-route-b.bat` |
| 路线 A 用 `starsector.exe` 启动 | 不是路线 A | `starsector.exe` 读根 `vmparams`（未注入路线 A agent）；必须用 `launch-route-a.bat` |

## 6. 证据文件索引

- 环境基线：`docs/m7-environment.md`、`SS098_Hypernova_Compat_AuditTest/evidence/m7-env.json`
- 256-mod 迁移计划：`SS098_Hypernova_Compat_AuditTest/evidence/m7-migrate-plan.json`
- 路线 B dry-run：`SS098_Hypernova_Compat_AuditTest/evidence/m7-route-b-plan.json`
- 路线 A dry-run：Task 4 报告 + commit `581eb51`（当前没有单独的 evidence JSON）
- Hypernova 真实运行（260mods）：`docs/m6-results.md` §3.2、`.../evidence/menu-smoke.json`
- FR + VOpt 真实运行（M1f）：`docs/m1f-results.md` §5.3
- Prepatcher × MixinFR 20/34：`docs/audit-2026-10-31-coremod-ecosystem.md` §7.1；
  目标摘要 `coreui/A/*`、`CampaignState`、`Market` 等全跳过（Task 4 brief /
  2026-10-29 实测记录）
- 上游声明：`https://www.fossic.org/thread-21705-1-1.html`（MixinFR）、
  `https://www.fossic.org/thread-21836-1-1.html`（Parallel）、
  `https://www.fossic.org/thread-21835-1-1.html`（Java 28 教程 / 路线 B 来源）
