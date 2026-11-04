# M7 玩家教程：路线 A / A+ / B / B+

> 适用：Starsector **0.98a-RC8**（Windows），远星汉化**优化测试版
> v2026.10.15**。其他版本 / 其他汉化包不要照抄。
>
> **验证状态（先看这一行）**：M7 的 Task 1–7 已完成工具、测试和实机验证。
> **最终结论：B 是 256 全量主推路线**——完整 Mikihime JDK28 47 项 + 8G/10G
> + FR 0.9.7rc2 + VOpt + Hypernova + CIF + Prepatcher；**热缓存
> 68.2 / 57.1 / 59.2 s（中位 59.2 s）**，冷缓存（首次或改组件后）
> **465 s**。**A（MixinFR）256 全量不可用**：1400 s 未到主菜单；单变量
> 对照把慢因定位到 **MixinFR**（Java 17 / FR 0.9.5 / Parallel / Prepatcher
> 均已排除，见 `docs/m7-isolation.md`）；A 只适合小/中 mod 集
> （12-mod 子集 15.6 s）。用户实机 gate（战役、战斗、读档、中文输入、
> 字体视觉、稳定性）仍 **pending**；菜单到达不是整套通过。本教程写
> “应该看到 / 预期”的地方是实测日志或结构证据，不是用户视觉验收。
>
> 本教程不重新分发任何第三方文件。所有组件请从作者官方来源下载；论坛附件
> 需要登录，不要用来路不明的网盘转载包。

---

## 0. 一分钟选路线

M7 提供两套**严格隔离**的路线。它们不能装在同一个安装目录里，也不能混装
组件。

| 你的首要目标 | 选 | 理由 |
|---|---|---|
| **256 全量 mod、要能进游戏** | **B（主推）** | 完整 Mikihime JDK28 47 项 + 8G/10G + CIF + Prepatcher；热缓存 **59.2 s**（中位），冷缓存 **465 s**。A 的 256 全量 1400 s 未到菜单，不可用 |
| 想要**逻辑多线程**（战斗 AI、市场推进等） | **A（仅小/中 mod 集）** | StarsectorParallel 0.1.0 依赖 MixinLib，只有 A 有；但 C1 `CombatAiHotspotMixin` 在 FR 0.9.5 下 `NOT-INJECTED`，且 A 的 256 全量不可用 |
| 保留汉化优化测试版的**高清字体**和 **MixinFRImeFix** | **A（仅小/中 mod 集）** | MixinFR 1.2.5 明确支持 2026.10.15，并带 `MixinFRImeFix.jar`；256 全量不可用，见 0.1 |
| 不想另装 JDK，用游戏自带 JRE 17 | **A（仅小/中 mod 集）** | A 固定 JRE 17 |
| 想要 **Java 28** / 21835 那套稳定组件组合 | **B** | B = FR 0.9.7rc2 + `jdk-28+13` |
| 想要 **Hypernova 完整纹理链**（lazy / DDS / file-index） | **B** | Hypernova 只支持 FR 0.9.7rc2 / 0.9.7；A 的 MixinFR 内置 FR 0.9.5，这些功能会被版本门禁关闭 |
| 想试 **StarsectorPrepatcher** | **B（已纳入最终组合，仍属实验）** | 0.18.4 未声明 Java 28；A 明确不支持 Prepatcher |
| 只想照 21835 的稳定栈走 | **B**（建议配传统汉化 / 非优化版） | 21835 明确说优化测试版自带启动加速，和 plain FR 会打架；M7 在优化测试根上跑 B 属于实验 |

**一句话取舍**：**256 全量只有 B 可用**；A（MixinFR）只适合小/中 mod 集
（12-mod 子集 15.6 s），且 Parallel 的 C1 热点 mixin 在 FR 0.9.5 下
`NOT-INJECTED`。要高清字体 / MixinFRImeFix 且 mod 集不大时才选 A；其余
情况选 B。

### 0.1 A+ / B+（最终组合）

A+ / B+ 不是新的混装路线，而是把 A/B 的组件补齐后的最终形态。**B+ 就是
主推的 B 配置**；A+ 只适合小/中 mod 集。

| 路线 | 最终组件 | 实测结果 |
|---|---|---|
| **A+（JRE 17 / MixinFR）** | MixinFR 1.2.5（含 MixinFRImeFix）+ FR 0.9.5 + StarsectorParallel 0.1.0 + VramOpt 1.0.45 + Hypernova 0.1.0 + Mikihime JRE17 兼容参数（16 项）；Prepatcher 排除 | **256 全量 1400 s 未到主菜单**（已进入纹理加载）；**12-mod 子集 15.6 s**；无 Fatal/OOM；Parallel 的 `CombatAiHotspotMixin` 实测 `NOT-INJECTED`（FR 重写 `CombatEngine`）。**只适合小/中 mod 集。** |
| **B+（B 主推配置）** | FR 0.9.7rc2 + Temurin 28-beta+13 + VramOpt 1.0.45 + Hypernova 0.1.0 + **完整 Mikihime JDK28 47 项（8G/10G）** + **ChineseInputFix（启用）** + **StarsectorPrepatcher 0.18.4**；不装 Parallel/MixinFR | **热缓存 68.2 / 57.1 / 59.2 s（中位 59.2 s）**；**冷缓存 465 s**（同组件冷跑参考，冷法线缓存；完整 Mikihime 未单独重复冷跑）；Prepatcher 冷跑 `16 classes / 21 patches / 4 skipped`、热跑 `12/17/4`；CIF v2.2 加载并子类化窗口；纹理错误 0。 |

**Mikihime 限制（重要）**：`mikihime/configurator/shared/
java-versions.properties` 只有 **Jdk27/Jdk28**，**没有 JRE17**；
`Miko_Lite.txt` 是 Mikihime 的 JDK28 参数（8G/10G）。因此：

- A+ 不能直接套用 Mikihime 配置器；只能从 `Miko_Lite.txt` 挑选 JRE17
  可接受的通用 `-XX`/内存项。实测采用 16 项，JRE17 拒绝 4 项
  （`UseCompactObjectHeaders`、`HotCodeHeap`、`AlwaysPreTouchStacks`、
  `ErrorLogSecondaryErrorDetails`），另 32 项 Mikihime 路径/classpath
  专属项不采用。
- B+ 使用完整 47 项 JDK28 调优；Mikihime 的 `mikohime/` 运行时路径
  （`-Djava.library.path=..\mikohime/windows`、`-Dlog4j.configuration`、
  `-XX:CompilerDirectivesFile` 等）没有复制，保留游戏源 `native\windows`
  与 classpath。Prepatcher 在 Java 28 仍未声明，属实验项。
- 详细采用/剔除清单见 `docs/m7-results.md` §9.3；B 的冷/热对照见
  `docs/m7-b-debug.md`。

