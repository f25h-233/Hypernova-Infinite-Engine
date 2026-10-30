# M-1b 实测结果：法线缓存懒加载（agent 路线）

> 日期：2026-10-30
> 环境：Starsector 0.98a + 260mods、热缓存、`scripts.enabled=true`、GraphicsLib 1.12.1、Fast Rendering 0.9.5
> 结论：**agent 路线通过出口门禁的自动化部分**；战斗内法线正常为唯一待人工确认项。DDS 烘焙是可选工具，不参与门禁。

## 1. 实测

### 1.1 最终 A/B（2026-10-30 19:47–19:57）

同一安装，只切换 `hypernova.json` 的 `textures.enabled`，其余配置（含 `scripts.enabled=true`）保持一致。

| 组 | `textures.enabled` | 主菜单 | `normal_before_menu` | `normal_after_menu` | 法线窗口 | `patched` | `mismatch_line` | `gate_ok` |
|---|---|---:|---:|---:|---:|---|---|---|
| A | `true` | **85.5 s** | **0** | 0 | **0.0 s** | true | null | **true** |
| B | `false` | 144.7 s | 30,378 | 2 | 37.0 s | false | null | false |

- **A − B = 59.2 s**，这是单次 A/B 的端到端差（含单轮波动与次级效应；B 的法线窗口为 37.0 s；同配置早前 A 冒烟为 98.2 s），不能当作纯纹理净收益。
- 启动期法线加载：30,378 → 0，下降 **100%**（门禁要求 ≥80%，且绝对 ≤50 行）。
- A 组 agent 日志：
  - `textures: cache probe ready, files=31627`
  - `textures: patched org/dark/shaders/util/TextureData`
- B 组 `normal_after_menu=2` 是菜单出现后才加载的 2 行，不参与门禁；门禁只看 `normal_before_menu`。
- 口径说明：B 组 `menu_s`（日志口径）为 144.7 s，冒烟器墙钟口径为 144.8 s，两者不矛盾。

门禁判定（`tools/m1b_measure.py`）：只分析最后一个 agent 会话，要求 `menu_t is not None`、`patched=true`、`mismatch_line=null`、`normal_before_menu <= min(max(50, baseline * 0.2), 50) = 50`。A 组全部满足。

### 1.2 基线与背景

| 阶段 | 主菜单 | 启动期法线行数 | 说明 |
|---|---:|---:|---|
| 10-25 无 agent 历史基线（`run2`） | 92.7 s | 30,401 | 法线窗口 29.4 s；M-1 热缓存中位数 86.5 s / 30,378 / 29.6 s（规格 §2） |
| 原始基线（M-1d scripts on、oracle 修前） | 187.5 s | 30,378 | 本轮优化前的起点 |
| M-1d oracle 修后、纹理补丁未生效 | 130.2 / 99.2 s | 30,378 | 按补丁未生效推断，非直接测量；两轮未存对应 JSON |
| 最终 B（补丁关闭） | 144.7 s | 30,378 | 同一次 A/B 的对照 |

**不要混口径**：187.5 → 85.5 s 是 M-1d oracle 修复与 M-1b 的累计收益，不能全部归因于 M-1b；§1.1 的 59.2 s 只是单次 A/B 端到端差（含单轮波动与次级效应；B 的法线窗口为 37.0 s；同配置早前 A 冒烟为 98.2 s），不能当作纯纹理净收益。

### 1.3 为什么 29.4 s 窗口没有变成 29.4 s 收益

- 92.7 s 是**无 agent** 的历史基线；当前 A 是 **agent+补丁**，两者不是同一配置。
- 29.4 s 是法线日志窗口，不等于关键路径耗时：它与脚本编译、DDS 句柄登记、mod 初始化交错，取消法线加载不会等量缩短首屏。
- agent 直接加载开销实测很小：premain 20 ms、transformers 26 ms、cache 预载 8 ms、CacheProbe 扫描 <1 s；后台 key 5.6 s + oracle 3.9 s（抢 I/O）。
- 单轮波动 85.5–144.7 s，不能把单次差值当净收益；确定性证据是法线 30,378 → 0。

**M-1b 的确定性出口是法线计数；时间收益量级 10–30 s，需多轮中位数才能钉死，不能从单轮宣称 30 s/59 s。**

