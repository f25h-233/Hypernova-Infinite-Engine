# M7 统一部署包：两路线实机验证结果（Task 7 + fix loop 1）

> 日期：2026-11-04。实验根：
> `SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15`。
> 本文记录**真实启动到主菜单为止**的自动化证据。路线 B 已到达主菜单；
> 路线 A 在延长观察窗口内仍未到达。战役 / 战斗 / 读档 / 中文输入 / 字体视觉
> 仍是用户 gate，全部 **pending**。**不宣称任何性能或显存收益。**

## 1. 结论

| 路线 | 安装结果 | 主菜单 | 结论 |
|---|---|---|---|
| A（MixinFR 1.2.5 + JRE 17 + StarsectorParallel） | fix loop `route-a --apply` 为 `applied=true ok=true`，manifest 就地生成成功 | **未到达** | 临时禁用 3 个声明 jar 缺失的 mod 后，MixinFR/Parallel/Hypernova 全部加载，无 Fatal/OOM；但在 600 s 上限 + 两次延长（总计约 1200 s）内仍停留在规则/脚本加载阶段，按协议记为 **timeout-not-menu**。 |
| B（FR 0.9.7rc2 + Java 28 + Hypernova） | fix loop `route-b --apply` 为 `applied=true ok=true`，manifest 就地生成成功 | **已到达（105.8 s）** | `--xms 8G --xmx 10G`；Java 28、FR 0.9.7rc2、Hypernova agent/lazy/file index/scripts cache 全部加载；VOpt Loaded；五类纹理错误 0；最终 lazy probe `misses=0 failed=0`。需要禁用 `jc_sf`（幽灵部队自检失败）并应用 AoTD 要求的 `starfarer.api.jar` 替换；两者均记录为环境/模组前提。**最终参数裁决见 §10：完整 Mikihime 47 项 + 8G/10G。** |
| **A+（组件补齐）** | `route-a --apply` `ok=true`；MixinFR 1.2.5 + Parallel 0.1.0 + VOpt 1.0.45 + Hypernova + MixinFRImeFix + Mikihime JRE17 子集 | **未到达** | 600 s 内未到菜单；617 s 仍在 rules/scripts，无 Fatal/OOM，纹理错误 0。Parallel/`CombatAiHotspotMixin` 为 `NOT-INJECTED`（FR 重写 `CombatEngine`）。 |
| **B+（组件补齐）** | `route-b --apply` `ok=true`；FR 0.9.7rc2 + VOpt + Hypernova + 完整 Mikihime JDK28 参数 + CIF + Prepatcher 0.18.4 | **已到达（355.3 s）** | Java 28；Prepatcher `16 classes / 21 patches / 4 skipped`；CIF v2.2 加载并子类化窗口；Hypernova lazy `misses=0 failed=0`；纹理错误 0。**355.3 s 是冷法线缓存首次启动，不是参数慢；见 §10。** |

> **2026-11-04 补充裁决**：B 的最终推荐参数改为**完整 Mikihime JDK28 47 项 +
> 8G/10G**，仍保留 FR/VOpt/Hypernova/CIF/Prepatcher。历史 105.8 s 是
> **精简参数 + 热缓存**；B+ 355.3 s 是**完整参数 + 冷法线缓存**。热缓存
> 复测时间与依据见 §10；详细对照见 `docs/m7-b-debug.md`。

关键事实：

- 路线 A 的**最初** apply 不是“在 manifest 步骤前被外部中断”：证据是
  `applied=true ok=false`、`FATAL: route-a apply failed`、manifest
  `critical=77356`（全部 `asset_outside_root`，junction 校验问题）。外部中断
  只影响过“补跑 manifest”那一步。fix loop 修好 junction 校验后，A 的 apply
  达到 `ok=true`。
- 路线 B 的 2 GB 旧运行在 300 s 内未到菜单；fix loop 提高到 8G/10G 后到达
  菜单。这是**同环境不同参数**的结果，不是单变量性能对照。
- 路线 B 仍需要两个与 Hypernova 无关的模组前提：
  1. `jc_sf`（SF-幽灵部队）自检 `幽灵部队模组文件损坏`，已临时禁用；
  2. AoTD Theory of Toolbox 要求把其 `0.98a/starfarer.api.jar` 复制到
     `starsector-core/starfarer.api.jar`；已按 260mods 的已知可用配置替换，
     并在回滚时恢复原 jar。
- 用户 gate 全部 pending；菜单到达不等于战役/战斗/读档/输入/字体通过。
- 路线 B 的日志还显示**日志级自动读档 + 战斗**：141 s 读取 260mods 的
  `save_123_...`，141–222 s `HYPERNOVA_TICK 1→3001`、战斗渲染插件注册、
  武器/导弹贴图加载。这是日志级证据，**不是用户实机 gate 通过**；存档来源
  是 260mods 既有存档，不是实验根新建存档（见 4.4）。

## 2. 环境

| 项 | 值 |
|---|---|
| 游戏 | Starsector 0.98a-RC8，远星汉化优化测试版 2026.10.15（`branch=startup-optimization`） |
| 实验根 | `SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15` |
| 迁移 | 256 个启用 mod + `ChineseInputFix`，`--link` 257 个目录联接；`enabled_mods.json=256` |
| 随包 JRE | Zulu 17.0.10（路线 A） |
| 路线 B JDK | Temurin `28-beta+13-ea`（`jdk-28+13`） |
| MixinFR | 1.2.5（内置 FR 0.9.5） |
| StarsectorParallel | 0.1.0 |
| Fast Rendering | v0.9.7rc2 |
| VramOptimizer | 1.0.45（在 256 mod 迁移列表中） |
| Hypernova | 0.1.0，`build/agent/hypernova.agent.jar` + `build/java/hypernova.jar` |
| 根 `vmparams` | `sha256=8f88ab530c3e989ca027f4aff320a49d8115cab281cd2e592bf9b57c83a29fee`，**全程未改** |
| 路线 A 内存 | fix loop 手工补丁：`-Xms8G -Xmx10G -XX:MaxDirectMemorySize=10G` |
| 路线 B 内存 | `--xms 8G --xmx 10G`（Miko_Lite 参考：`-Xms8192m -Xmx10240m`） |
| 验证日 | 2026-11-04，Windows 11 中国区，物理内存 31.2 GB |