**A 的 256 全量定位**：慢因已定位为 MixinFR，结论已移交上游作者
（GerBeria）；本项目不承担 MixinFR 侧修复，也不把 A 的 256 全量列入
后续里程碑。A 只定位小/中 mod 集；256 全量由 B 承担。

### 0.2 启动入口（`launch-route-*.bat`）

`launch-route-a.bat` / `launch-route-b.bat` **由 apply 生成**（仓库不预置），
放在 `%AUDIT%\scripts\`。它们分别执行：

- A：`..\jre\bin\java.exe @..\route-a.vmparams`（JRE 17）
- B：`..\jdk-28+13\bin\java.exe @..\route-b.vmparams`（Java 28）

```bat
"%AUDIT%\scripts\launch-route-a.bat"
"%AUDIT%\scripts\launch-route-b.bat"
```

**不要用 `starsector.exe` 或 `fr.bat` 启动**：两者硬编码 JRE 17，且不读
`route-*.vmparams`。不要移动 / 重命名 `scripts` 目录；bat 用 `%~dp0` 定位
实验根。重新 apply 会刷新对应 bat；回滚会删除 / 恢复它。

---

## 1. 准备

### 1.1 路径约定

下面用三个变量。**请改成你自己的路径**；示例假设仓库在
`D:\github\Hypernova-Infinite-Engine`，实验根是仓库内的
`SS098_Hypernova_Compat_AuditTest\install\optimized-2026.10.15`。

在 `cmd.exe` 里：

```bat
set REPO=D:\github\Hypernova-Infinite-Engine
set AUDIT=%REPO%\SS098_Hypernova_Compat_AuditTest
set ROOT=%AUDIT%\install\optimized-2026.10.15
cd /d "%REPO%"
```

> 以下命令都在 **cmd.exe** 中执行。PowerShell 请把 `%VAR%` 换成
> `$env:VAR`，或直接写完整路径；不要混用两种展开语法。路径有空格时一定
> 加引号。

### 1.2 预检

先确认 Python 和安装根：

```bat
python --version
python -I tools\m7_stack.py inspect --root "%ROOT%" --text
```

预期看到：

```text
localization.version=2026.10.15
localization.branch=startup-optimization
jre_version=17.0.10
dyn_font=true
ssime_dll=true
mods.enabled_count=0
```

如果你的 `mods.enabled_count` 不是 0，说明这不是干净安装根；先用全新安装
目录，不要覆盖已有整合。

如果 `python` 是 Microsoft Store 的假入口，改用：

```bat
py -3 --version
py -3 -I tools\m7_stack.py inspect --root "%ROOT%" --text
```

### 1.3 安全须知

- **关掉游戏**再操作。
- **不要动 `Starsector-098-260mods`**；M7 只写实验根。
- **A 和 B 推荐各用一个全新安装根**；至少不要同时装在同一根上。如果只有
  一份安装、必须复用，换路线前先回滚（第 7 节）并确认 MixinFR / Parallel
  残留已消失。
- `m7_stack.py` 默认 **dry-run**；只有显式 `--apply` 才写盘。
- 路线 A/B 和 `disable-ime` 的 `--apply` 会先生成 M6 快照和 M7 回滚快照；
  记住输出里的 `rollback.label=...`。`migrate --apply` 不生成
  `route-rollback.json`，它只创建新 target，失败时清理半成品。
- 256 mod 的 `apply` 还要生成 Hypernova manifest，可能停顿几分钟；不要
  中途关窗口。

---

## 2. 下载清单

| 组件 | 版本 | 用途 | 官方来源 | 放到哪里（示例） |
|---|---|---|---|---|
| 远星汉化优化测试版 | 2026.10.15 | 游戏 + 汉化 + JRE 17 + 高清字体 + `ssime.dll` | 汉化包仓库 `https://github.com/TruthOriginem/Starsector-Localization-CN`；发布 / 安装器以远星论坛（fossic）汉化发布帖为准 | 全新安装到 `%ROOT%` |
| MixinFR | **1.2.5** | 路线 A：MixinLib + FR 0.9.5 + IME 修复 | `https://www.fossic.org/thread-21705-1-1.html`（附件需登录） | `%AUDIT%\vendor\MixinFR-1.2.5\MixinFR` |
| StarsectorParallel | **0.1.0** | 路线 A：逻辑多线程 | `https://www.fossic.org/thread-21836-1-1.html`（附件需登录） | `%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel` |
| Fast Rendering | **0.9.7rc2** | 路线 B：FR | `https://github.com/Halke1986/starsector-render` 发布页（21835 与 Prepatcher README 均引用）；具体 rc2 以作者发布页为准 | `%REPO%\.cache\fr097\fast-rendering-0.9.7rc2` |
| Temurin JDK | **28+13-ea-beta** | 路线 B：Java 28 | `https://github.com/adoptium/temurin28-binaries/releases/tag/jdk-28+13-ea-beta` | `%REPO%\Starsector-098-260mods\jdk-28+13` |
| VramOptimizer | **1.0.45**（锁定） | 显存优化；两路线都用 | `https://github.com/DeCEll-1/VramOptimizer/releases/tag/v1.0.45`，文件 `VramOptimizer-win-x64-sc.zip` | 由 256-mod 迁移带入 `%ROOT%\mods\VramOptimizer`；不要升 1.0.46+ |
| Hypernova Infinite Engine | 0.1.0 | 两路线都用（agent + mod） | `https://github.com/f25h-233/Hypernova-Infinite-Engine`（Release 或自行构建） | `%REPO%`（`--hypernova-mod` 指向含 `mod_info.json`、`data/`、`graphics/`、`jars/` 或 `build/` 的目录） |
| ChineseInputFix | 2.0.0 | **B 最终组合（启用）**；IME 备选 | `https://www.fossic.org/thread-20561-1-1.html`（作者 Chesand；260mods 自带 2.0.0） | `%REPO%\Starsector-098-260mods\mods\ChineseInputFix`，或 `disable-ime --cif-source` 指定 |
| Mikihime 配置器 / `Miko_Lite.txt` | JDK28（8G/10G） | B 的完整 JVM 调优参数（47 项） | Mikihime 官方配置器（Jdk28 profile）；本机 `Starsector-098-260mods` 内已有 `Miko_Lite.txt` | `%REPO%\Starsector-098-260mods\Miko_Lite.txt` |
| StarsectorPrepatcher | **0.18.4**（B 最终组合，仍属实验） | 实验性预加载补丁 | `https://github.com/kirpoly/StarsectorPrepatcher`（0.18.4 包内 README / `docs/COMPATIBILITY.md` 指向该仓库） | `%REPO%\.cache\prepatcher\extracted\StarsectorPrepatcher` |

> **Prepatcher 来源更正**：M7 计划文档里写的 `cyrrp/StarsectorPrepatcher`
> 与 0.18.4 包内 README 不一致；包内所有文档都指向
> `kirpoly/StarsectorPrepatcher`。下载时以包内来源为准，不要混用不明 fork。
>
> **版本必须对上**：MixinFR 1.2.5、Parallel 0.1.0、FR 0.9.7rc2、VOpt
> 1.0.45、Prepatcher 0.18.4。低版本 MixinFR 有字体竖条 / DDS 元数据半截
> 等已知问题；VOpt 1.0.46+ 不在 M7 的验证范围内。

