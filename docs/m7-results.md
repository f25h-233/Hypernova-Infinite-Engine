# M7 统一部署包：两路线实机验证结果（Task 7）

> 日期：2026-11-04。实验根：
> `SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15`。
> 本文只记录**真实启动到主菜单为止**的自动化证据；战役 / 战斗 / 读档 /
> 中文输入 / 字体视觉仍是用户 gate，全部 **pending**。
> **两条路线都没有在本轮到达主菜单**，因此下文没有任何“整套通过”的结论，
> 也不宣称性能或显存收益。

## 1. 结论

| 路线 | 安装结果 | 主菜单 | 结论 |
|---|---|---|---|
| A（MixinFR 1.2.5 + JRE 17 + StarsectorParallel） | 文件已安装；apply 在 manifest 步骤前被外部中断，manifest 由源安装补生成 | **未到达** | **blocked**：MixinLib `LaunchSnapshot` 在游戏 JVM 启动阶段 fail-closed，报 `Missing enabled mod jar: mods\迷失武器包\jars\missp_varunastra.jar`。该 jar 在 mod 包内确实不存在；`mod_info.json` 却声明了它。 |
| B（FR 0.9.7rc2 + Java 28 + Hypernova） | `applied=true`，但 `ok=false`（junction 导致 manifest 校验 Critical）；agent 安装 rc0 | **未到达（300 s 超时）** | 已确认 **Java 28 / FR 0.9.7rc2 / Hypernova agent + lazy + file index + scripts cache 全部加载**；最后一次运行在 325 s 时仍停留在加载进度条，无 Fatal、五类纹理错误 0。按 300 s 协议记为 timeout，不记为菜单通过。 |

关键判断：

- 路线 A 的失败点**不是 Hypernova**：去掉 Hypernova agent 的 no-Hypernova 对照得到同一
  `Missing enabled mod jar` 失败。
- 路线 B 的早期失败是**工具/环境**问题，不是 Hypernova：Java 28 拒绝 JRE 17 参数、
  缺 `mods/DDSCache`、LunaLib 设置被写成 257 份相同内容、`--enable-preview`
  触发 Java 28 identity 规则。逐项处理后最后一次运行无 Fatal，但未在 300 s 内到菜单。
- M7 工具在本次实机中暴露了 4 个需要修的工具侧问题（junction manifest 校验、
  relative `--root` 回滚路径重复、路线 B 继承 Java 17 参数、运行环境
  `DDSCache`/LunaLib 设置未预检），见第 7 节。

## 2. 环境

| 项 | 值 |
|---|---|
| 游戏 | Starsector 0.98a-RC8，远星汉化优化测试版 2026.10.15（`branch=startup-optimization`） |
| 实验根 | `SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15` |
| 迁移 | 256 个启用 mod + `ChineseInputFix`，`--link` 共 257 个目录联接；`enabled_mods.json=256` |
| 随包 JRE | Zulu 17.0.10（路线 A） |
| 路线 B JDK | Temurin `28-beta+13-ea`（`jdk-28+13`） |
| MixinFR | 1.2.5（内置 FR 0.9.5） |
| StarsectorParallel | 0.1.0 |
| Fast Rendering | v0.9.7rc2 |
| VramOptimizer | 1.0.45（在 256 mod 迁移列表中） |
| Hypernova | 0.1.0，`build/agent/hypernova.agent.jar` + `build/java/hypernova.jar` |
| 根 `vmparams` | `sha256=8f88ab530c3e989ca027f4aff320a49d8115cab281cd2e592bf9b57c83a29fee`，`-Xmx2048m -Xms2048m` |
| 验证日 | 2026-11-04，Windows 11 中国区 |

方法说明：

- `migrate --apply --link` 只创建实验根 `mods/`，未改
  `Starsector-098-260mods`。
- 路线 A/B 都不改根 `vmparams`；agent 写在 `route-a.vmparams` /
  `route-b.vmparams`，用显式 `java.exe @argfile` 启动。
- `java @argfile` 本身只会打开 Starsector 启动器 UI，不会自动进游戏。
  实机启动额外注入 M6 已实测的
  `-DlaunchDirect=true -DstartRes=1707x1067 -DstartFS=false -DstartSound=true`，
  绕过启动器 UI。第一次不知情时只到了启动器设置窗口（截图见证据），不是主菜单。
- 所有进程都按 **PID** 结束；未使用 `taskkill /IM java.exe`。

## 3. 路线 A 自动化证据

### 3.1 迁移与安装

