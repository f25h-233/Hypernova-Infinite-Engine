# Hypernova Infinite Engine

Starsector 0.98a 的运行时纹理预取与兜底 mod，附带一个可选的启动期 Java agent。

> **版本：1.9.9（2026-11-12）**
>
> `1.0.0` 是“功能完善可用”的锚点（M2.8，2026-11-02：主 mod + agent +
> manifest + lazy/DDS/LRU 全部落地）；之后 M4/M4.1/M6 的诊断、兼容性
> 工具与修复累计为 `1.9.3`。主 mod 的运行期路径默认开启；会改变加载/显存
> 行为的实验路径默认关闭。用户实机 gate（战役 / 战斗 / 读档 / 中文输入 /
> 字体视觉）仍 **pending**；“到主菜单”不等于整套通过。不宣称 Hypernova
> 的显存/启动收益。

## 这是什么

大量 mod 的 Starsector 在启动和场景切换时，时间主要花在两件事上：贴图加载/解码，以及 Janino 脚本编译。Hypernova 不改游戏文件，分两层处理：

- **主 mod（纯 mod，Form A）**：按 manifest 在舰队发现、联系人对话、部署、进入星系等时机，用帧预算调度器预取即将用到的舰船/武器贴图；miss 时回退到原版加载路径。
- **可选 agent（Form B）**：通过 `-javaagent` 在类加载期做启动期的事——FR 文件索引、Janino 脚本预编译缓存、法线图缓存补丁；另含实验性的纹理懒加载/淘汰和 frame-time probe。

主 mod 不依赖 agent；agent 缺失时自动退回纯 mod 行为。

## 版本地图

| 版本 | 里程碑 | 含义 |
|---|---|---|
| `0.x`（pre-release） | M0 … M2.7 | 内部开发；未公开发行 |
| **`1.0.0`** | M2.8（`9f4946e`，2026-11-02） | 功能完善可用：主 mod + agent + manifest + lazy/DDS/LRU |
| `1.1.0`–`1.2.9` | M4 | frame-time probe / 会话报告 |
| `1.3.0`–`1.4.2` | M4.1 | agent-side frame probe |
| `1.5.0`–`1.9.3` | M6 | 汉化 / 中文输入 / 字体 / UI 兼容性审计与工具 |
| **`1.9.9`** | 高清字体桥（2026-11-12） | 优化测试版 + FR：agent premain 让 DynFont 生成高清缓存，并把成对的 fnt/page 覆盖到 `graphics/fonts/`；原文件备份 `*.bak-hypernova-hd`；首次约 2–3 秒，之后复用；`-Dhypernova.fontHd=false` 关闭 |
| **`1.9.7`** | manifest 生成提速（2026-11-12） | 图片尺寸持久缓存 + 并行探测 + 去掉重复磁盘校验；只加一个 mod 不再重扫全量 |
| **`1.9.6`** | FR 0.9.8 适配（2026-11-07） | agent 文件索引支持 0.9.8；lazy/DDS 使用 ResourceLoaderLock；lazy 仍默认关闭 |
| **`1.9.5`** | 健壮性修复（2026-11-05） | 玩家侧 manifest 生成容忍失效 DDSCache 记录与重复 ModID |
| **`1.9.4`** | 兼容修复（2026-11-05） | 纹理补丁支持 GraphicsLib 1.12.2（多版本 SHA 变体） |
| `1.9.3` | M6 终审 fix（`e43e7b0`，2026-11-03） | — |

`1.9.3` 不是“第 19 个正式版”，而是 `1.0.0` 之后按 `feat`/`fix` 累计出来的
post-1.0 历史：9 个 minor（诊断、兼容性工具），最后一个 minor 线到
`1.9.1`–`1.9.3` 三个 patch。里程碑本身仍用 `m0`…`m6` tag 记录，不映射到
公开版本号。

## 当前默认值

| 模块 | 默认 | 开关 |
|---|---:|---|
| 主 mod 运行期预取/兜底 | **开** | `hypernova.json` → `enabled` |
| agent 文件索引（FR FileLoaderFast） | **开** | `fileIndex.enabled` / `-Dhypernova.fileIndex`；0.9.8 上可用 `-Dhypernova.fileIndex.fr098=false` 单独关闭 |
| agent Janino 脚本缓存 | **开** | `scripts.enabled` |
| agent 法线图缓存补丁 | **开** | `textures.enabled` |
| agent 高清字体桥（远星汉化优化测试版 + FR） | **开**（仅检测到 DynFont 时） | `-Dhypernova.fontHd=false`；只观察不写盘 `-Dhypernova.fontHd.dryRun=true` |
| 纹理懒加载 | **关** | `textures.lazy.enabled=true` / `-Dhypernova.textures.lazy=true` |
| DDS 懒加载 | 随懒加载 | `textures.lazy.dds` |
| 显存淘汰 / LRU | **关** | `textures.lazy.eviction.enabled=true` |
| 场景卸载（实验） | **关** | `...eviction.sceneUnload=true` |
| frame-time probe | **关** | `-Dhypernova.frameProbe=true` |

> 发行配置 `data/config/hypernova/hypernova.json` 不含 `lazy` 块；上表的懒加载/淘汰都需要显式开启。默认关闭不是“没做完”，而是 M2.8/M4 的结论：这些路径尚未在用户门禁里证明稳定收益，先保持可回滚。主 mod 的 `eviction` 是预留项，当前未实现。

## 兼容性