方法说明：

- 所有路线启动都用显式 `java.exe @argfile`；裸 argfile 只会打开启动器 UI，
  实机启动额外注入 M6 已验证的
  `-DlaunchDirect=true -DstartRes=1707x1067 -DstartFS=false -DstartSound=true`。
- 所有游戏进程都按 **PID** 结束，未使用 `taskkill /IM java.exe`。
- 路线 A 的 600 s 上限被两次延长以区分 timeout 与失败；文中明确标注。
- fix loop 未修改 `Starsector-098-260mods`；只读取了它的 LunaSettings 和
  AoTD 已知可用 jar。

## 3. 路线 A 自动化证据

### 3.1 安装（fix loop）

- 迁移：`copy=256 enabled=256 extras=ChineseInputFix`，257 junction；目标
  `mods/` 258 项。
- 为绕过 MixinFR `LaunchSnapshot` 对“声明了但不存在”的 jar 的 fail-closed，
  在**实验根** `enabled_mods.json` 临时移除 3 个 mod（不改 260mods）：
  - `missingshipsweapons`（迷失武器包）：声明 `jars/missp_varunastra.jar`，包内无 `jars/`；
  - `CRS_Mod_Core`：声明 `jars/CRS_Boarding.jar`，包内无 `jars/`；
  - `StopGapMeasures3`：声明 `jars/Stop Gap Measure.jar`，包内无 `jars/`。
  证据：`evidence/fixloop1/missing_declared_jars.json`、
  `enabled_mods.before-route-a-fixloop1.json`、
  `enabled_mods.route-a-fixloop1-run2.json`。
- fix loop apply（绝对 `--root`）：
  `applied=true ok=true`，`generated=2 copied=8`，manifest
  `L1=6624 L2=18513 L3=55385 skip=73320`，Critical=0；
  rollback label `m7-route-a-20261104-021154-749861`。
- **F2 更正**：最初那次 apply 的实际证据是
  `evidence/m7-route-a-apply.json`：`applied=true ok=false`、
  `FATAL: route-a apply failed`、manifest `critical=77356`。外部中断只影响
  “补跑 manifest”步骤，不是 apply 在 manifest 之前被中断。

### 3.2 manifest（junction 修复后的就地生成）

- 修复前：`install_manifest.py` 对 junction 资产报 77356 条
  `asset_outside_root`；根因是 `manifest_builder` 写 `absolutePath` 时用
  `Path.resolve()` 跟随 junction 到 260mods 源路径，`validate_manifest` 也用
  `resolve()` 判断越界。
- 修复后：`manifest_builder` 用 lex 绝对路径写 `absolutePath`；
  `validate_manifest._inside_root` 用 `os.path.abspath` + `commonpath` 做
  lex 包含判断。目标根就地生成：
  `rc=0`，`L1=6624 L2=18525 L3=55400`（B apply 时）/
  `L1=6624 L2=18513 L3=55385`（A apply 时），Critical=0。
- 证据：`evidence/fixloop1/manifest-test2/generate.log`。

### 3.3 启动尝试时间线

| # | 参数 | 结果 |
|---|---|---|
| 1 | 裸 `@route-a.vmparams` | 只到启动器设置 UI，未进游戏；325 s 结束 |
| 2 | `launchDirect` + `missingshipsweapons` 禁用 | 2 s 后 MixinLib 报 `Stop Gap Measure.jar` 缺失（第二个坏 mod） |
| 3 | 再禁用 `CRS_Mod_Core`/`StopGapMeasures3`，2 GB | 79 s 直接缓冲 OOM：`allocated=2146627305 limit=2147483648` |
| 4 | 8G/10G + 10G direct | 无 OOM/Fatal；600 s 时仍在加载 rules/scripts；延长到约 1200 s 仍未到菜单 |

- 尝试 4 的关键日志：
  - `mixinlib.log`：`integration=MixinFR+FastRendering phase=fr`；
    `Handoff - game JVM started pid=24448 enabledMods=256 jars=228`。
  - `starsector.log`：`Java version: 17.0.10 (64-bit)`。
  - `scripts-agent.log`：`hypernova agent premain`；
    `lazy: unsupported FR version 0.9.5; lazy textures disabled`；
    `file index: unsupported FR version 0.9.5; disabled`；
    `scripts cache transformer registered`；
    `scripts cache preloaded: entries=18`。
- 尝试 3 的 OOM 是**内存不足**的直接证据；尝试 4 提高内存后 OOM 消失。
- 尝试 4 结束时：日志约 45 MB，持续写规则/脚本；
  `m6_log_audit total=0 ok=true complete=true`；无 Fatal、无五类纹理错误、
  未出现主菜单锚点。按协议记为 **timeout-not-menu**，不是崩溃。
- 证据：`evidence/fixloop1/route-a-run4-timeout/`、
  `route-a-run3-oom/`、`route-a-run2-missing-jars/`、
  `route-a-run3-status.txt`（2 GB OOM 轮询状态）。

### 3.4 no-Hypernova 对照