---

## 3. 路线 A：MixinFR 1.2.5 + JRE 17 + StarsectorParallel

> **最终判定（2026-11-04）：A 的 256 全量不可用。** 1400 s 预算内仍未到
> 主菜单（已进入纹理加载）；单变量对照把慢因定位到 **MixinFR**
> （见 `docs/m7-isolation.md`）。结论已移交上游作者（GerBeria），本项目
> 不承担 MixinFR 侧修复。A 只适合小/中 mod 集（12-mod 子集 15.6 s）。
> 下面仍保留安装 / 启动步骤，供小/中集或诊断使用；不要把它当作 256 全量
> 方案。

### 3.1 这条路线给你什么

- **仅适合小/中 mod 集**；256 全量 1400 s 未到主菜单，不要用 A 带 256 mod。
- MixinFR：MixinLib + Fast Rendering 0.9.5 一体化；对汉化优化测试版提供
  高清字体重定向和 `MixinFRImeFix.jar`。
- StarsectorParallel 0.1.0：战斗 AI、市场推进等逻辑热点并行；但 C1
  `CombatAiHotspotMixin` 在 FR 0.9.5 下 `NOT-INJECTED`，其余 5 个热点
  日志级 `APPLY`。不要把“组件已装”写成“Parallel 已生效”。
- Hypernova agent 会加载，但 **`lazy` / DDS / file-index 会被 FR 0.9.5
  版本门禁关闭**；`scripts` 缓存和 normal-cache 是否生效以
  `scripts-agent.log` 为准。不要把 A 当成 Hypernova 全功能栈。
- 不支持 Java 28，不支持 Prepatcher。

### 3.2 安装

#### 第 1 步：放组件

确认下面两个目录存在（版本号见 `mod_info.json`）：

```text
%AUDIT%\vendor\MixinFR-1.2.5\MixinFR
%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel
```

`--mixinfr` 指向的源目录可以叫别的名字，但安装后的目标文件夹固定是
`%ROOT%\mods\MixinFR`；Parallel 固定是 `%ROOT%\mods\StarsectorParallel`。
不要手动改这两个目标文件夹名：MixinFR 的 agent 路径和 Parallel 的依赖都
按它们定位。

> 也可以运行 `%AUDIT%\scripts\route-a.bat --apply`。它默认使用上面的
> vendor 路径和 `install\optimized-2026.10.15`，路径不同就用显式命令。
> 这个 bat 只安装 / 切换，**不启动游戏**；启动仍用 `launch-route-a.bat`。

#### 第 2 步：迁移 256 mod

先 dry-run，确认只读：

```bat
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --text
```

预期摘要：

```text
copy=256
enabled=256
excluded=hypernova_infinite_engine
extras=ChineseInputFix
missing_enabled_ids=-
duplicate_ids=lw_console:ConsoleCommands,shaderLib:GraphicsLib,lw_lazylib:LazyLib,particleengine:Particle Engine
```

`duplicate_ids` 是已知的 4 组重复 id 选择（按排序取第一个文件夹），不是
fail-closed 错误，也不影响 `copy=256` / `enabled=256`。

`--link` 用目录联接，省空间但依赖源目录；想长期独立使用就去掉
`--link`，改为完整复制（12 GB，耗时更久）。

> **重要：`migrate --apply` 要求 target 不存在。** 优化版安装器会创建一个
> 空的 `%ROOT%\mods`。如果它是空的，先删掉空目录；如果有内容，不要删，
> 换一个全新安装根。
>
> ```bat
> dir /b "%ROOT%\mods"
> rmdir "%ROOT%\mods"
> ```
>
> 第二条只在确认目录为空后执行。`rmdir` 对非空目录会失败，这是有意的保护。

然后 apply：

```bat
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --apply --text
```

预期：

```text
applied=true
copied=256
extras_copied=1
total_copied=257
enabled=256
```

这会把 256 个启用 mod 和 `ChineseInputFix`（保留但不启用）复制 / 联接过去，
并生成 `%ROOT%\mods\enabled_mods.json`。VramOptimizer 就在这 256 个里。

#### 第 3 步：dry-run 路线 A

> **前置 blocker：必须先完成 `migrate --apply`。** `route-a --apply` 对
> `enabled_mods.json` 的 **missing / 解析错误都 fail-closed**：目标根没有
> `enabled_mods.json` 时，apply 打印 `FATAL` 并返回 1，不会新建只含
> `hypernova_infinite_engine`、`MixinLib`、`starsectorparallel` 的 3 项
> 列表。dry-run 必须看到 `enabled_mods.state=ok` 才能进入第 4 步；
> `state=missing` 就先回第 2 步迁移。

```bat
python -I tools\m7_stack.py route-a --root "%ROOT%" --mixinfr "%AUDIT%\vendor\MixinFR-1.2.5\MixinFR" --parallel "%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel" --hypernova-mod "%REPO%" --text
```

预期关键行：

```text
route=a
java=..\jre\bin\java.exe
jre_version=17.0.10
agents=-javaagent:..\mods\MixinFR\jars\MixinLib-bridge.jar,-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar
root_vmparams_modified=false
copies=8
enabled_mods.state=ok
enabled_mods.add=hypernova_infinite_engine,MixinLib,starsectorparallel
enabled_mods.order=<259 项；末尾为 VramOptimizer,hypernova_infinite_engine,MixinLib,starsectorparallel>
```

`enabled_mods.order` 是完整的 259 项（迁移带入的 256 项 + Hypernova +
MixinLib + starsectorparallel），不是 3 项；只有 `enabled_mods.add` 是
3 项。实际输出是一整行，上面只展示末尾。

`warnings` 在迁移完成后应只剩两类固定说明：Prepatcher 被排除、
`starsector.exe` 硬编码 JRE 17。若还有 `missing source` / `missing agent
jar` / `VramOptimizer not present` / `enabled_mods.state=missing`，先修好
再 apply。

#### 第 4 步：apply 路线 A

```bat
python -I tools\m7_stack.py route-a --root "%ROOT%" --mixinfr "%AUDIT%\vendor\MixinFR-1.2.5\MixinFR" --parallel "%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel" --hypernova-mod "%REPO%" --apply --text
```

预期：

```text
applied=true
ok=true
rollback.label=m7-route-a-...
generated=2
copied=8
root_vmparams_modified=false
```

**把 `rollback.label=` 抄下来。** 以后回滚只用这个 label。

这次 apply 会：

- 写 `%ROOT%\route-a.vmparams`（token-less，首 token 是 `-noverify`，不是
  `java.exe`）。
- 生成 `%AUDIT%\scripts\launch-route-a.bat`。**这个文件是 apply 之后才出现
  的**，仓库里没有预置。
