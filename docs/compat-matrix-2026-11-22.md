# 兼容性矩阵（2026-11-22 审计）

> 适用：Starsector 0.98a-RC8（Windows）。测试基座 `Starsector-098-Base`（12 个 mod：
> BoxUtil / ChineseInputFix / lunalib / lw_console / lw_lazylib / MagicLib / particleengine /
> RetroLib / shaderLib / VramOptimizer / DDSCache / hypernova_infinite_engine），
> `-Xmx4g -Xms2g`（为给别的程序让内存临时下调）。
>
> **口径**：`实测` = 本机真实启动 + 日志/JSON 证据；`源码` = 读上游源码/字节码得出；
> `推断` = 未实机；`未测` = 本轮没做。用户实机 gate（战役 / 战斗 / 读档 / 中文输入 /
> 字体视觉）仍 **全部 pending**，本文不宣称验收通过。

## 1. 版本实况（2026-11-22 查上游）

| 组件 | A/B 草稿锁定 | 当前 release | 漂移 | 本轮处理 |
|---|---|---|---|---|
| Fast Rendering | 0.9.7rc2 | **v1.0.2**（2026-11-18，正式版） | 跨 3 个大版本 | **实机 10/10 通过**，agent 已支持 |
| VramOptimizer | 1.0.45 | **v1.0.51**（2026-11-16） | 6 个 patch | 已实机（1.0.45 在基座，1.0.51 未装） |
| Mikohime | v0.8.1 | **v0.8.3**（2026-11-12） | 2 个 minor | 未测（与 FR 1.0.2 无直接耦合） |
| Prepatcher | 0.18.4 | **v0.18.9**（2026-11-19） | 5 个 patch | 未测 |
| MixinFR | 1.2.5 | **1.2.5**（2026-11-01） | 无 | 仍是最新 |
| StarsectorParallel | 0.1.0 | **0.1.0**（2026-10-26） | 无 | 仍是最新 |
| Hypernova | 1.9.x | **1.9.11**（本文） | — | 已更新 |

## 2. Fast Rendering × Hypernova（本轮核心）

| FR 版本 | file index | scripts cache | normal-cache | lazy/DDS | 证据 |
|---|---|---|---|---|---|
| 0.9.7 / 0.9.7rc2 | ✅ | ✅ | ✅ | ✅（默认关） | M-1f / M-1g |
| 0.9.8 | ✅（默认开） | ✅ | ✅ | ✅（默认关） | M-1g |
| 1.0.0 / 1.0.1 | ✅ | ✅ | ✅ | 门禁关（签名已变） | 2026-11-18 基座 5/5 |
| **1.0.2 正式版** | ✅ **1.9.11 起** | ✅ | ✅ | 门禁关 | **本轮 10/10** |
| 1.0.2rc1 | ❌ 门禁关（fail-open） | ✅ | ✅ | 门禁关 | 2026-11-18 关索引 6/6 |

### 1.0.2 的 `reserve(getImageFileCount())` 修复

**问题**：FR 1.0.2rc1 起，`ResourceLoaderState.initMain` 在加载任何纹理前
`texGenerator.reserve(getImageFileCount())`。这个计数只由真实目录枚举
（`DirectoryCrawler.makeNewRosurceHandle`）累加。索引重放跳过枚举 → 计数为 0 →
纹理线程在 `ResourceLoaderLock` 之外并发 `glGenTextures()` → `ResourceGenerator.get`
的 `expectedCacheSize` 路径 `Executor.get` 拿不到值 → 启动期随机崩溃。

**实机证据（基座，FR 1.0.2 稳定版）**：

| 配置 | 通过率 | 崩溃签名 |
|---|---|---|
| 索引关（`-Dhypernova.fileIndex=false`） | 5/5 | — |
| 索引开，**无** `fileCount` 补偿（伪报 1.0.1 放行门禁） | **3/4** | `ArrayIndexOutOfBoundsException: Index 2 out of bounds for length 2` at `Frame.add` |
| 索引开，补偿只数索引 entries（images=2119） | **5/8** | `Executor.get` 返回 null → `portrait*.png not found` |
| 索引开，补偿 entries **+ 目录 + 真实 crawl 重算**（images=5466） | **10/10** | — |