- 上一轮已做：从 `route-a.vmparams` 仅移除 Hypernova agent，重新启动；
  5 s 后报**完全相同**的 `Missing enabled mod jar`（迷失武器包）。
- 结论：最初 A 的阻断与 Hypernova 无关，是 mod 声明 jar + MixinFR 严格校验。
- 证据：`evidence/m7-route-a/control-no-hypernova/`。

### 3.5 回滚

- label：`m7-route-a-20261104-021154-749861`。
- `rollback --apply`（绝对 root，路径修复后）：
  `restored=1 deleted=12 ok=true`；
  `mods/MixinFR`、`mods/StarsectorParallel`、
  `mods/hypernova_infinite_engine`、`route-a.vmparams`、
  `launch-route-a.bat`、`starsector-core/graphics/hypernova/blank.png`
  全部删除；`enabled_mods.json` 恢复为 apply 前的 255。
- 随后手工恢复最初 256 项 enabled 列表（含 3 个坏 mod），供路线 B 使用。

## 4. 路线 B 自动化证据

### 4.1 安装（fix loop）

- `route-b --apply --xms 8G --xmx 10G`（绝对 root）：
  - `applied=true ok=true`；
  - `generated=2 copied=15 agent_rc=0`；
  - manifest `L1=6624 L2=18525 L3=55400 skip=73347`，Critical=0；
  - `created_dirs=[mods/DDSCache]`；
  - `enabled_mods.count=257`；
  - rollback label `m7-route-b-20261104-024921-195133`。
- `jdk-28+13/bin/java.exe -version`：Temurin `28-beta+13-ea`；
  `fr.version.txt=v0.9.7rc2`。
- `route-b.vmparams`：`-Xms8G -Xmx10G`；JRE 17 专属 token
  （`-noverify`、`--enable-preview` 等 7 项）已移除；agent 顺序
  Hypernova → FR；`fr.jar` 在 classpath 首位；首 token 是 JVM 参数。
- 安装器现在会创建 `mods/DDSCache` 并纳入回滚；LunaLib 设置做只读预检。

### 4.2 模组/环境前提（与 Hypernova 无关）

1. **`jc_sf`（SF-幽灵部队）**：运行到 436 s 时
   `data.scripts.Jc_asm_ModPlugin.modFileCheck` 抛
   `幽灵部队模组文件损坏，请重新安装！`；Fatal 对话框已截图。
   临时禁用 `jc_sf` 后继续。
2. **AoTD Theory of Toolbox**：运行到 439 s 时要求把
   `Ashes of The Domain - Theory of Toolbox/0.98a/starfarer.api.jar`
   复制到核心；否则 Fatal（“市场测试失败”）。
   源 260mods 的核心 jar 与该 bundled jar 的 sha256 完全一致
   （`ad41a688…`），说明 260mods 已应用过该替换。fix loop 备份目标原 jar
   （`769c8e94…`）后替换；回滚时已恢复原 jar。
   没有采用“禁用 AoTD”的方案，因为 `aotd_theory_of_toolbox` 的类被其它
   AoTD 子模组依赖，禁用会导致 `NoClassDefFoundError`。
3. **LunaLib 设置**：上一轮 2 GB 运行曾把 257 个 `*.json.data` 写成同一份
   1521 B 内容，导致 IndEvo NPE；本轮启动前把 260mods 的 75 份真实设置
   复制到目标，运行后未再损坏（74 个唯一 hash）。
4. **DDSCache**：路径预检 + apply 自动创建空目录；FR 不再因缺目录 Fatal。

### 4.3 主菜单运行（fix loop）

- 启动：`jdk-28+13\bin\java.exe -DlaunchDirect=true -DstartRes=1707x1067
  -DstartFS=false -DstartSound=true @..\route-b.vmparams`。
- **主菜单锚点**：
  `starsector.log.1:280362:105769 [Thread-18] INFO sound.H - Playing music with id [miscallenous_main_menu.ogg]`
  → 进程启动后 **105.8 s** 到达主菜单。
- 截图：`evidence/fixloop1/window-route-b-menu.png`（Starsector 主菜单，
  FPS 60）。
- 启动日志：
  - `Fast Rendering: v0.9.7rc2`
  - `Java version: 28-beta (64-bit)`
  - `VOpt Loaded`
  - `FR Version: v0.9.7rc2`
  - `Suitable FR Version found, skipping DDS file handling`
- Hypernova agent（`saves/hypernova/scripts-agent.log`）：
  - `file index transformer registered`
  - `hypernova agent premain`
  - `lazy: transformers registered`
  - `textures normal-cache transformer registered`
  - `scripts cache transformer registered`
  - 菜单期 lazy probe：`index=73347`、`hits=7192`、`misses=0`、
    `degraded=0`、`failed=0`、`disabled=0`、`main=main`、
    `liveBytes≈16.1 MB`（菜单），`dds=1`、`ddsFallback=31`、
    `ddsFbMeta=31`。
- 五类纹理错误：`starsector.log` 与 `starsector.log.1` 逐份扫描
  `total=0`；`m6_log_audit`（当前 log + agent log）`total=0 ok=true
  complete=true`。
- 按 PID 46480 结束游戏；运行期间无 Fatal/OOM。

### 4.4 自动化读档 + 战斗（日志级证据，非用户 gate）

B 菜单运行的日志还显示：游戏在读档后实际进入了战斗。这是**日志级自动化
证据**，不是用户视觉/输入 gate。

关键 log（`evidence/fixloop1/route-b-menu/starsector.log` / `.log.1`）：