- 复制 MixinFR、StarsectorParallel、Hypernova 到 `%ROOT%\mods`。
- 把 `hypernova_infinite_engine`、`MixinLib`、`starsectorparallel` 追加到
  `enabled_mods.json`，顺序是 Hypernova → MixinLib → Parallel。
- 生成 Hypernova manifest。
- **不改根 `vmparams`**，也**不调用** `install_agent`；agent 只写在
  `route-a.vmparams` 里。

#### 第 5 步：启动

```bat
"%AUDIT%\scripts\launch-route-a.bat"
```

它等价于在 `%ROOT%\starsector-core` 下执行：

```text
..\jre\bin\java.exe @..\route-a.vmparams
```

**不要用 `starsector.exe`。** 它读根 `vmparams`（路线 A 没有改），不会加载
MixinFR / Parallel / Hypernova agent。**也不要运行
`mods\MixinFR\install.bat`**；它会把 MixinLib agent 再写进根 `vmparams`，
制造两套启动配置。路线 A 的 agent 已经写在 `route-a.vmparams` 里。

### 3.3 启动后检查

日志都在 `%ROOT%\starsector-core\`，agent 日志在
`%ROOT%\saves\hypernova\scripts-agent.log`。

| 检查项 | 位置 | 预期 |
|---|---|---|
| 实际 Java | `starsector.log` 开头的 `Java version:` | `17.0.10`（或 17.x） |
| MixinFR + FR | `mixinlib.log` | `[MixinFR] integration=MixinFR+FastRendering phase=fr` |
| 高清字体 | `mixinfr-fonthd.log` | 出现 `REMAP-OK`；连续 `REMAP-SKIP` / “整体未生效” 要查 |
| IME 修复 | `mixinfr-ime-fix.log` | 优化测试版上应有 bridge 相关行；没有这个文件说明没有 IME 类可修 |
| Parallel | `mixinlib.log` / `starsector.log` 搜 `sparallel-` | `CombatAiHotspotMixin` / `MarketHotspotMixin` 被 APPLY；线程名 `sparallel-p*` / `sparallel-e*` / `sparallel-worker` |
| Hypernova agent | `saves\hypernova\scripts-agent.log` | `hypernova agent premain; config=...`；`scripts cache transformer registered` |
| Hypernova lazy | 同上 | 预期会出现 `lazy: unsupported FR version ...; lazy textures disabled`（版本串可能是 `0.9.5` 或 `unknown`）。**这是 A 的已知限制，不是安装失败** |
| VOpt | `starsector.log` | `VOpt Loaded`；没有 `Failed to initialize VRAM Optimizer` |
| 五类纹理错误 | `starsector.log` | `Failed to load texture`、`VerifyError`、`ClassFormatError`、`AsyncException`、`isStateCorrupted` 均为 0 |

### 3.4 A 的已知限制

- **256 全量不可用**：1400 s 未到主菜单；单变量对照把慢因定位到 MixinFR
  （Java 17 / FR 0.9.5 / Parallel / Prepatcher 均已排除，见
  `docs/m7-isolation.md`）。结论已移交上游作者（GerBeria）；本项目 A
  只定位小/中 mod 集（12-mod 子集 15.6 s），256 全量由 B 承担。不要等
  本项目去修 MixinFR。
- **Hypernova 纹理链不完整**：FR 0.9.5 不在 `FileIndexHook` 的支持列表里，
  `lazy` / DDS / file-index 关闭。`-Dhypernova.textures.lazy=true` 等 token
  在 A 里是无效的，不要为了这条日志反复重装。
- **不支持 Java 28**：MixinFR / Parallel 官方只支持 JRE 17。
- **不支持 Prepatcher**：0.18.4 在 MixinLib 的 `TargetClassLoader` 下
  20/34 目标 `SKIPPED_LOADER`，Java 27+ 还会硬失败。
- **选 A 就不要装 FR 0.9.7**：MixinFR 已内置 FR 0.9.5，双 FR 会冲突。

---

## 4. 路线 B：FR 0.9.7rc2 + Java 28

### 4.1 这条路线给你什么

- Fast Rendering 0.9.7rc2：渲染 / 加载优化。
- Temurin `jdk-28+13`：Java 28。
- **完整 Mikihime JDK28 47 项 + 8G/10G**：`Miko_Lite.txt` 的 JVM 调优。
- **ChineseInputFix 启用**（日志 v2.2）；**Prepatcher 0.18.4**（实验，
  已纳入最终组合）。
- Hypernova 完整组合：M6 已在 260mods（Java 28 + FR 0.9.7rc2 + VOpt
  1.0.45，agent-only）跑过菜单 smoke，`lazy.present=true`、`ddsHit=19`、
  `texture_errors_total=0`。
- 没有 StarsectorParallel（缺 MixinLib），没有 MixinFR 的高清字体 /
  `MixinFRImeFix`。
- **这是 256 全量主推路线**：热缓存 **59.2 s**（中位），冷缓存 **465 s**。

> **和 21835 的关系**：B 的组件组合就是 21835（包子哥 / 3l psi 教程，
> `https://www.fossic.org/thread-21835-1-1.html`）的稳定栈。但 21835 明确说
> “优化测试版汉化别和 plain FR 一起用，它自己已经做了启动加速，二者会
> 打架”。M7 的 B 是在优化测试根上的实验；如果你只要 21835 的稳定形态，
> 请把它装在**传统汉化 / 非优化版**上。最终配置（完整 Mikihime 47 项 +
> CIF + Prepatcher）在优化测试根上热跑 **68.2 / 57.1 / 59.2 s（中位
> 59.2 s）**，冷跑 **465 s**；105.8 s 是历史精简参数 + 热缓存数字。仍按
> 实验记录，用户 gate 尚未验证。

### 4.1.1 先决条件（环境 / 模组，不是 Hypernova 要求）

Task 7 在优化测试根上到达主菜单前，必须补齐下面三条。它们都是环境或
第三方模组的前提，**不是 Hypernova 的要求**，也不由 M7 工具自动完成：

1. **禁用 `jc_sf`（SF-幽灵部队）**：该 mod 自检报“幽灵部队模组文件损坏”，
   会在启动早期 Fatal。先在启动器里取消启用；不要用 M7 改它的文件。
2. **应用 AoTD 的 `starfarer.api.jar` 替换**：AoTD Theory of Toolbox 要求把
   其 `0.98a/starfarer.api.jar` 复制到 `starsector-core/starfarer.api.jar`。
   Task 7 按 260mods 的已知可用配置替换，并在回滚时恢复原 jar（优化测试版
   原 jar 的 sha256 见 `docs/m7-results.md`）。没有这一步会在启动时 NPE。
3. **恢复 LunaLib 设置**：把 260mods 的 `saves/common/LunaSettings` 恢复到
   本次安装根。256 mod 首次启动可能生成一批内容相同的损坏设置，导致
   LunaLib 报错或界面异常。工具只做只读预检，不写用户设置。