**修复（1.9.11）**：`FileIndexHook.refillFileCount` 在重放索引时按扩展名重建
`FileLoaderFast.fileCount`，覆盖 **重放出来的文件 key** 与 **索引记录的目录**
（目录在 FR 里也按扩展名 `""` 计数）。日志交叉验证：
`refilled file counts for 98 extensions, dirs=1134, images=5466, outerImages=5466`
—— 内层 `getImageFileCount()` 读回与补偿值完全一致；真实 crawl 的
`CACHED FILES` 为 `png: 5168 / jpg: 180 / PNG: 120`（合计 5468，差值来自
大小写扩展名归类，非漏计）。

**冷/热与收益**（同一基座、同一 warm 条件、连续轮次）：

| 配置 | 到主菜单 | 说明 |
|---|---|---|
| 索引开（修复后） | 7.5 / 8.0 / 8.0 / 8.0 / 8.0 / 8.5 / 8.5 / 8.5 / 8.9 / 8.0 s | 10/10 |
| 索引关（对照） | 7.0 / 7.0 / 8.0 / 8.0 / 8.0 s | 5/5 |

**结论：12-mod 基座上索引没有可测收益（略慢或持平）。** 首轮建库
（9452 entries / 3529 mod entries / 480 dirs）之后，重放本身要遍历 9442 条并重建
`FileLoaderFast.cachedFiles`，在只有 480 个目录时省下的枚举时间不足以抵消。
索引的价值仍应在 256-mod 量级（M3 实测 file-index 批次 2–4 s）；**本轮不做收益结论**。
注意：`--clear-index-each-round` 每轮强制冷建库的跑法会显示 18.6–22.6 s，
那不是「索引关」的数字，别混用。

## 3. 第三方组件 × Hypernova

| 组件 | vs agent | vs 主 mod | 顺序 | 备注 |
|---|---|---|---|---|
| **active-stats 1.0**（FD神秘肥鱼 22120） | ✅ 零类重叠 | ✅ | `hypernova → fr → active-stats` | 它改 10 个战役核心类；`COMPUTE_FRAMES` 重算被 FR 改写的帧表；作者要求放其它 agent 之后 |
| ChineseInputFix 2.0.0 | ✅ | ✅ | — | 日志实测加载 v2.2 组件 |
| VramOptimizer 1.0.45/1.0.51 | ✅ | ✅ | — | 1.0.48「Oats for genir」与 FR 联动；基座每会话一条 `SetDDSTextureParamaters` `NoSuchMethodException` 属已知预期 |
| BoxUtil 1.6.3 | ✅ | ✅ | — | FR readme 声明 1.6.0+ 需 OpenGL 4.5 |
| GraphicsLib 1.12.2 | ✅ | ✅ | — | 纹理补丁按类 SHA 选变体；**目录名 `shaderLib`**（`GraphicsLib` 与之同 id 同 jar，只能留一份） |
| MixinFR 1.2.5 | 需手动顺序 | ✅ | `MixinLib-bridge → Hypernova` | 单行 vmparams 用 `install-agent.bat` 会被拆行，建议手动插 |
| StarsectorParallel 0.1.0 | ✅ | ✅ | — | 依赖 MixinLib；`CombatAiHotspotMixin` 在 FR 0.9.5 下 `NOT-INJECTED` |
| **Prepatcher 0.18.9（B，plain FR）** | ✅ | ✅ | `Hypernova → FR → Prepatcher` | 实测 `status=transformer-installed`、**15 classes / 21 patches / 0 skipped** |
| **Prepatcher 0.18.9（A，MixinFR）** | ❌ **空转** | — | `MixinLib-bridge → Hypernova → Prepatcher` | `status=runtime-unavailable`、**patchedClasses=0 / appliedPatches=0**，原因 `Starsector runtime is unavailable ... com.fs.starfarer.api.Global`；游戏能启动但补丁一个都没打 |

## 4. 汉化优化测试版 × FR

| 组合 | 结果 | 证据 |
|---|---|---|
| 优化测试版 2026.10.15 + FR 0.9.5 / 0.9.7rc2 / 0.9.8 | ✅ | 2026-11-21 本机复现 |
| 优化测试版 2026.10.15 + **FR 1.0.x** | ❌ premain 断言退出 | `AssertionError: Ambiguous methods`；优化版改写了 `sound/O0oO` 与 `LoadingUtils` |
| 传统汉化 / 原版 obf + FR 1.0.2 | ✅ | 本轮基座即此组合 |