- `:141208 Reading save data from [D:\github\...\Starsector-098-260mods\starsector-core\..\saves\save_123_8126140098359840818\descriptor.xml]`
- `:141206 aEP_CombatEffectPlugin Registered in CombatLayeredRenderingPlugin`
- `:141399 Hypernova main thread bound at advance: main`
- `:141403 HYPERNOVA_TICK 1 ... ticks=1`
- `:141611 'BoxUtil' Combat rendering plugin join layer: 'ABOVE_PARTICLES_LOWER'`
- `:146542 / :151473 / ... / :222674 KE_EtherCombatPlugin ...`
  （以太之潮 tick 持续到 222 s+）
- `:192183 HYPERNOVA_TICK 3001 ... ticks=3001, nanosLastTick=2700, backlog=0`
- 141–222 s 仍有武器/导弹/材质贴图加载。

**触发器**：

- 本轮**没有** agent 脚本点击、SendInput/PostMessage 或手工菜单操作；
  唯一自动化是进程启动（`launchDirect`）和非交互的
  `SetForegroundWindow`/`PrintWindow` 截图。
- 主菜单音乐锚点在 105.769 s，首次 save descriptor 读取在 106.036 s
  （+267 ms）；141.208 s 再次读取并进入战斗。这个时序更像**自动
  continue/读档**，而不是菜单点击。
- 无法从日志证明具体是 `launchDirect` 分支还是某个 mod 的 auto-continue；
  也不能完全排除用户物理键鼠输入，但没有任何 agent 注入。

**存档来源**：

- 日志路径是 `Starsector-098-260mods\starsector-core\..\saves\save_123_...`；
  实验根 `saves/` 在 B 前后都是空的，**没有由我们复制过存档**。
- B 日志里 `SS098_Hypernova...` 路径出现 65,757 次，
  `Starsector-098-260mods` 只出现 1 次（就是这条 save 路径）——游戏本体
  确实从实验根运行。
- `save_123` 的 `descriptor.xml`/`campaign.xml` 内含绝对 260mods mod 路径；
  这是**260mods 的既有存档**，不是实验根新建的存档。具体由游戏 save index
  还是 descriptor 记录的原路径解析到 260mods，本轮**没有证明**；作为
  provenance caveat 记录。

**判定**：

- 可作为“B 栈能加载既有存档并运行战斗”的**日志级自动化证据**；
  Hypernova 主线程绑定、`HYPERNOVA_TICK 1→3001`、战斗渲染插件注册均出现。
- **不能**写成用户实机 gate 通过：没有视觉/UI/输入/字体/稳定性验证，
  存档来源也不是实验根的新存档。用户 gate 仍全部 pending。

### 4.5 F3：上一轮 360 s 时间线（不是游戏自身崩溃）

上一轮 2 GB 运行在 325 s 轮询结束后，日志继续记录到 360 s，然后再被 PID
结束。该时间片的关键行：

```
2026-11-03T17:45:57.825Z ERROR lazy: materialize failed for
  graphics/weapons/blonkers/blonkerCyan/blinker08.png (attempt 1)
java.lang.NullPointerException: Cannot read field "texGenerator" because
  ContextManager.getThreadContext() is null
2026-11-03T17:46:07.532Z lazy probe ... failed=1
  liveBytes=2706485672
starsector.log 360639 ms ERROR com.fs.starfarer.combat.CombatMain
  ... org.lwjgl.LWJGLException: Could not make current context
```

- 这些行出现在 325 s 轮询之后、按 PID 结束的时间窗内；**疑似由结束进程
  触发的上下文销毁导致**，不能当作游戏自身崩溃。
- **口径补充**：`m6_log_audit` 的五类错误模式**不覆盖**
  `ERROR lazy: materialize failed`；因此 audit `total=0` 不能用来否认这条
  ERROR，只能说明它不在审计模式集合内。本节直接引用原始日志行。
- fix loop 的 8G/10G 菜单运行中 lazy `failed=0`，无 materialize 失败，
  支持“上一轮是结束过程/内存不足共同作用”的判断。
- 证据：`evidence/m7-route-b/scripts-agent.log`（失败切片）、
  `evidence/fixloop1/route-b-menu/`（成功切片）。

### 4.6 F4：超时原因分析

- 旧运行 `-Xmx2048m`，256 mod；360 s 时 Hypernova `liveBytes≈2.7 GB`，
  超出 2 GB heap/直接内存默认上限；这是超时的**候选原因**。
- 但旧日志**没有 `OutOfMemoryError`**；不能把超时单方面归因于 OOM。
- fix loop 用 `-Xms8G -Xmx10G`，菜单在 105.8 s 到达。该结果与“内存/加载
  时间是主因”一致，但同时还有 normal-map 缓存、LunaLib 设置修复、`jc_sf`
  禁用等变化，**不是单变量对照**；不宣称性能收益。

### 4.7 F5：B 的 no-Hypernova 对照

- fix loop 的 B **已到达主菜单**，因此没有触发“仍未到菜单则做
  no-Hypernova 对照”的条件；本轮**未做**该对照。
- 如后续需要严格归因，可在同一 8G/10G 环境移除 Hypernova agent 重跑，
  比较到达菜单的时间；本轮不把菜单到达归功于 Hypernova。

### 4.8 回滚

- label：`m7-route-b-20261104-024921-195133`。
- `rollback --apply`（绝对 root）：`restored=2 deleted=20 ok=true`。
- 删除/恢复：`route-b.vmparams`、`jdk-28+13`、`starsector-core/fr.*`、
  `mods/hypernova_infinite_engine`、`mods/DDSCache`、`blank.png`、
  `fr.vmparams.bak-hypernova`；`enabled_mods.json` 恢复到 apply 前 256；
  `launch-route-b.bat` 恢复到 apply 前内容。
- 手工恢复：`starfarer.api.jar` 回到原优化版 jar
  （`769c8e94…`）；清理 `saves/common`、`saves/hypernova`、FR/字体缓存和日志。