缺少任一条都可能 Fatal / NPE；先修好再跑下面的 dry-run / apply。

### 4.2 安装

#### 第 1 步：放组件

确认：

```text
%REPO%\.cache\fr097\fast-rendering-0.9.7rc2
%REPO%\Starsector-098-260mods\jdk-28+13
%REPO%\Starsector-098-260mods\Miko_Lite.txt
```

`jdk-28+13` 的文件夹名建议保持 `jdk-28+13`（21835 也提醒必须以 `jdk-28`
开头）；apply 会把它复制到 `%ROOT%\jdk-28+13`，启动器固定用这个相对路径。

#### 第 2 步：迁移 256 mod

如果是**全新安装根**，按 3.2 的步骤迁移。如果这个根已经迁移过（例如从
路线 A 回滚后复用同一根），`%ROOT%\mods` 里已经有 256 个 mod，**不要重复
迁移**，直接跳到第 3 步。

如果这个安装根已经装过 A，先按第 7 节回滚 A，再装 B；不要在同一根上叠加。

全新根先 dry-run：

```bat
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --text
```

确认 `copy=256`、`enabled=256`、`extras=ChineseInputFix`。确认
`%ROOT%\mods` 为空后删掉它（`rmdir "%ROOT%\mods"`），再 apply：

```bat
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --apply --text
```

`--link` / 完整复制的取舍见 3.2。apply 成功后 `%ROOT%\mods` 会被重新创建，
并写入 `enabled_mods.json`。

> 也可以运行 `%AUDIT%\scripts\route-b.bat --apply`。它默认使用上面的 FR /
> JDK 路径和实验根；只安装 / 切换，**不启动游戏**。启动仍用
> `launch-route-b.bat`。

#### 第 3 步：dry-run 路线 B（最终配置）

```bat
python -I tools\m7_stack.py route-b --root "%ROOT%" --fr-dir "%REPO%\.cache\fr097\fast-rendering-0.9.7rc2" --jdk-dir "%REPO%\Starsector-098-260mods\jdk-28+13" --hypernova-mod "%REPO%" --mikohime-args "%REPO%\Starsector-098-260mods\Miko_Lite.txt" --xms 8G --xmx 10G --enable-cif --prepatcher "%REPO%\.cache\prepatcher\extracted\StarsectorPrepatcher" --text
```

预期关键行（以实际输出为准）：

```text
route=b
intended_java.version=28
intended_java.runtime=28-beta+13-ea
launcher.java=..\jdk-28+13\bin\java.exe
launcher.argfile=..\route-b.vmparams
memory.xms=8G
memory.xmx=10G
memory.source=override
mikihime.adopted=47
cif.verified=true
copies=16
enabled_mods.add=hypernova_infinite_engine,starsector_prepatcher,ChineseInputFix
root_vmparams_modified=false
```

`copies=16` 是 8 个 FR 文件 + jdk 树 + Hypernova 6 项 + Prepatcher；
ChineseInputFix 若迁移时已带入则不重复复制。去掉 `--prepatcher` 或
`--enable-cif` 后数字会变；这两个是最终 B 配置的一部分。

#### 第 4 步：apply 路线 B（最终配置）

```bat
python -I tools\m7_stack.py route-b --root "%ROOT%" --fr-dir "%REPO%\.cache\fr097\fast-rendering-0.9.7rc2" --jdk-dir "%REPO%\Starsector-098-260mods\jdk-28+13" --hypernova-mod "%REPO%" --mikohime-args "%REPO%\Starsector-098-260mods\Miko_Lite.txt" --xms 8G --xmx 10G --enable-cif --prepatcher "%REPO%\.cache\prepatcher\extracted\StarsectorPrepatcher" --apply --text
```

预期 `applied=true`、`ok=true`、`rollback.label=m7-route-b-...`。抄下 label。

如果只想先跑最小 B（不装 Prepatcher/CIF），去掉 `--prepatcher ...` 和
`--enable-cif`；但最终推荐配置包含它们。Prepatcher 在 Java 28 仍未声明，
异常时先去掉它重装。

这次 apply 会：

- 写 `%ROOT%\route-b.vmparams`（token-less，首 token 是
  `-XX:+UnlockDiagnosticVMOptions`；不是 `-noverify`，`-noverify` 只适用于 A）。
- 生成 / 刷新 `%AUDIT%\scripts\launch-route-b.bat`。
- 把 FR 文件复制到 `%ROOT%\starsector-core`，把 `jdk-28+13` 复制到
  `%ROOT%\jdk-28+13`，把 Hypernova 复制到 `%ROOT%\mods`。
- agent 顺序：Hypernova → FR → Prepatcher；都在 `-classpath` 和主类之前。
- 把 `hypernova_infinite_engine`、`starsector_prepatcher`（以及启用时的
  `ChineseInputFix`）加入 `enabled_mods.json`。
- 应用完整 Mikihime JDK28 47 项，内存统一为 `-Xms8G -Xmx10G`。
- 生成 Hypernova manifest；并调用 `install_agent` 给
  `starsector-core\fr.vmparams`（FR 的 JRE 17 回退启动文件）注入 Hypernova
  agent，备份为 `fr.vmparams.bak-hypernova`。
- **不改根 `vmparams`**；`starsector.exe` 仍跑 JRE 17，只是回退 / 对照。

#### 第 5 步：启动

```bat
"%AUDIT%\scripts\launch-route-b.bat"
```

它等价于在 `%ROOT%\starsector-core` 下执行：

```text
..\jdk-28+13\bin\java.exe @..\route-b.vmparams
```

**不要用 `starsector.exe`，也不要用 `fr.bat`。** 两者都硬编码
`..\jre\bin\java.exe`（JRE 17），不是路线 B 的入口。

### 4.3 启动后检查

| 检查项 | 位置 | 预期 |
|---|---|---|
| 实际 Java | `starsector.log` 开头的 `Java version:` | `28-beta (64-bit)`（M6 的实机行就是这个格式） |
| JDK 版本 | `%ROOT%\jdk-28+13\release` 或 `jdk-28+13\bin\java.exe -version` | `JAVA_VERSION="28"` / `Temurin-28+13` |
| FR | `starsector-core\fr.version.txt` | `v0.9.7rc2` |
| FR agent | `starsector.log` 开头 | `com.genir.renderer.agent.Agent - Fast Rendering: v0.9.7rc2`；没有 agent 缺失错误 |
| Hypernova agent | `saves\hypernova\scripts-agent.log` | `hypernova agent premain`；`lazy: transformers registered`；`file index transformer registered` |
| VOpt | `starsector.log` | `VOpt Loaded`、`Suitable FR Version found`；没有 `Failed to initialize VRAM Optimizer` |
| 五类纹理错误 | `starsector.log` | 全部为 0 |
| Prepatcher | `starsector-core\logs\prepatcher.log` | 最终配置包含 0.18.4；冷跑 `16 classes / 21 patches / 4 skipped`、热跑 `12/17/4`；没有大量 `SKIPPED_LOADER`。Java 28 未声明，异常就退回无 Prepatcher |