## 2. 门禁结论

| 出口项 | 要求 | 实测 | 结论 |
|---|---|---|---|
| 启动期 `cache/*_normal.png` 行数 | 下降 ≥80%，绝对 ≤50 行 | 30,378 → 0（−100%） | PASS |
| 补丁实际生效 | `patched=true` 且无 hash mismatch | 两者均满足 | PASS |
| 战斗内法线正常 | 人工检查 | 待执行（见 §4） | PENDING |

结论：自动化门禁 **PASS**；战斗内法线检查完成前，M-1b 的出口视为“自动化通过、人工项待签”。若人工检查发现异常，按 §5 回滚。

## 3. 实现机制

### 3.1 javaagent 顺序（关键）

FR 的 `BytecodeFileTransformer` 会先改写 `TextureData` 的 GL 常量池（`org/lwjgl/opengl/GLxx` → `com/genir/renderer/bridge/opengl/GLxx`）。如果超新星 agent 排在 `-javaagent:fr.agent.jar` **之后**，transformer 收到的是已被改写的字节，SHA-256 守卫不匹配，补丁静默 no-op。因此启动参数中必须先注册超新星 agent：

```
-javaagent:.../hypernova.agent.jar
-javaagent:fr.agent.jar
```

`tools/install_agent.py` 已强制该插入点，并会在旧安装上迁移：删除 FR 之后的旧 agent 行，重新插到 FR 之前；写入 LF 行尾，保留 `.bak-hypernova` 备份。

### 3.2 脚本域文件限制与 CacheProbe

补丁类由脚本类加载器定义，Starsector 的脚本安全管理器拒绝文件访问：

```
SecurityException: File access and reflection are not allowed to scripts
```

因此补丁类不能自己 stat/打开缓存文件。解决方案是把文件探测前移到 agent 域：

1. `TextureCacheTransformer.transform()` 首次命中 `TextureData` 时调用 `CacheProbe.init(modRoot)`；
2. `CacheProbe` 在 agent 域一次性扫描 `mods/GraphicsLib/cache/`，记录满足 `isFile()` 且 `length() >= 8` 的文件名集合（本机 31,627 个）；
3. 补丁类只调用 `CacheProbe.has(cachePath)` 做内存查表，basename 匹配，不碰文件系统；
4. 扫描失败/路径不可解析时集合为空，懒加载自动回退原路径，不崩溃。

### 3.3 懒条目与加载时机

命中条件（全部满足才走懒路径）：

```
!invalidateCache
&& !GraphicsLibSettings.preloadAllMaps()
&& !isAlwaysPreloadFor(type, key)
&& CacheProbe.has(cachePath)
```

此时创建：

```java
new TextureEntry(null, cachePath, 1f, !autoGenOverride, true, false, false)
```

语义：不创建 Sprite、`loaded=false`、`spriteName=cachePath`、`validToLoad=true`；只登记 key/name 映射，不在启动期解码/上传纹理。战斗前 `unloadAndPreloadTextures()` / `getTextureDataWithAutoGen()` 按原逻辑加载这些条目，与原始 eager 行为一致。

未命中时走原 eager 路径（见 §6 的已知限制）。

### 3.4 补丁身份

| 项 | 值 |
|---|---|
| 原 `TextureData.class` SHA-256 | `6a4302bcacd2dd90f6637c815d1443ddfdb3d28ff59095d48c875358de4e8594` |
| 补丁 `TextureData.class` SHA-256 | `789bb790b24c368017cea78e6d087e417393f961fc5c2454862cbbaecb100d22`（probe 修复后的最终产物） |
| 编译目标 | `--release 17`（class major 61） |
| 锁定版本 | GraphicsLib 1.12.1；Fast Rendering 0.9.5 |

## 4. 战斗内法线人工检查（待执行）

状态：**未执行**（需用户在真实启动器下人工确认）。
检查日期：____　截图：____

1. 用正常启动器（不是 `launchDirect`）启动 260mods，加载一个存档。
2. 进入一场包含多种舰船/武器的战斗。
3. 检查：舰船/武器有正常的光照层次，没有全黑、全亮、彩虹噪点或明显平面化。
4. 检查 `starsector.log`：战斗加载期间应出现 `Loading image [cache/..._normal.png]`（说明懒加载真的在工作），且不出现 `Failed to load texture`。
5. 截图留档；若异常，记录 mod/舰船名并回滚补丁（`textures.enabled=false`）。