## 5. 用户实机 gate（全部 pending）

| # | 场景 | 结果 |
|---|---|---|
| 1 | 主菜单（启动后停留 30 s） | **B 已到主菜单**；A 未到（timeout）。仍不替代后续场景 |
| 2 | 战役（新开/载入，进星系/市场） | pending |
| 3 | 战斗（小规模） | pending |
| 4 | 读档/存档 | pending |
| 5 | 分辨率/全屏/alt-tab | pending |
| 6 | 中文输入（改名/搜索/对话） | pending |
| 7 | 字体视觉（LunaLib/市场/对话/舰船） | pending |
| 8 | 稳定性（20–30 分钟） | pending |

**B 的菜单到达不等于战役、战斗、读档、中文输入或字体视觉通过。**
B 的 141–222 s 读档/战斗是**日志级自动化证据**（见 4.4）：存档来自 260mods
既有 `save_123`，不是实验根新建存档；Hypernova tick 和战斗插件注册只能
证明加载链/战斗引擎跑过，不能证明视觉、输入、字体或稳定性。场景 #3/#4
仍为 **pending**，不标通过。
A 的菜单未到达，不能用任何自动化指标替代用户 gate。

## 6. 失败归因

### 6.1 路线 A

- **最初阻断**：`迷失武器包`、`CRS_Mod_Core`、`StopGapMeasures3`
  三个 mod 的 `mod_info.json` 声明了不存在的 jar；MixinFR 1.2.5 的
  `LaunchSnapshot` 对启用 mod 的声明 jar 做存在性校验并 fail-closed。
  no-Hypernova 对照得到同一失败，排除 Hypernova。
- **fix loop**：禁用这 3 个 mod 后，apply `ok=true`，MixinFR/Parallel/
  Hypernova 全部加载；2 GB 运行出现直接缓冲 OOM，提高到 8G/10G 后 OOM
  消失，但 600 s + 延长到约 1200 s 仍停留在规则/脚本加载，未到菜单。
  这是**启动时间**问题，不是崩溃；无 Fatal、纹理错误 0。
- MixinFR 的 FR 0.9.5 使 Hypernova `lazy`/file-index 关闭（预期限制），
  且脚本缓存只有 18 条，完整脚本编译/规则加载很慢。
- 证据：`evidence/fixloop1/route-a-run4-timeout/`、
  `route-a-run3-oom/`、`missing_declared_jars.json`。

### 6.2 路线 B

- **旧 2 GB 超时**：300 s 未到菜单；F4 的 `liveBytes≈2.7 GB` 是候选，
  但日志无 OOM 证据；F3 的 360 s materialize/NPE/context 错误发生在
  PID 结束窗口，疑似结束过程导致。
- **fix loop**：`--xms 8G --xmx 10G` + normal-map/LunaLib 修复后，菜单在
  105.8 s 到达；lazy `misses=0 failed=0`，纹理错误 0。
- **与 Hypernova 无关的模组前提**：
  - `jc_sf` 自检失败 → 临时禁用；
  - AoTD Theory of Toolbox 要求核心 `starfarer.api.jar` 替换 → 按 260mods
    已知可用配置替换，回滚恢复；
  - LunaLib 首轮 257 份相同设置 → 用 260mods 设置修复；
  - `mods/DDSCache` → 安装器创建。
- F5：B 已到菜单，未做 no-Hypernova 对照；不把菜单到达归因于 Hypernova。

## 7. 默认值与回滚

### 7.1 默认值

- M7 两条路线仍**默认 off**；根 `vmparams` 全程未改。
- 路线 A 的 8G/10G 是 fix loop 手工补丁；工具目前没有 route-a 的
  `--xmx` 接口（见 7.3）。
- 路线 B 的 `--xms/--xmx` 是显式 CLI；默认仍保留源 vmparams 值。
- 最终场景：`mods/` 258 项（256 junction + `ChineseInputFix` +
  `enabled_mods.json`），`enabled_mods=256`，
  `vmparams=8f88ab53…`，`starfarer.api.jar=769c8e94…`（原优化版），
  无 route/MixinFR/FR/JDK/DDSCache 残留；`launch-route-a.bat` 已删除，
  `launch-route-b.bat` 恢复到 apply 前内容。

### 7.2 回滚结果

| 路线 | label | 工具结果 | 备注 |
|---|---|---|---|
| A（最初） | `m7-route-a-20261104-005534-097705` | `restored=1 deleted=2` | 相对 root 路径重复 bug；手工清理 3 目录 + blank.png |
| A（fix loop） | `m7-route-a-20261104-021154-749861` | `restored=1 deleted=12 ok=true` | 路径修复后完整删除 |
| B（fix loop） | `m7-route-b-20261104-024921-195133` | `restored=2 deleted=20 ok=true` | DDSCache 也删除；核心 jar 手工恢复 |

### 7.3 工具修复（本轮）

1. **junction manifest**：
   - `manifest_builder` 写 `absolutePath`/`ddsPath` 改用 lex 绝对路径
     （`os.path.abspath`），不再 `Path.resolve()` 跟随 junction；
   - `validate_manifest._inside_root` 改为 `abspath + normcase +
     commonpath` 的 lex 包含判断；
   - 目标根 `install_manifest` 现在 rc=0、0 Critical。
   - 测试：`test_junction_inside_root_is_not_outside`。
2. **relative `--root` 回滚**：
   - `plan_route_a` / `plan_route_b` 的 `base` 统一 `.resolve()`，回滚清单
     不再出现 `<root>\<root>\...`；`blank.png` 等路径可正确删除。
   - 测试：`test_route_a_relative_root_rollback_removes_created_mods_and_blank`。