### 4.4 B 的已知限制

- **没有 Parallel**：StarsectorParallel 依赖 MixinLib；B 不装 MixinFR。
- **没有 HD 字体重定向**：plain FR 不认优化测试版的矢量字体路径；字体
  可能回到传统位图（上游 21705 的说明）。要高清字体选 A（仅小/中集）。
- **没有 MixinFRImeFix**：中文输入用已启用的 ChineseInputFix。
- **冷 / 热缓存**：改组件会改变 enabled 集合 → Hypernova 脚本 / 法线缓存
  key 变化 → 首次启动按冷跑算（约 300–500 s，同组件冷跑参考 465 s）；热跑
  才是 57–68 s。不要拿一次冷启动判断“B 很慢”。
- **优化测试版 + plain FR 有冲突报告**：21835 明确不建议；M7 的 B 在优化
  测试根上是实验。最终配置热跑 59.2 s（中位），但用户 gate 仍 pending。
- **Prepatcher Java 28 未声明**：最终配置包含 0.18.4，但仍是实验项，可能
  部分 patch 失败；异常时先去掉 Prepatcher 跑通，再加。
- **B 是 256 全量唯一可用路线**：A 的 256 全量 1400 s 未到菜单，慢因已
  定位为 MixinFR 并移交上游（GerBeria）；本项目不承担该修复。

---

## 5. 汉化短路

### 5.1 字体模糊 / 文字压成竖条

1. **先确认是 MixinFR 1.2.5**：
   ```bat
   findstr /i "version" "%ROOT%\mods\MixinFR\mod_info.json"
   ```
   应该是 `"version": "1.2.5"`。1.2.4 修了高清字体重定向，1.2.5 修了
   “部分界面文字被压成竖条”（LazyLib `LazyFont` 的 fnt / 图集不同源）。
2. 看 `%ROOT%\starsector-core\mixinfr-fonthd.log`：有 `REMAP-OK` 说明
   重定向命中；连续 `REMAP-SKIP` 或 `[FONT-HD] ★ 字体重定向整体未生效`
   说明没生效。
3. `disable-mixinfr-fonts` **在 1.2.5 上只是诊断，不是开关**：
   ```bat
   python -I tools\m7_stack.py disable-mixinfr-fonts --root "%ROOT%" --text
   ```
   1.2.5 没有独立的 `FrFontHd` 配置开关，工具会报 `switch_available=false`、
   `writes=0`。不要指望它把字体改回模糊版。
4. 如果确认 1.2.5 仍然竖条：把 `mixinlib.log`、`mixinfr-fonthd.log`、
   `starsector.log`、`vmparams` 一起反馈给 MixinFR 作者。临时改用路线 B
   （装在传统汉化 / 非优化版上）可以绕开 MixinFR，但会失去高清字体和 IME
   修复；在优化测试版上 B 仍是实验。

### 5.2 中文输入冲突

优化测试版自带 `ssime.dll`。MixinFR 1.2.5 用 `MixinFRImeFix.jar` 把 IME
原生调用桥到窗口线程；如果候选框仍停在屏幕左上角、选词无反应：

1. 看 `%ROOT%\starsector-core\mixinfr-ime-fix.log` 是否有 bridge 行。
2. 还不行就短路成 ChineseInputFix。先 dry-run：
   ```bat
   python -I tools\m7_stack.py disable-ime --root "%ROOT%" --text
   ```
   预期 `dll_present=true`、`rename=ssime.dll->ssime.dll.disabled`、
   `cif.verified=true`、`enabled_mods.state=ok`。
3. apply：
   ```bat
   python -I tools\m7_stack.py disable-ime --root "%ROOT%" --apply --text
   ```
   预期 `applied=true`、`changed=true`、`renamed=1`、`copied_cif=true`、
   `enabled_mods.add=ChineseInputFix`、`rollback.label=m7-disable-ime-...`。
   它会把 `ssime.dll` 改名成 `ssime.dll.disabled`，复制 / 启用
   ChineseInputFix；失败会自动回滚。
4. 回滚 IME 短路：
   ```bat
   python -I tools\m7_stack.py rollback --root "%ROOT%" --label m7-disable-ime-... --apply --text
   ```
5. **一次只留一条输入路径**：用了 ChineseInputFix 就不要再去修
   `ssime.dll`；反之亦然。CIF 的默认源是
   `Starsector-098-260mods\mods\ChineseInputFix`，不在默认位置时用
   `--cif-source` 指定。

### 5.3 热启动冲突（优化测试版 vs FR）

- 优化测试版汉化自带启动加速；plain FR 也做启动 / 加载优化，21835 明确
  说两者会打架。
- 想保留优化测试版：用 **路线 A（仅小/中 mod 集）**（MixinFR 明确支持
  2026.10.15，它把 MixinLib + FR 整合成一套）。A 的 256 全量不可用。
- 想走 21835 稳定栈：用 **路线 B**，但装在传统汉化 / 非优化版上；M7 在
  优化测试根上的 B 热跑 59.2 s（中位）、冷跑 465 s，仍属实验，用户 gate
  pending。
- 优化测试版目前没有“一键关闭启动加速”的用户开关。
  `localization_version.json` 只标记 `branch=startup-optimization`；
  `settings.json` 的 `enableScriptCaching=false` 是另一项设置（当前关闭），
  不是关闭启动加速的开关。不要手改 `settings.json` 去猜。

---

## 6. 实机验证

Task 7 已跑：**B（最终配置）热跑 68.2 / 57.1 / 59.2 s（中位 59.2 s），
冷跑 465 s**；**A 的 256 全量 1400 s 未到菜单**（慢因 MixinFR，已移交
上游；A 仅小/中集可用）。下面每一项（战役 / 战斗 / 读档 / 中文输入 /
字体视觉 / 稳定性）仍默认 `待验证`，用户 gate pending。请按场景逐项记录，
**不要用菜单 smoke 代替整套验收**。

### 6.1 场景清单

| # | 场景 | 怎么测 | 通过条件 | 结果 |
|---|---|---|---|---|
| 1 | 主菜单 | 启动到主菜单，停留 30 秒 | 不崩、不黑屏、无五类纹理错误 | 待验证 |
| 2 | 战役 | 新开或载入战役，进一个星系 / 市场 | 不崩、无缺字 / 豆腐块、UI 不竖条 | 待验证 |
| 3 | 战斗 | 打一场小规模战斗 | 不崩、无纹理错误、Parallel（A）线程出现 | 待验证 |
| 4 | 读档 / 存档 | 存一次、退回主菜单、再读档 | 读档成功、不崩、无纹理错误 | 待验证 |
| 5 | 分辨率 / 全屏 / alt-tab | 切窗口 / 全屏 / alt-tab 再回来 | 不崩、可继续操作 | 待验证 |
| 6 | 中文输入 | 改名、搜索、对话输入各至少 2 个中文字 | 候选框跟随文本框、选词成功、不崩 | 待验证 |
| 7 | 字体视觉 | 打开 LunaLib 配置入口、市场 / 对话 / 舰船界面 | 文字清晰，无竖条、无错位、无缺字 | 待验证 |
| 8 | 稳定性 | 连续玩 20–30 分钟，切几个场景 | 无新异常、无 OOM、无纹理错误增长 | 待验证 |