补充观察：懒条目把加载从菜单推迟到战斗前/首次使用，战斗加载阶段会承担原先首屏的一部分成本；检查时一并留意是否有不可接受的卡顿。

## 5. 回滚

### 5.1 只关闭纹理补丁（最小改动，推荐）

编辑安装目录：

```
Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
```

设置：

```json
"textures": { "enabled": false }
```

重启游戏。注意：配置缺失时默认 **enabled=true**，必须显式写 `false`。也可用系统属性覆盖：`-Dhypernova.textures=false`。

回滚后法线恢复启动期全量加载，行为回到 B 组口径（主菜单约 144.7 s、30,378 行）。

### 5.2 移除 agent（彻底回滚）

```bash
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite --action uninstall
```

`--env` 需与实际启动器一致：`260mods-lite` 对应 `Miko_Lite.txt`，`260mods`/`260mods-simple` 对应 `Miko_Simple.txt`，`base` 对应 `starsector-core/fr.vmparams`。卸载只删除 agent 行，不消费/恢复 `.bak-hypernova` 备份。

### 5.3 DDS 可选线回滚

见 `docs/m1b-dds-optional.md` §6（还原 `DDSCache/GraphicsLib` 备份，或删除 `cache\` 条目与对应 DDS）。

## 6. 已知限制

- **截断缓存文件**：`CacheProbe` 只按“文件名存在 + 长度 ≥8 B”注册。≥8 B 但已截断/损坏的 `*_normal.png` 仍会登记懒条目，首次加载时才暴露失败；<8 B 不注册，走原路径。
- **强制路径**：`GraphicsLibSettings.preloadAllMaps()==true`、`invalidateCache==true`、或 `isAlwaysPreloadFor(type, key)` 命中时，补丁走原始 eager 路径，不产生懒条目。
- **版本锁**：仅 GraphicsLib 1.12.1 且原 class SHA-256 精确匹配时生效。其它版本或被其它 agent 改写过的字节会 hash mismatch，补丁静默 no-op（日志有 `textures: TextureData sha mismatch`），不会崩溃。
- **agent 顺序**：超新星 agent 必须在 FR 之前；用户手动改启动参数可能破坏顺序，补丁随之失效。
- **probe 失败**：agent 域无法解析 mod 根或扫描异常时 `CacheProbe` 为空集，懒加载禁用，回退原路径。
- **白屏观察**：本轮 A/B 两次都在 260mods 加载画面出现白屏；B 组最终 144.8 s 到达主菜单，日志无补丁相关异常（只有 mod 版本检查器网络超时）。现有证据不能把白屏归因于补丁，但需在人工战斗中继续观察。
- **首屏下限**：即使法线全部不加载，实测首屏仍 85.5 s，高于规格早先估计的 ~56 s；差额来自其它加载阶段（脚本、DDS 句柄登记、mod 数据等）。M-1b 单独不足以达标 G-01。
- **成本转移**：懒条目在战斗前/首次使用时加载，战斗加载阶段会承担原先首屏的一部分成本；需人工确认无不可接受卡顿。
- **DDS 线**：BC7 有损，画质只能肉眼确认；本机尚未对安装目录执行完整烘焙与 A/B，当前没有 DDS 数字。

## 7. 验证记录（本次文档任务）

| 命令 | 结果 |
|---|---|
| `bash tools/java/run-agent-tests.sh` | **47/47 passed** |
| `bash tools/java/run-tests.sh` | **95/95 passed** |
| `python -m pytest tests/tools -q` | **139 passed, 2 failed** |

2 条失败为 `tests/tools/test_smoke_check.py::test_jar_provenance_detects_mismatch` 与 `test_provenance_mismatch_fails_without_skip`，属 M1 遗留问题（安装 jar 不是有效 zip 的夹具场景），**deferred**，不是 M-1b 引入。本任务未重跑游戏冒烟；A/B 数据由 controller 于 2026-10-30 19:47–19:57 采集，战斗内检查由用户执行。