3. **路线 B Java 28 参数**：
   - 移除 7 个 JRE 17 专属 token：`-noverify`、
     `-XX:+UseXMMForArrayCopy`、`-XX:+ParallelRefProcEnabled`、
     `-XX:+AlwaysAtomicAccesses`、`-XX:+UseVectorStubs`、
     `-XX:ShenandoahGCMode=iu`、`--enable-preview`；
   - 新增 `--xms/--xmx`：只传一个时保留源 vmparams 里的另一个，plan 输出
     最终 `memory.xms/xmx`；两者同时传入才完全覆盖。
   - 测试：`test_plan_route_b_removes_java17_flags_and_applies_memory`、
     `test_plan_route_b_single_memory_override_preserves_other`、
     `test_plan_route_b_rejects_invalid_xmx`。
4. **环境预检**：
   - `mods/DDSCache` 缺失时 plan 告警，apply 创建并纳入回滚；
   - `saves/common/LunaSettings` 只读预检，检测“所有文件同 hash”的已知
     损坏并告警；不写用户设置。
   - 测试：`test_plan_route_b_prechecks_ddscache_and_lunalib`。
5. **终审 must-fix（2026-11-04）**：
   - route A/B 的 `enabled_mods.json` 在 **missing / 解析错误**时都
     fail-closed：apply 打印 `FATAL`、返回 1，不写任何启用列表。
   - 路线 A 断言 MixinFR `mod_info.version=1.2.5`、Parallel `0.1.0`；
     不匹配时 plan/apply 输出 `WARNING`（plan 文本含 `mixinfr.version` /
     `parallel.version` 字段）。
   - 测试：`test_apply_route_b_refuses_missing_enabled_mods`、
     `test_apply_route_a_refuses_missing_enabled_mods`、
     `test_route_a_warns_on_unexpected_version`、
     `test_route_a_text_shows_version_checks`。
6. 测试结果（2026-11-04 终审 fix）：`python -I -m pytest tests/tools -q`
   → **565 passed**（修复前 556 passed；新增 fail-closed / 单参数内存 /
   版本断言测试）。

## 8. 限制

- **A 未到菜单**：600 s 上限 + 延长到约 1200 s 仍停在规则/脚本加载；
  只证明 apply/manifest/内存修复有效，不能证明 A 可玩。
- **B 菜单到达但有前提**：`jc_sf` 禁用、AoTD 核心 jar 替换、LunaLib 设置
  恢复、DDSCache 创建；这些是环境/模组前提，不是 M7 默认行为。
- **B 不是单变量收益证明**：8G/10G、缓存、LunaLib、jc_sf、AoTD jar 同时
  变化；不比较帧率、显存或启动时间收益。
- **F3/F4 口径**：旧 360 s 的 materialize/NPE/context 错误与 PID 结束窗口
  重叠，不能当作游戏自身崩溃；旧日志无 OOM 证据，2.7 GB liveBytes 只是
  超时候选。
- **F5**：B 已到菜单，未做 no-Hypernova 对照；不宣称 Hypernova 是菜单到达的
  原因。
- **读档/战斗证据的边界**：B 的 141–222 s 读档/战斗是**日志级**；存档来自
  260mods 既有 `save_123`，实验根 `saves/` 为空；没有 agent 点击，时序像
  自动 continue，但具体触发器未证明。它不证明视觉/输入/字体/稳定性，也不把
  场景 #3/#4 标通过。
- **A+ 未到菜单**：600 s 内仍在 rules/scripts；MixinFRImeFix 只确认 jar
  被发现，未产生可判定的 `REMAP-OK`/IME bridge；Parallel 热点 mixin
  `NOT-INJECTED`，不能把“组件已装”写成“Parallel 已生效”。
- **B+ 菜单但有前提**：Prepatcher 0.18.4 在 Java 28 未声明（4 个 patch
  skipped）；`jc_sf` 禁用、AoTD 核心 jar 替换仍是模组前提；CIF 只证明
  加载/窗口子类化，不代表用户输入/候选框验收；不宣称收益。
- **用户 gate 全 pending**：战役、战斗、读档、中文输入、字体视觉、稳定性
  均未验证。
- **第三方合规**：不重新分发任何第三方文件；AoTD jar/LunaSettings 仅从用户
  已有的 260mods 读取。

## 9. A+ / B+ 组件补齐复跑（2026-11-04）

### 9.1 组件表

| 路线 | Java | FR | MixinFR | Parallel | VramOpt | Hypernova | CIF | Prepatcher | MixinFRImeFix | Mikihime |
|---|---|---|---|---|---|---|---|---|---|---|
| **A+** | JRE 17.0.10 | MixinFR 内置 0.9.5 | 1.2.5 | 0.1.0 | 1.0.45 | 0.1.0 | 否 | **排除** | 是（MixinFR 包内） | JRE17 兼容子集（16 项） |
| **B+** | Temurin 28-beta+13 | 0.9.7rc2 | 无 | 无 | 1.0.45 | 0.1.0 | **启用**（2.0.0，日志 v2.2） | **0.18.4** | 否 | 完整 JDK28 调优（47 项） |

### 9.2 启动结果

#### A+

- apply：`applied=true ok=true`；manifest
  `L1=6624 L2=18290 L3=55231 skip=72944`，Critical=0；
  rollback label `m7-route-a-20261104-050308-745309`。
- 为通过 MixinFR `LaunchSnapshot`，实验根临时禁用 3 个声明 jar 缺失的
  mod（`missingshipsweapons`、`CRS_Mod_Core`、`StopGapMeasures3`）；
  这是 mod 包问题，不是 M7 组件缺失。