### 6.2 用 `m6_session` 记录

每个场景一对 `start` / `end`。先 `start`，再启动游戏，退出后 `end`：

```bat
python -I tools\m6_session.py start --game-root "%ROOT%" --evidence-root "%AUDIT%" --label m7a-menu
python -I tools\m6_session.py end --game-root "%ROOT%" --evidence-root "%AUDIT%" --label m7a-menu
```

路线 B 把 label 换成 `m7b-...`；其他场景用 `m7a-campaign`、`m7a-combat`、
`m7a-load`、`m7a-resolution`、`m7a-ime`、`m7a-font` 等。产物在
`%AUDIT%\<label>\session.json`。

预期 `session.json` 里：

- `ok=true`
- `texture_errors_total=0`
- `log_audit.complete=true`
- `log_audit.total=0`

### 6.3 日志审计与收集

```bat
python -I tools\m6_log_audit.py --game-root "%ROOT%" --out "%AUDIT%\evidence\m7-log-audit.json" --text
python -I tools\m7_stack.py collect-logs --root "%ROOT%" --out "%AUDIT%\evidence\m7-logs" --text
```

`collect-logs` 会复制存在的 `starsector.log`、`mixinlib.log`、
`mixinfr-fonthd.log`、`scripts-agent.log`；`missing=` 里列出的就是没找到的
日志。

### 6.4 判定口径

- 菜单能进 ≠ 战役 / 战斗 / 读档 / 输入 / 字体通过。
- `texture_errors_total=0` 和 `log_audit.total=0` 是自动化健康指标，不等于
  肉眼字体 / UI 正常。
- 任何一项失败，先保留 `session.json` + 日志 + `vmparams`，再回滚对应 label；
  不要把失败环境继续叠加下一套路线。

---

## 7. 回滚

### 7.1 找到 label

`route-a --apply` / `route-b --apply` 输出里的 `rollback.label=`，或：

```bat
dir /b "%AUDIT%\backups"
```

M7 的 label 形如 `m7-route-a-YYYYMMDD-...`、`m7-route-b-...`、
`m7-disable-ime-...`。只有带 `route-rollback.json` 的 M7 快照能用于
`rollback`；M6 的 `baseline-...` 快照没有这个清单，工具会报
`missing route rollback manifest`。

### 7.2 先 dry-run，再 apply

```bat
python -I tools\m7_stack.py rollback --root "%ROOT%" --label m7-route-a-... --text
python -I tools\m7_stack.py rollback --root "%ROOT%" --label m7-route-a-... --apply --text
```

预期 apply：

```text
applied=true
restored=...
deleted=...
ok=true
```

再跑一次应该 `restored=0 deleted=0`（幂等）。

### 7.3 回滚范围

- 恢复：根 `vmparams`、`route-a.vmparams` / `route-b.vmparams`、启动器、
  `enabled_mods.json`、`settings.json`、`hypernova.json`、本次复制的组件。
- 删除：apply 前不存在的路径（例如首次装 A 时的 `mods/MixinFR`、
  `mods/StarsectorParallel`）。
- **不碰存档**；也不会把整个安装目录还原成出厂状态。
- `migrate --apply` 没有 `rollback` label；它只创建新 target，失败时清理
  半成品。成功迁移后想撤销，删除 `%ROOT%\mods` 或从安装备份恢复；删之前
  确认里面没有你的额外文件。**如果用了 `--link`，先确认你删的是 junction
  而不是源目录；不确定就用安装备份还原。**
- 换路线：推荐直接用新安装根。若复用同一根，先回滚 A，确认
  `mods\MixinFR`、`mods\StarsectorParallel` 已消失，再 apply B。路线 B 的
  plan 会再次检查并拒绝 MixinFR / MixinLib / Parallel 残留。

如果回滚报 manifest 缺失或校验失败：不要手改 JSON 猜恢复；用安装目录的
完整备份还原，或重新安装一份干净根。

---

## 8. 故障排除