| 项 | 版本 / 说明 |
|---|---|
| Starsector | 0.98a-RC8 |
| Java | 17+（游戏自带 JRE 17 可运行；JDK 28 已验证） |
| Fast Rendering | 0.9.7rc2 / 0.9.8（软依赖；agent 的 file index / lazy 支持 0.9.7 / 0.9.7rc2 / 0.9.8） |
| VramOptimizer | 1.0.45（测试环境） |
| GraphicsLib | 1.12.1 / 1.12.2（agent 纹理补丁按原类 SHA-256 分别支持；其它版本降级为不修改，不崩溃） |

- 主 mod 不需要 FR；其它 FR 版本下 agent 的 file index / lazy textures 会 fail-open（不跳过、不代理），不会崩溃。
- FR 0.9.8 上的 lazy/DDS 仅在菜单路径做过 selftest（真实进程内 materialize→evict→re-materialize）；读档/战役场景未验证。
- 汉化测试版 / ChineseInputFix / 字体 UI 的兼容性审计见 [`docs/m6-results.md`](docs/m6-results.md)。
- 本仓库**不包含** Starsector 游戏文件、汉化包或第三方 mod 文件。

## 安装

### 1. 主 mod

1. 把 `hypernova_infinite_engine/` 放进 `mods/`。
2. 在启动器的 Mod 管理里启用。
3. 发行包内的 `manifest-v1.json` / `lazy-skip-v1.txt` 由 **Base 纹理集**生成，只对 Base 安装准确。在 260mods 或任何其它 mod 集上使用前，必须重新生成：

   ```bash
   bash tools/java/install-manifest.sh <游戏目录>
   ```

   该脚本需要仓库里的 `tools/`；发行 zip 不含 tools。生成器会把图片尺寸缓存到
   `manifest-probe-cache-v1.json`：之后再生成只探测新增或改动过的图片，只加一个
   mod 不会重扫全量。
4. 重启游戏。manifest generation/尺寸不匹配时 lazy 会 fail-open，不会崩溃。

### 2. 可选 agent

agent 负责启动期模块。安装器会把 `-javaagent` 行插到 **FR agent 之前**（顺序不能反）：

```bash
python tools/install_agent.py --game <游戏目录> --env <profile>
```

`--env` 与启动文件对应：`base` → `starsector-core/fr.vmparams`；`260mods` / `260mods-simple` → `Miko_Simple.txt`；`260mods-lite` → `Miko_Lite.txt`。装错文件不会报错，游戏照常启动，但 agent 不会加载——**静默失效**。

> `-D` 参数必须写在 `com.fs.starfarer.StarfarerLauncher` **之前**；argfile 里主类之后的 token 是应用参数，不是 JVM 选项。

## 构建与发行

```bash
bash tools/java/build-mod.sh
```

产物：`build/java/hypernova-1.9.9.zip`（含主 jar、agent jar、manifest、lazy-skip、README-install）。发行包固定使用 `Starsector-098-Base` 的 manifest；其它 mod 集在目标游戏目录就地生成。

## 回滚

- 主 mod：`hypernova.json` 里把 `enabled` 设为 `false`，或从 Mod 管理里禁用。
- agent：删除启动文件里的 `-javaagent:...hypernova.agent.jar` 行；安装器会保留 `*.bak-hypernova` 备份。
- lazy / eviction：把对应 `enabled` 设回 `false`，或加 `-D...=false`。
- 所有路径都 fail-open；出问题先看 `saves/hypernova/scripts-agent.log` 与 `starsector-core/starsector.log`。

## 工程状态

按里程碑推进，每个里程碑有独立的结果文档；内部 tag 为 `m0`…`m6`。

| 里程碑 | 主题 |
|---|---|
| M0 | 数据/索引基座（L1/L2/L3、manifest） |
| M1 | 运行期预取 + 兜底（Form A） |
| M-1d | Janino 脚本预编译缓存 |
| M-1b | 启动期法线桶 / DDS 可选 |
| M-1d-2 | key manifest（7,606 → 458 ms） |
| M-1e | 无 FR / OS 缓存 / Java 17 三门禁 |
| M-1f | FR 0.9.7rc2 迁移 + 重新基线 |
| M3 / M3.1 | 启动加速（G-01'' ≤50 s）/ 索引 save 异步化 |
| M2 | manifest 驱动（80,286 烘焙覆盖） |
| M2.5–M2.8 | 懒加载 / DDS / LRU / 场景卸载（默认 off） |
| M4 / M4.1 | 验收与发布硬化 / agent-side frame probe |
| M6 | 汉化 / 中文输入 / 字体 / UI 兼容审计（260mods 单环境） |

> 表里的数字是各里程碑在当时环境下的门禁结果，不代表所有 mod 集/硬件都能复现。

最近一次全量验证（2026-11-07）：main 115/115、agent 217/216/1（1 个已知 Windows symlink 用例 aborted（环境性））、pytest 511。

## 版本策略

- `1.0.0`：功能完善可用（M2.8；主 mod + agent + manifest + lazy/DDS/LRU）。
- `1.x.0`：`1.0.0` 之后的新功能 / 诊断 / 兼容性工具。
- `1.x.y`：修复、兼容性、文档；不改默认行为。
- `2.0.0`：破坏性变更（配置 schema、存档兼容、默认行为翻转导致结果不同）。
- 内部里程碑用 `m0`…`m6` tag 记录，不映射到公开版本号。

## 文档

- [M6 兼容性审计](docs/m6-results.md)
- [M6 手动验收](docs/m6-manual-acceptance.md)

## 第三方

本仓库不重新分发任何 mod、汉化包、游戏本体。详见 [`NOTICE`](NOTICE)。

## License

- 代码（Java / Python / 脚本）：**Apache-2.0**，见 [`LICENSE`](LICENSE)。
- 公开文档（`docs/m6-*`）：**CC BY 4.0**（署名即可转载/引用）。
- 第三方组件：各自原许可证，见 [`NOTICE`](NOTICE)。