- 启动 600 s：**未到达主菜单**。617 s 时仍在加载 `Pch_*` rules/scripts；
  无 Fatal/OOM；`m6_log_audit total=0`；五类纹理错误 0。
- `starsector.log`：`Java version: 17.0.10 (64-bit)`；
  `mixinlib.log`：`integration=MixinFR+FastRendering phase=fr`；
  `Handoff - game JVM started pid=55840 enabledMods=256 jars=228`。
- MixinFRImeFix：`discovered mixinfr.imefix.mixin.json from .../MixinFRImeFix.jar`；
  因未到菜单，`mixinfr-fonthd.log`/`mixinfr-ime-fix.log` 没有产生可判定的
  `REMAP-OK`/IME bridge 行。
- StarsectorParallel：mod 与 `starsectorparallel.mixin.json` 已加载，
  `APPLY ... CombatAiHotspotMixin` 后
  `PROBE ... verdict=NOT-INJECTED`；原因：
  `[MixinGovernance] WARN target is rewritten by Fast Rendering:
  com.fs.starfarer.combat.CombatEngine ... the mixin will likely not apply`。
  **Parallel 组件存在但热点 mixin 未实际注入。**
- Hypernova：`premain` 正常；`lazy: unsupported FR version 0.9.5; disabled`、
  `file index: unsupported FR version 0.9.5; disabled`、
  `scripts cache transformer registered`（cold，`preloaded=0`）。
- rollback：`restored=1 deleted=12 ok=true`。

#### B+

- apply：`applied=true ok=true`；manifest
  `L1=6518 L2=18323 L3=55102 skip=72847`，Critical=0；
  `copied=16`（含 Prepatcher），`created_dirs=[mods/DDSCache]`；
  enabled 258 = 255（`jc_sf` 禁用）+ Hypernova + Prepatcher + CIF；
  rollback label `m7-route-b-20261104-051743-293497`。
- 启动 **到达主菜单**：
  `starsector.log:355296 [Thread-18] INFO sound.H - Playing music with id [miscallenous_main_menu.ogg]`
  → **355.3 s**（600 s 内）。
- `starsector.log`：`Java version: 28-beta (64-bit)`；
  `Fast Rendering: v0.9.7rc2`；`VOpt Loaded`；
  `Suitable FR Version found`。
- CIF：`[CIF] 中文输入修复 v2.2 已加载`；
  `[CIF] [SysIME] 窗口子类化成功 ... client=1707x1067`；
  `ReflectionUtils 初始化成功`。**未执行 `disable-ime`**，
  `ssime.dll` 保持原状；只启用了 CIF mod。
- Prepatcher：
  `StarsectorPrepatcher 0.18.4: status=transformer-installed,
  patchedClassesSoFar=16, appliedPatchesSoFar=21, skippedPatchesSoFar=4`。
  没有大量 `SKIPPED_LOADER`；Java 28 未声明的 warning 仍保留在 plan/文档。
- Hypernova：`premain`、`file index transformer registered`、
  `lazy: transformers registered`、`scripts cache transformer registered`；
  菜单/读档期 lazy probe `index=72847`、`misses=0 degraded=0 failed=0
  disabled=0 main=main`、`liveBytes≈2.9 GB`。
- 五类纹理错误：`starsector.log`+`.1` 均 0；`m6_log_audit total=0
  complete=true`。
- 菜单锚点后日志还出现 260mods 既有 `save_123` 的读档与战斗
  （`Reading save data`、BoxUtil/aEP 战斗插件、`HYPERNOVA_TICK 1`），
  与上一轮 B 相同：**日志级自动化证据，不是用户实机 gate**；
  存档来源仍是 260mods 既有存档，实验根 `saves/` 为空。
- rollback：`restored=2 deleted=21 ok=true`；`mods/DDSCache`、
  Prepatcher、JDK、FR、Hypernova 均删除；核心 `starfarer.api.jar`
  手工恢复到原优化版 `769c8e94…`；enabled 恢复为原始 256。

### 9.3 Mikihime 参数清单

事实：`mikohime/configurator/shared/java-versions.properties` 只有
`Jdk27/Jdk28`，**没有 JRE17**；`Miko_Lite.txt` 是 Mikihime 的 JDK28 参数
（`-Xms8192m -Xmx10240m`，G1）。

验证方法：对每个候选参数跑
`java <options> -version`（目标 JRE/JDK，临时目录），迭代移除 JVM 拒绝的
参数；采用项 = 目标 Java 接受，剔除项 = 目标 Java 拒绝或
Mikihime 路径/classpath 专属。证据：
`evidence/fixloop2/mikohime-jre17.json`、
`evidence/fixloop2/mikohime-full.json`。

#### A+：JRE17 兼容子集（采用 16 项）

```text
-XX:+UnlockDiagnosticVMOptions
-XX:+UnlockExperimentalVMOptions
-XX:+TieredCompilation
-XX:TieredStopAtLevel=4
-XX:+UseCompressedOops
-XX:+UseG1GC
-XX:+UseStringDeduplication
-XX:ReservedCodeCacheSize=512m
-XX:-BytecodeVerificationLocal
-XX:-BytecodeVerificationRemote
-XX:+ShowCodeDetailsInExceptionMessages
-XX:+ExtensiveErrorReports
-XX:+PrintCommandLineFlags
-Xss4m
-Xms8192m
-Xmx10240m
```

JRE17 明确拒绝的 4 项（`java -version` 报 Unrecognized VM option）：

```text
-XX:+UseCompactObjectHeaders
-XX:+HotCodeHeap
-XX:+AlwaysPreTouchStacks
-XX:+ErrorLogSecondaryErrorDetails
```

