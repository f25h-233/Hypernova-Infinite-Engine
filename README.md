# Hypernova Infinite Engine

Starsector 0.98a 的运行时纹理预取与兜底 mod，附带一个可选的启动期 Java agent。

> **状态：pre-release（0.1.0）**
> 主 mod 的运行期路径默认开启；会改变加载/显存行为的实验路径默认关闭。
> 公开发行按 M6 → M5 的路线推进，当前优先目标是“装了不会坏”。

## 这是什么

大量 mod 的 Starsector 在启动和场景切换时，时间主要花在两件事上：贴图加载/解码，以及 Janino 脚本编译。Hypernova 不改游戏文件，分两层处理：

- **主 mod（纯 mod，Form A）**：按 manifest 在舰队发现、联系人对话、部署、进入星系等时机，用帧预算调度器预取即将用到的舰船/武器贴图；miss 时回退到原版加载路径。
- **可选 agent（Form B）**：通过 `-javaagent` 在类加载期做启动期的事——FR 文件索引、Janino 脚本预编译缓存、法线图缓存补丁；另含实验性的纹理懒加载/淘汰和 frame-time probe。

主 mod 不依赖 agent；agent 缺失时自动退回纯 mod 行为。

## 当前默认值

| 模块 | 默认 | 开关 |
|---|---:|---|
| 主 mod 运行期预取/兜底 | **开** | `hypernova.json` → `enabled` |
| agent 文件索引（FR FileLoaderFast） | **开** | `fileIndex.enabled` / `-Dhypernova.fileIndex` |
| agent Janino 脚本缓存 | **开** | `scripts.enabled` |
| agent 法线图缓存补丁 | **开** | `textures.enabled` |
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
| Java | 17+（游戏自带 JRE 17 可运行；JDK 28 为测试环境） |
| Fast Rendering | 0.9.7rc2（软依赖；0.9.5 为回滚档） |
| VramOptimizer | 1.0.45（测试环境） |
| GraphicsLib | 1.12.1（测试环境） |

- 主 mod 不需要 FR；agent 的 file index / lazy textures 只在 **FR 0.9.7 / 0.9.7rc2** 上启用，其它版本 fail-open（不跳过、不代理），不会崩溃。
- 汉化测试版 / ChineseInputFix / 字体 UI 的兼容性审计入口是 [`docs/m6-results.md`](docs/m6-results.md)；lazy / eviction / probe 默认仍为 off，用户实机 gate 见该文档 §4。
- 本仓库**不包含** Starsector 游戏文件、汉化包或第三方 mod 文件。

## 安装

### 1. 主 mod

1. 把 `hypernova_infinite_engine/` 放进 `mods/`。
2. 在启动器的 Mod 管理里启用。
3. 发行包内的 `manifest-v1.json` / `lazy-skip-v1.txt` 由 **Base 纹理集**生成，只对 Base 安装准确。在 260mods 或任何其它 mod 集上使用前，必须重新生成：

   ```bash
   bash tools/java/install-manifest.sh <游戏目录>
   ```

   该脚本需要仓库里的 `tools/`；发行 zip 不含 tools。
4. 重启游戏。manifest generation/尺寸不匹配时 lazy 会 fail-open，不会崩溃。

### 2. 可选 agent

agent 负责启动期模块。安装器会把 `-javaagent` 行插到 **FR agent 之前**（顺序不能反）：

```bash
python tools/install_agent.py --game <游戏目录> --env <profile>
```

`--env` 与启动文件对应：`base` → `starsector-core/fr.vmparams`；`260mods` / `260mods-simple` → `Miko_Simple.txt`；`260mods-lite` → `Miko_Lite.txt`。装错文件不会报错，游戏照常启动，但 agent 不会加载——**静默失效**。

> `-D` 参数必须写在 `com.fs.starfarer.StarfarerLauncher` **之前**；argfile 里主类之后的 token 是应用参数，不是 JVM 选项。

## 回滚

- 主 mod：`hypernova.json` 里把 `enabled` 设为 `false`，或从 Mod 管理里禁用。
- agent：删除启动文件里的 `-javaagent:...hypernova.agent.jar` 行；安装器会保留 `*.bak-hypernova` 备份。
- lazy / eviction：把对应 `enabled` 设回 `false`，或加 `-D...=false`。
- 所有路径都 fail-open；出问题先看 `saves/hypernova/scripts-agent.log` 与 `starsector-core/starsector.log`。

## 工程状态

按里程碑推进，每个里程碑有独立的结果文档。

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

> 表里的数字是各里程碑在当时环境下的门禁结果，不代表所有 mod 集/硬件都能复现。

最近一次全量验证（2026-11-03）：main 115/115、agent 211/210/1（1 个已知 Windows symlink 用例跳过）、pytest 460。

完整实测记录在 `docs/`；规格与裁决在 [`技术笔记-纹理按需加载.md`](技术笔记-纹理按需加载.md)。

## 文档

- [技术笔记 / 规格](技术笔记-纹理按需加载.md)
- [M4 结果](docs/m4-results.md)
- [M4 手动验收](docs/m4-manual-acceptance.md)
- [M2.7 结果](docs/m27-results.md)
- [M2.8 结果](docs/m28-results.md)

## 第三方

本仓库不重新分发 Fast Rendering、VramOptimizer、GraphicsLib 或汉化包。兼容性验证使用其各自发布方的版本；请从原发布方获取并遵守各自许可证。