- `migrate` dry-run：`copy=256 enabled=256 excluded=hypernova_infinite_engine
  extras=ChineseInputFix missing_enabled_ids=-`，
  `duplicate_ids=lw_console:ConsoleCommands,shaderLib:GraphicsLib,lw_lazylib:LazyLib,particleengine:Particle Engine`。
- `migrate --apply --link`：`applied=true copied=256 extras_copied=1
  total_copied=257 enabled=256 link=true`，rc=0。
- 目标 `mods/` 258 项 = 256 个 junction + `ChineseInputFix` + `enabled_mods.json`；
  junction 257 个。
- 路线 A apply 在 manifest 步骤前被外部中断；**没有重跑 route-a --apply**。
  现场由协调方核实后继续：
  `mods/MixinFR`、`mods/StarsectorParallel`、`mods/hypernova_infinite_engine`、
  `route-a.vmparams`、`scripts/launch-route-a.bat` 已存在，
  回滚清单为
  `backups/m7-route-a-20261104-005534-097705/route-rollback.json`。

### 3.2 manifest（junction 限制）

- 对实验根直接跑
  `python -I tools/install_manifest.py --game-root <root>`：**rc=1**。
  原因是 `validate_manifest._inside_root()` 对 junction 做 `Path.resolve()`，
  所有资产被解析到 `Starsector-098-260mods/mods/...`，报
  `[Critical] asset_outside_root`。这是 `--link` 迁移与 manifest 校验的结构冲突，
  不是 manifest 内容坏了。
- 对真实源安装 `Starsector-098-260mods` 生成到 evidence（rc=0）：
  `L1=6624 L2=18525 L3=55445 baked=80286/80286 unresolved=0`；
  `cross_layer_duplicate=44`（Important，非阻断）；
  `skip=73447`，`skip_v2=73447`，generation 配对。
- 把运行时 `manifest-v1.json`、`lazy-skip-v1.txt`、`lazy-skip-v2.txt`
  复制进实验根；sha256 与源生成一致
  （manifest `e61084a3…`，skip-v1 `f20380f0…`）。
- 证据：`evidence/m7-route-a/manifest-source/generate.log`、
  `evidence/m7-route-a/install_manifest.txt`（目标根失败输出）。

### 3.3 启动与日志

- 第一次 `java.exe @..\route-a.vmparams`：进程存活，但只到启动器设置窗口
  （分辨率/全屏/声音），没有主菜单；325 s 超时后按 PID 结束。
  截图：`evidence/m7-route-a/window-route-a.png`。
- 第二次注入 `-DlaunchDirect=true`：游戏 JVM 启动 6 s 后退出。
- `mixinlib.log`：
  - `integration=MixinFR+FastRendering phase=fr configEnabled=true frPresent=true`
  - `FR game JVM prepared version=v0.9.5`
  - `Handoff - game JVM started pid=... enabledMods=259 jars=231`
- `starsector.log`：`Java version: 17.0.10 (64-bit)`；MixinFR 的
  `effective game JVM command` 也指向随包 `jre\bin\java.exe`。
- `saves/hypernova/scripts-agent.log`：
  - `hypernova agent premain; config=ScriptCacheConfig[...]`
  - `lazy: unsupported FR version 0.9.5; lazy textures disabled`（A 的已知限制）
  - `file index: unsupported FR version 0.9.5; disabled`
  - `scripts cache transformer registered`
- **阻断点**（`mixinlib.log` 第 17-22 行）：
  ```
  GameBootstrap - fatal game startup failure
  java.io.IOException: Missing enabled mod jar:
    ...\mods\迷失武器包\jars\missp_varunastra.jar
    at MixinLib.bootstrap.LaunchSnapshot.validateFiles(LaunchSnapshot.java:103)
  ```
  该 mod 的 `mod_info.json` 声明 `"jars": ["jars/missp_varunastra.jar"]`，
  但包内既无 `jars/` 目录也无该 jar；MixinFR 的 LaunchSnapshot 与游戏
  FileLoader 不同，选择 fail-closed。
- **主菜单未到达**。
- 五类纹理错误：`m6_log_audit` 对 `starsector.log` + `scripts-agent.log`
  结果 `total=0, ok=true, complete=true`。
- 证据目录：`evidence/m7-route-a/`（`starsector.log`、`mixinlib.log`、
  `mixinlib-launcher-stdio.log`、`mixinlib-game-stdio.log`、
  `scripts-agent.log`、`route-a.vmparams`、`launch-route-a.bat`、
  `m6-log-audit.json`、截图）。

### 3.4 no-Hypernova 对照

- 从 `route-a.vmparams` 仅移除
  `-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar`，
  生成 `route-a-control.vmparams` 并启动。