| 症状 | 先查 | 处理 |
|---|---|---|
| Java 28 下 MixinFR / Parallel 没启用 | `starsector.log` 的 `Java version:` | 路线 A 必须用 `launch-route-a.bat`（JRE 17）；不要用 `jdk-28` 启动 A。MixinFR / Parallel 官方只支持 JRE 17 |
| `SKIPPED_LOADER` 很多 | `starsector-core\logs\prepatcher.log` | Prepatcher 的目标类在别的 classloader；路线 A 根本不该装。路线 B 先去掉 `--prepatcher` 重装，确认稳定后再试 |
| 双 javaagent / 启动报 agent 冲突 | `route-a.vmparams` / `route-b.vmparams` 里的 `-javaagent` | A 只能有 MixinLib-bridge + Hypernova；B 只能有 Hypernova + FR + Prepatcher（最终配置）。不要运行 MixinFR 的 `install.bat`，不要给 A 加 FR 0.9.7，不要给 B 加 MixinFR |
| `vmparams` 首 token 是 `java.exe` / 启动报找不到主类 | `route-*.vmparams` 第一个 token | 生成的 argfile 是 token-less，首 token 必须是 JVM 参数：A 通常是 `-noverify`，B 是 `-XX:...`（Task 7 实测为 `-XX:+UnlockDiagnosticVMOptions`）。不要手工加 `java.exe`；用 `launch-route-*.bat` 启动 |
| 用 `starsector.exe` / `fr.bat` 启动后没有优化 | 启动入口 | `starsector.exe` 和 `fr.bat` 都硬编码 JRE 17，且不读 `route-*.vmparams`。A 用 `launch-route-a.bat`，B 用 `launch-route-b.bat` |
| `FATAL: route-a apply failed (manifest=...)` | 终端输出的 `manifest` / `rollback.label` | apply 可能已写文件但 manifest 失败；按 label 回滚，检查 `mods` 是否迁移完整、`enabled_mods.json` 是否有效、Hypernova `build/` 或 `jars/` 是否存在 |
| `Hypernova disabled: manifest unavailable` | `starsector.log` | 重新 apply 让工具生成 manifest，或 `python -I tools\install_manifest.py --game-root "%ROOT%"`；确认 `mods` 不是空目录 |
| 256 mod 启动 OOM / 很慢 | 根 `vmparams` 的 `-Xmx` / `-Xms` | 默认可能是 `-Xmx2048m`，256 mod 通常不够。按机器内存调到 8–12 GB（例如 `-Xmx8g`），留系统余量；改根 `vmparams` 后重新 apply，或直接改 `route-*.vmparams` |
| B 首次启动 300–500 s | 法线 / 脚本缓存 | 冷缓存正常（实测 465 s）；热跑 57–68 s。改组件会改变 enabled 集合并触发重新冷启动，不要拿冷启动判断“B 很慢” |
| A 的 256 全量 1400 s 仍不到菜单 | `docs/m7-isolation.md` | 已定位为 MixinFR 路径，不是 Java 17 / FR 0.9.5；结论已移交上游（GerBeria），本项目不承担修复。缩小 mod 集或改用 B，不要反复重装 |
| `migrate --apply` 报 `target already exists` | `%ROOT%\mods` 是否为空 | 空目录先 `rmdir`；非空目录不要删，换全新安装根。工具不会合并到已有 mods |
| `enabled_mods.json missing/error` | `%ROOT%\mods\enabled_mods.json` | 先跑迁移；或在游戏启动器里勾选 mod 并保存一次生成。工具对 missing / error 都 fail-closed（`FATAL` + rc1），不会用空列表或最小列表覆盖 |
| `--link` 创建 junction 失败 | 文件系统 / 权限 | 去掉 `--link`，用完整复制；或把安装根和源 mods 放到同一 NTFS 卷 |
| VOpt 初始化失败 | `starsector.log` 的 `Failed to initialize VRAM Optimizer` | 确认 VOpt 是 1.0.45、FR 是 0.9.7rc2（B）；A 确认 MixinFR 1.2.5。不要升 VOpt 1.0.46+ |
| 字体模糊 / 竖条 | `mods\MixinFR\mod_info.json`、`mixinfr-fonthd.log` | 确认 1.2.5；`disable-mixinfr-fonts` 在 1.2.5 只是诊断；路线 B 没有 HD 重定向，属预期 |
| 候选框在左上角 / 选词无反应 | `mixinfr-ime-fix.log` | 先看 MixinFR IME 修复；仍不行用 `disable-ime --apply` 切 ChineseInputFix；一次只留一条输入路径 |
| 优化测试版 + FR 启动冲突 | 是否路线 B + 优化版 | 21835 明确警告。改用路线 A，或把 B 装到传统汉化 / 非优化版；不要在优化版上硬叠 plain FR |
| Prepatcher 在 Java 28 下报错 / patch 不全 | `prepatcher.log` | 0.18.4 未声明 Java 28。先不加 `--prepatcher`；确认稳定后再实验 |
| 脚本 / 相对路径失效 | 是否移动了 `scripts\*.bat` | `launch-route-*.bat` 按 `%~dp0..\install\...` 定位；不要移动或重命名 scripts 目录里的文件 |
| `python` 打不开 / 是应用商店 | `python --version` | 安装真实 Python 3，或用 `py -3` 替换命令里的 `python` |
| 杀软报 javaagent | 是否 MixinFR / Hypernova agent | 字节码 agent 常见误报；确认来源官方后加白名单，不要直接关杀软 |

---

## 9. 合规与反馈

- **不重新分发**：MixinFR、StarsectorParallel、FR、汉化包、ChineseInputFix、
  Prepatcher 都从作者官方来源获取；本仓库不打包第三方文件。
- **不要上传含个人路径的日志**：反馈前检查 `starsector.log` /
  `scripts-agent.log` 里的用户名、盘符；必要时打码。
- **反馈三件套**：`starsector.log`、`mixinlib.log`（A）或
  `fr.version.txt` + Prepatcher 日志（B）、`vmparams`；再加游戏版本、
  汉化版本、完整 mod 列表、CPU / 内存。
- **版本锁定**：0.98a-RC8 + 汉化 2026.10.15 + MixinFR 1.2.5 +
  Parallel 0.1.0 + FR 0.9.7rc2 + VOpt 1.0.45 + Prepatcher 0.18.4。
  游戏或任一组件升级后，先按本教程重新 dry-run，不要直接沿用旧结论。

---

## 附录：命令速查

```bat
rem 预检
python -I tools\m7_stack.py inspect --root "%ROOT%" --text

rem 迁移（dry-run / apply）
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --text
python -I tools\m7_stack.py migrate --source Starsector-098-260mods\mods --target "%ROOT%\mods" --link --apply --text

rem 路线 A（dry-run / apply）
python -I tools\m7_stack.py route-a --root "%ROOT%" --mixinfr "%AUDIT%\vendor\MixinFR-1.2.5\MixinFR" --parallel "%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel" --hypernova-mod "%REPO%" --text
python -I tools\m7_stack.py route-a --root "%ROOT%" --mixinfr "%AUDIT%\vendor\MixinFR-1.2.5\MixinFR" --parallel "%AUDIT%\vendor\StarsectorParallel-0.1.0\StarsectorParallel" --hypernova-mod "%REPO%" --apply --text

rem 路线 B（最终配置；dry-run / apply）
python -I tools\m7_stack.py route-b --root "%ROOT%" --fr-dir "%REPO%\.cache\fr097\fast-rendering-0.9.7rc2" --jdk-dir "%REPO%\Starsector-098-260mods\jdk-28+13" --hypernova-mod "%REPO%" --mikohime-args "%REPO%\Starsector-098-260mods\Miko_Lite.txt" --xms 8G --xmx 10G --enable-cif --prepatcher "%REPO%\.cache\prepatcher\extracted\StarsectorPrepatcher" --text
python -I tools\m7_stack.py route-b --root "%ROOT%" --fr-dir "%REPO%\.cache\fr097\fast-rendering-0.9.7rc2" --jdk-dir "%REPO%\Starsector-098-260mods\jdk-28+13" --hypernova-mod "%REPO%" --mikohime-args "%REPO%\Starsector-098-260mods\Miko_Lite.txt" --xms 8G --xmx 10G --enable-cif --prepatcher "%REPO%\.cache\prepatcher\extracted\StarsectorPrepatcher" --apply --text

rem 启动（apply 后生成）
"%AUDIT%\scripts\launch-route-a.bat"
"%AUDIT%\scripts\launch-route-b.bat"

rem IME 短路（dry-run / apply）
python -I tools\m7_stack.py disable-ime --root "%ROOT%" --text
python -I tools\m7_stack.py disable-ime --root "%ROOT%" --apply --text

rem 字体诊断（1.2.5 上只读）
python -I tools\m7_stack.py disable-mixinfr-fonts --root "%ROOT%" --text

rem 回滚（dry-run / apply）
python -I tools\m7_stack.py rollback --root "%ROOT%" --label m7-route-a-... --text
python -I tools\m7_stack.py rollback --root "%ROOT%" --label m7-route-a-... --apply --text

rem 日志
python -I tools\m6_log_audit.py --game-root "%ROOT%" --out "%AUDIT%\evidence\m7-log-audit.json" --text
python -I tools\m7_stack.py collect-logs --root "%ROOT%" --out "%AUDIT%\evidence\m7-logs" --text
```