**给玩家的口径**：优化测试版 1015 只能用 MixinFR 1.2.5（内置 FR 0.9.5）或纯 Hypernova；
想用 FR 1.0.2 就换传统汉化。上游 issue：`Halke1986/starsector-render#15`（仍 open，0 评论）。

## 5. 已知未测 / 风险

- **VOpt 1.0.51** 已装进两个 A/B 小集根（实机跑通，见 §6）；**Mikohime v0.8.3** 已用于 B（非交互配置，见 §6）；
  **Prepatcher 0.18.9** 仍未装（0.18.5 起才修好 Java 28 XML/platform-class 处理，属实验项）。
- **256 mods 环境**：本轮全部在小基座（12 mod）上做；`59.2 s / 465 s` 仍是 2026-11-04
  FR 0.9.7rc2 环境的数字，**没有在 1.0.2 上重测**。
- **active-stats** 只做了源码级兼容分析，没有实机三 agent 联跑。
- **lazy/DDS** 在 1.0.2 上仍是门禁关（`DDSIntegration.commitTexture` 已改为
  `(String,int,TextureData)`），要开需要单独一轮适配。
- **A 路线的双 JVM 会让"到主菜单"测量失真**：MixinFR 的 launcher JVM 先退出，
  旧 `smoke_run.py` 把 launcher 退出当成 `menu-timeout`（并用 launcher 的 PID 去
  kill，rc=128 打空），游戏 JVM 留在后台继续加载。**上一版记录的「A = 4.26 s」
  就是 launcher 的退出时刻，不是主菜单时间**；原始 json 全是 `menu-timeout`。
  已修（`two_jvm` 标记 + `find_game_jvm` 按父进程找游戏 JVM），见 §6。

## 6. A/B 小集实机（2026-11-23 重建，3 轮交替）

两个根**从零重建**（`optimized-2026.10.15` 全量复制 → 装组件，不再用 junction 复用）。

| | A | B |
|---|---|---|
| 启动 | `jre/bin/java.exe` + `launch_a.vmparams`（`starsector.exe` 读的单行 `vmparams` 行内插 agent） | `jdk-28+13/bin/java.exe` + `../Miko_Simple.txt`（Mikohime 0.8.3 非交互生成） |
| 组件 | MixinFR **1.2.5**（内置 FR 0.9.5）+ JRE **17** + VOpt **1.0.51** + Hypernova **1.9.11** + Prepatcher **0.18.9** | FR **0.9.8**（双 jar）+ Temurin **28+13-ea** + Mikohime **v0.8.3** + VOpt **1.0.51** + Hypernova **1.9.11** + Prepatcher **0.18.9** |
| 本机实测（3 轮，装 Prepatcher） | **13.5 / 13.5 / 12.5 s，中位 13.5 s** | **8.5 / 8.0 / 8.5 s，中位 8.5 s** |
| 本机实测（3 轮，不装 Prepatcher） | 14.5 / 13.0 / 14.0 s，中位 14.0 s | 8.5 / 8.0 / 7.5 s，中位 8.0 s |
| Prepatcher 实效 | **空转**：`runtime-unavailable`，0 classes / 0 patches | 生效：`transformer-installed`，**15 classes / 21 patches / 0 skipped** |
| agent 状态 | scripts cache 命中（116 条 / 3–4 ms）；`textures patched`；`file index: disabled for FR 0.9.5`（设计门禁） | scripts cache 命中（116 条 / 1 ms）；`textures patched`；`file index` 写入 3771 / 加载 15657（513–519 dirs） |
| 进程 GPU | 1114 MB | 1116 MB |

口径：12-mod 小集（BoxUtil **1.6.3** / ChineseInputFix 2.0 / lunalib / LazyLib / MagicLib /
Particle Engine / RetroLib / shaderLib(GraphicsLib 1.12.2) / VOpt 1.0.51 / Hypernova 1.9.11 /
Prepatcher 0.18.9，A 另加 MixinLib）、`-Xmx4096m`、warm（首轮建缓存）。

**两条路线的汉化都已核对**：`starfarer_obf.jar` = `8d4de3c9…`、`fs.sound_obf.jar` = `14562a3e…`，
`localization_version.json` = 「远行星号中文汉化包 2026.10.15 / startup-optimization / zh-Hans」，
与母本 `optimized-2026.10.15` 逐项一致。