- 结果：5 s 后启动器进程退出，游戏 JVM 报**完全相同**的
  `Missing enabled mod jar: ...missp_varunastra.jar`。
- 结论：路线 A 的阻断与 Hypernova agent 无关，是 mod 包缺 jar + MixinFR
  严格校验。
- 证据：`evidence/m7-route-a/control-no-hypernova/mixinlib.log`、
  `route-a-control.vmparams`。

### 3.5 回滚

- label：`m7-route-a-20261104-005534-097705`。
- `rollback --apply`：`restored=1 deleted=2 ok=true`。
- 但工具只删除了 `route-a.vmparams` 和 `launch-route-a.bat`；
  `mods/MixinFR`、`mods/StarsectorParallel`、`mods/hypernova_infinite_engine`、
  `starsector-core/graphics/hypernova/blank.png` 仍存在。原因是回滚清单里这些
  路径被写成了重复前缀（见 7.3），工具按错误路径找不到目标。
  已按回滚清单的 `existed_before=false` 语义手工删除这些目标路径；
  未触碰 `Starsector-098-260mods`。

## 4. 路线 B 自动化证据

### 4.1 安装

- dry-run：`copies=15`，`intended_java.version=28`，
  `intended_java.runtime=28-beta+13-ea`，`enabled_mods.state=ok`，
  `enabled_mods.add=hypernova_infinite_engine`，warnings=1（固定说明）。
- apply（使用**绝对** `--root`，规避相对路径回滚 bug）：
  - `applied=true`，`ok=false`；
  - `generated=2`，`copied=15`，`agent_rc=0`；
  - `enabled_mods.count=257`，加入 `hypernova_infinite_engine`；
  - `manifest.ok=false`，Critical 77356 条 `asset_outside_root`（同一 junction 限制）；
  - `root_vmparams_modified=false`；
  - rollback label：`m7-route-b-20261104-011738-834506`。
- `jdk-28+13/bin/java.exe -version`：
  `openjdk version "28-beta"`，`Temurin-28+13-202608271655`，
  `28-beta+13-ea`。
- `starsector-core/fr.version.txt`：`v0.9.7rc2`。
- agent 顺序：`hypernova.agent.jar` → `fr.agent.jar`；
  `fr.jar` 在 classpath 首位；argfile 首 token 是 JVM 参数（token-less）。
- manifest 同样用源安装生成的运行时文件补入（sha256 与 A 相同）。

### 4.2 Java 28 参数与启动环境修复

路线 B 继承的是随包 JRE 17 的 vmparams，Java 28 逐项拒绝。实测**必须移除**：

```
-noverify
-XX:+UseXMMForArrayCopy
-XX:+ParallelRefProcEnabled
-XX:+AlwaysAtomicAccesses
-XX:+UseVectorStubs
-XX:ShenandoahGCMode=iu
```

另外 `--enable-preview` 在 Java 28 会激活 Valhalla identity 规则，导致
`Seafood Shipworks` 的 `SF_DancingStats.<clinit>` 抛
`java.lang.IdentityException: java.lang.Integer is not an identity class`；
该运行已保存。移除 `--enable-preview` 后该失败消失。

还遇到并修复了两个环境缺口：

1. **`mods/DDSCache` 不存在** → FR 0.9.7rc2 `DDSIntegration` 在
   `ResourceLoaderState.init` 抛 `NoSuchFileException: ..\mods\DDSCache`，
   弹出 Fatal 对话框。创建空目录后继续。
2. **LunaLib 设置被写成 257 份相同内容** → 目标
   `saves/common/LunaSettings/*.json.data` 全部是 1521 B、同一 md5
   （内容是 `agc_*`），导致 `IndEvo_InitSYCustomProductionDiag.<clinit>`
   的 `LunaSettings.getInt(...)` 返回 null。把源 260mods 的 75 份真实设置
   复制回目标后，该 NPE 消失。

### 4.3 最终运行（修复后）

- 启动：`jdk-28+13\bin\java.exe -DlaunchDirect=true -DstartRes=1707x1067
  -DstartFS=false -DstartSound=true @..\route-b.vmparams`。
- 启动日志确认：
  - `Fast Rendering: v0.9.7rc2`
  - `Java version: 28-beta (64-bit)`
- Hypernova agent（`saves/hypernova/scripts-agent.log`）：
  - `file index transformer registered`
  - `hypernova agent premain; config=ScriptCacheConfig[...]`
  - `lazy: transformers registered`
  - `textures normal-cache transformer registered`
  - `scripts cache transformer registered`
  - `file index: loaded mod_entries=223552, total_entries=235483, dirs=17396, bytes=3380079`
  - lazy probe：`queue=52604 wouldSkip=45785 ... hits>0 misses=0 failed=0 disabled=0`，
    `dds=1`、`ddsFallback` 持续增加（DDS 未命中回退，不是纹理错误）。