另外 32 项未采用（`excluded_profile`）：Mikihime 专属
`-Xlog:gc*:file=gc-miko.log...`、`-XX:CompilerDirectivesFile=..\mikohime/...`、
`-Dlog4j*`/`-Djava.xml.config.file`/`-Dcom.fs.starfarer.launcher_bg`/
`-Djava.library.path=..\mikohime/windows`、`--add-opens`/`--add-exports`
（源 argfile 已有游戏所需 opens/exports）、`--enable-*` 等。
A+ 保留源 `-Djava.library.path=native\windows`、源 classpath/main。

#### B+：完整 JDK28 调优（采用 47 项）

采用项（全部被 Temurin 28+13 接受；`excluded_java=0`）：

```text
-XX:+UnlockDiagnosticVMOptions
-XX:+UnlockExperimentalVMOptions
-Xlog:async
-Xlog:gc*:file=gc-miko.log:time,uptime,level,tags:filecount=3,filesize=20M
-XX:+TieredCompilation
-XX:TieredStopAtLevel=4
-XX:+UseCompactObjectHeaders
-XX:+UseCompressedOops
-XX:+HotCodeHeap
-XX:+UseG1GC
-XX:+UseStringDeduplication
-XX:+AlwaysPreTouchStacks
-XX:ReservedCodeCacheSize=512m
-XX:-BytecodeVerificationLocal
-XX:-BytecodeVerificationRemote
-Dlog4j1.compatibility=true
-DLog4jContextSelector=org.apache.logging.log4j.core.async.AsyncLoggerContextSelector
-Dlog4j2.enableThreadlocals=true
-Dlog4j2.enableDirectEncoders=true
-Dlog4j2.garbagefreeThreadContextMap=true
-Djava.util.Arrays.useLegacyMergeSort=true
-Dsun.java2d.renderer.useRef=weak
--add-opens=java.base/sun.nio.ch=ALL-UNNAMED
--add-opens=java.base/java.nio=ALL-UNNAMED
--add-opens=java.base/java.util=ALL-UNNAMED
--add-opens=java.base/java.util.concurrent=ALL-UNNAMED
--add-opens=java.base/java.util.concurrent.locks=ALL-UNNAMED
--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED
--add-opens=java.base/java.lang.reflect=ALL-UNNAMED
--add-opens=java.base/java.lang.ref=ALL-UNNAMED
--add-opens=java.base/java.lang=ALL-UNNAMED
--add-opens=java.management/javax.management=ALL-UNNAMED
--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED
--add-opens=java.base/java.text=ALL-UNNAMED
--add-opens=java.desktop/java.awt.font=ALL-UNNAMED
--add-opens=java.desktop/java.awt=ALL-UNNAMED
--enable-native-access=ALL-UNNAMED
--enable-final-field-mutation=ALL-UNNAMED
-XX:+ShowCodeDetailsInExceptionMessages
-XX:+ExtensiveErrorReports
-XX:+ErrorLogSecondaryErrorDetails
-XX:+PrintCommandLineFlags
-Xlog:gc+init
-Dsun.java2d.renderer.useLogger=true
-Xss4m
-Xms8192m
-Xmx10240m
```

未采用的 5 项（`excluded_profile`，Mikihime 路径专属，实验根没有
`mikohime/` 运行时；保留源游戏的 `native\windows`/log4j 配置）：

```text
-XX:CompilerDirectivesFile=..\mikohime/.rouge_owo
-Djava.library.path="..\mikohime/windows"
-Dlog4j.configuration=..\mikohime/mikohime.properties
-Djava.xml.config.file=..\mikohime/miko_jxp.properties
-Dcom.fs.starfarer.launcher_bg=..\mikohime/launcher_bg.jpg
```

### 9.4 用户实机 gate

A+ **未到主菜单**；B+ **到主菜单**但只有日志级证据。战役、战斗、读档、
中文输入、字体视觉、分辨率、稳定性仍全部 **pending**。B+ 的 CIF/Prepatcher
加载状态是组件级证据，不等于 IME 候选框/字体视觉/Prepatcher 行为已由用户
验收；不宣称性能或显存收益。

## 10. B 最终参数裁决（2026-11-04 补充）

- **最终 B 配置**：完整 Mikihime JDK28 47 项（源
  `Starsector-098-260mods/Miko_Lite.txt`；其中 `-Xms8192m/-Xmx10240m`
  统一表达为 `-Xms8G -Xmx10G`）+ FR 0.9.7rc2 + VOpt 1.0.45 + Hypernova +
  CIF（启用）+ Prepatcher 0.18.4；enabled 258（`jc_sf` 禁用）。
- **热缓存复测**（`optimized-b-debug`，同一根、同一组件集合，连续 3 次）：
  **68.2 / 57.1 / 59.2 s**，中位 **59.2 s**。
- **组件加载**：`Java version: 28-beta`、`Fast Rendering: v0.9.7rc2`、
  `VOpt Loaded`、CIF v2.2 窗口子类化、Prepatcher 0.18.4
  `transformer-installed`、Hypernova lazy `misses=0 failed=0`；
  `m6_log_audit total=0 ok=true complete=true`；五类纹理错误 0。
- **依据**：同缓存下完整 47 项控制组为 67.7 s，说明参数不是慢因；
  B+ 的 355.3 s 由 30,043 张冷法线生成造成；历史 B 105.8 s 是精简参数 +
  热缓存，不能作为“精简优于完整”的证据。冷启动参考约 465 s（同组件、
  精简参数冷跑；完整 Mikihime 未单独重复冷跑）；105.8 s 与 57–68 s
  都是热缓存数字。
- 详细逐组对照、缓存 key 结论与现场恢复见 `docs/m7-b-debug.md`。