**Prepatcher 的差异幅度在噪声内**（A −0.5 s、B +0.5 s，各 3 轮），不能当作收益或损失结论。
真正的区别是**有没有生效**：A 0 个补丁，B 21 个补丁。

**B 比 A 快 ~5 s，但这是 12-mod 小集单机 3 轮，不能外推到 256 全量**
（M7 的 59.2 s / 465 s 是 FR 0.9.7rc2 的旧环境）。

已确认的踩坑（本轮修复）：

1. **MixinFR 双 JVM**：smoke 不能把 launcher 退出当失败（见 §5）。
2. **`MIKO_FAST_RENDERING` 只认 `1`**，写 `yes` 会被静默忽略 → Mikohime 报 `Fast Rendering: Disabled`。
   同理 `MIKO_RESOURCE_CACHE=0` / `MIKO_PREPATCHER=0`。
3. **Mikohime 必须在干净 PATH 下跑**：Git Bash 的 PATH 里有 GNU `find`，会把
   `find /I "..."` 解析成 Unix find，报 `unknown predicate`。
4. **`fr_install.py` 是"升级/回滚"工具**，拒绝安装到没有 `fr.jar` 的目录；全新根要先按
   FR 官方 readme 复制文件，再让工具改版本/重指启动行。
5. **VOpt 的 gh-proxy 下载会被截断**：断点续传会把 zip 拼坏（50,820,261 vs 官方 49,763,493）。
   **必须用 `testzip()` 校验体积与完整性**，损坏就整份重下。
6. **Prepatcher 在 A（MixinFR）上是空转**：agent 能加载、游戏能启动，但
   `prepatcher.log` 报 `Starsector runtime is unavailable; no bytecode patches registered:
   com.fs.starfarer.api.Global`，`status=runtime-unavailable`、0 classes / 0 patches。
   **不要因为"游戏起来了"就认为 A 的 Prepatcher 生效**——必须看这两行。
7. **Mikohime 的 Prepatcher 集成会写带引号的 agent 行**（`"-javaagent:...jar"`），
   而 Hypernova 的 `install_agent.py` 匹配的是不带引号的形式；重新生成启动档后
   要重新插 Hypernova agent，并确认顺序是 `Hypernova → FR → Prepatcher`。


## 7. 路线 A 的纹理补丁为什么打不上（2026-11-23 查清）

**不是 agent 顺序问题**（顺序只是让 Hypernova 能插进去，插进去也不会生效）。
真正原因是 **MixinFR 自己也改写了同一个类**：

```
[mixinlib.log]
[MixinGovernance] WARN potential conflict: target=org.dark.shaders.util.TextureData
                  declared by 2 mixins [GLNormalMapBudgetMixin, FrNormalTakeoverMixin]
[main/Audit] APPLY mixin=GLNormalMapBudgetMixin  target=org.dark.shaders.util.TextureData
[main/Audit] APPLY mixin=FrNormalTakeoverMixin  target=org.dark.shaders.util.TextureData
[main/Transform] target org.dark.shaders.util.TextureData 50438 -> 92696
```

Hypernova 的 `TextureCacheTransformer` 按**精确 source SHA** 匹配三个变体
（GraphicsLib 1.12.1 `6a4302bc…`、1.12.2 `3b939e21…`、以及其 patched 版本）。
MixinFR 把 `TextureData` 从 50,438 字节改写成 92,696 字节后，这个 SHA 不存在于白名单，
于是每次都是：

```
textures: unsupported GraphicsLib TextureData (sha256=…); lazy normal cache disabled for this version
```

**这属于设计内降级（fail-open），不是崩溃**：A 路线上 textures/normal-cache 一直没生效，
只有 scripts cache 生效。两条路线共用的 `Graphics.jar` SHA 相同（`c4ed41ac…`），
所以差异确实来自 MixinFR 的运行期改写，不是 mod 文件不同。

**结论**：A 路线上不要指望纹理补丁。真想要纹理补丁就用路线 B。
若要支持 A，需要为「MixinFR 改写后的 TextureData」再生成一个变体——但那要跟着
MixinFR 的每次更新重做，且两个 mixin 的最终形状由 Fabric 的顺序决定，不保证稳定。
**本项目不做这个适配。**