- 运行到 **325 s** 时：进程仍存活、Responding、窗口标题
  `Starsector 0.98a-RC8`，画面为加载进度条（截图
  `evidence/m7-route-b/window-route-b-timeout.png`），未出现主菜单锚点。
- **主菜单未到达（300 s 协议超时）**。按 PID 结束。
- 五类纹理错误：`m6_log_audit` 对最终 `starsector.log` + `scripts-agent.log`
  结果 `total=0, ok=true, complete=true`。
- 说明：最终运行的 `starsector.log` 在超过大小后轮转，evidence 里的副本从
  191 s 开始；Java 28 / FR 0.9.7rc2 的启动行保存在同一套配置的前三次运行
  （`run-dds-missing/`、`run-indevo-npe/`、`run-identity-exception/`），
  以及最终运行轮转前的实时轮询输出。

### 4.4 回滚

- label：`m7-route-b-20261104-011738-834506`。
- `rollback --apply`（绝对 root）：`restored=2 deleted=19 ok=true`。
- 恢复/删除覆盖：`enabled_mods.json`、`route-b.vmparams`、`launch-route-b.bat`
  （恢复到 apply 前内容）、`jdk-28+13`、`starsector-core/fr.*`、
  `mods/hypernova_infinite_engine`、`blank.png`、`fr.vmparams.bak-hypernova`。
- 手工清理（回滚清单未覆盖的环境项）：`mods/DDSCache`、
  `saves/common`、`saves/hypernova`、`fr-resource-cache`、
  `starsector-core/cache`、`mixinlib-launch`、运行日志与字体/FR 缓存。

## 5. 用户实机 gate（全部 pending）

| # | 场景 | 结果 |
|---|---|---|
| 1 | 主菜单（启动后停留 30 s） | **pending**；A 未到达，B 300 s 超时未到达 |
| 2 | 战役（新开/载入，进星系/市场） | pending |
| 3 | 战斗（小规模） | pending |
| 4 | 读档/存档 | pending |
| 5 | 分辨率/全屏/alt-tab | pending |
| 6 | 中文输入（改名/搜索/对话） | pending |
| 7 | 字体视觉（LunaLib/市场/对话/舰船） | pending |
| 8 | 稳定性（20–30 分钟） | pending |

**本轮没有任何一项可以标通过。** 菜单都未到达，不能据此推断战役、战斗、
读档、中文输入或字体视觉正常。

## 6. 失败归因

### 6.1 路线 A

- **直接原因**：`mods/迷失武器包/mod_info.json` 声明
  `jars/missp_varunastra.jar`，但该 mod 包内没有 `jars/` 目录和 jar；
  MixinFR 1.2.5 的 `GameBootstrap`/`LaunchSnapshot` 对所有启用 mod 的
  声明 jar 做存在性校验并 fail-closed。
- **no-Hypernova 对照**：移除 Hypernova agent 后同样失败，排除 Hypernova。
- **JRE 17**：`java -version` 与实际启动均为 Zulu 17.0.10；不是 Java 版本问题。
- **manifest 缺失**：本次用源安装生成的运行时 manifest 补入；它不是 A 失败的原因
  （失败发生在此之前），但说明 junction 迁移与 manifest 校验不兼容。
- **建议**：修 mod 包（补 `missp_varunastra.jar` 或从 `mod_info.json` 移除该
  声明），或在路线 A 启用前对声明 jar 做预检并给出可读错误。

### 6.2 路线 B

- 早期失败均为工具/环境，不是 Hypernova：
  1. Java 28 拒绝 JRE 17 参数（`-noverify` 等 6 项）——**M7 工具 bug**；
  2. 缺 `mods/DDSCache`——FR 运行环境未由 M7 创建；
  3. LunaLib 把 257 个设置文件写成同一份 `agc_*` 内容——运行环境/并发问题，
     用源安装设置绕过；
  4. `--enable-preview` 在 Java 28 触发 `IdentityException`——**M7 工具 bug**
     （继承了 Java 17 参数）。
- 修复后最终运行**无 Fatal**，Hypernova agent、lazy、file index、scripts cache
  全部注册，五类纹理错误 0；仅因 300 s 内未到主菜单而记为 timeout。
- 由于最终运行不是失败而是超时，本轮**没有**为 B 再做 no-Hypernova 对照；
  若需要严格归因，可在同一环境下移除 Hypernova agent 重跑并比较加载耗时。
- 优化测试版 + plain FR 是 21835 明确警告的实验组合；B 的超时/加载慢可能与
  该组合有关，本轮不能区分。

## 7. 默认值与回滚

### 7.1 默认值

- M7 两条路线都**默认 off**：不改根 `vmparams`，不自动启用任何路线组件；
  必须显式 `route-a` / `route-b` 和显式 `launch-route-*.bat`。
- 本轮没有把路线 A/B 的 argfile 或启动器写入默认启动链。
- 根 `vmparams` 全程保持
  `8f88ab530c3e989ca027f4aff320a49d8115cab281cd2e592bf9b57c83a29fee`。
- 最终场景：`mods/` 258 项（256 junction + `ChineseInputFix` +
  `enabled_mods.json`），`enabled_mods.json=256`，无 `MixinFR` /
  `StarsectorParallel` / `hypernova_infinite_engine` / `jdk-28+13` /
  `route-*.vmparams` 残留；`launch-route-a.bat` 已删除，
  `launch-route-b.bat` 恢复到 apply 前内容。

### 7.2 回滚结果

| 路线 | label | 工具结果 | 备注 |
|---|---|---|---|
| A | `m7-route-a-20261104-005534-097705` | `restored=1 deleted=2 ok=true` | 工具漏删 3 个 mod 目录和 `blank.png`；已按 `existed_before=false` 手工清理 |
| B | `m7-route-b-20261104-011738-834506` | `restored=2 deleted=19 ok=true` | 使用绝对 `--root`，路径正确；环境项手工清理 |

### 7.3 发现的工具问题

1. **junction × manifest**：`validate_manifest._inside_root()` 用
   `Path.resolve()`，junction 目标被解析到实验根外，导致
   `asset_outside_root` Critical 和 `install_manifest rc=1`。
   `migrate --link` 与 manifest 生成目前不兼容；要么 manifest 生成放宽
   junction，要么迁移时对需要 manifest 的安装改用复制。
2. **relative `--root` 回滚路径重复**：`plan_route_a/b` 的
   `rollback_paths` 里既有相对 `vmparams`，也有
   `str(base / HYPERNOVA_MOD_REL)`；当 `base` 是相对路径时，
   `_snapshot_paths` 又把它拼到 resolved root 后面，产生
   `<root>\<root>\mods\...`。结果是 A 的回滚清单漏删目标。
   **规避**：调用 `route-b` / `rollback` 时传绝对 `--root`；
   根治应在 `_snapshot_paths` 或 `plan_route_*` 统一成绝对路径。
3. **路线 B 继承 Java 17 参数**：`route-b.vmparams` 从根 `vmparams`
   复制了 `-noverify`、`-XX:ShenandoahGCMode=iu` 等；Java 28 直接拒绝。
   需要按目标 JDK 过滤已知不兼容参数（以及 `--enable-preview`）。
4. **环境缺口未预检**：`mods/DDSCache`、LunaLib 设置目录/内容未由 M7 创建或校验；
   FR/LunaLib 会以 Fatal 或 NPE 形式失败。

## 8. 限制

- **不是菜单通过**：A 被 MixinFR 的 mod-jar 校验阻断；B 在 300 s 内停在加载
  进度条。没有战役、战斗、读档、中文输入、字体视觉或稳定性证据。
- **没有收益结论**：本轮不比较帧率、显存、启动时间或 A→B/stutter；不宣称
  Hypernova 的 lazy/DDS/eviction 有任何收益。B 的 lazy 已注册且有
  `misses=0`、`failed=0`，但这只是加载期健康指标，不等于玩法收益。
- **manifest 是跨安装生成**：因 junction 校验失败，运行时 manifest/skip 由
  `Starsector-098-260mods` 生成后复制；它与目标 256 mod 集合一致，但没有在
  目标根通过 `install_manifest.py` 的就地校验。
- **B 的最终日志轮转**：最终 `starsector.log` 副本从 191 s 开始；Java 28 /
  FR 版本行来自同一配置的前三次运行和轮转前轮询。完整最终启动段可能已随
  `starsector.log.1` 被清理，未纳入 evidence。
- **优化测试版 + plain FR**：21835 明确不建议；本轮 B 在该组合上是实验，
  超时不能归因于单一组件。
- **Java 28 参数/LunaLib 修复是本地实验性绕过**：不是 M7 工具已经支持的
  默认行为；玩家复现时仍可能遇到同样的 JVM 参数拒绝和 LunaLib 设置问题。
- **第三方合规**：本轮不重新分发任何第三方文件；所有组件来自用户已有的
  260mods/vendor/缓存目录。
