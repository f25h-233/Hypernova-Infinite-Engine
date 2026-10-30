# M-1b 可选路线：DDSCreator 离线烘焙法线图（BC7 DDS）

> **可选，不参与 M-1b 出口门禁。** 主路线是 agent 的 `TextureData` 懒加载补丁；
> 本路线只是把 3 万张 `GraphicsLib/cache/*_normal.png` 预先压成 BC7 DDS，
> 让 DDSCache/VOpt 在运行时直接上传压缩纹理。两条路线可以独立验证，不要同时开。
>
> 工具：`tools/dds_normal_cache.py`（`prepare` / `adopt` / `verify`）
> 测试：`tests/tools/test_dds_normal_cache.py`（3 passed）

## 1. 为什么 DDSCreator 会跳过我们

GraphicsLib 的 mod id 是 **`shaderLib`**（`mods/GraphicsLib/mod_info.json`），
DDSCreator 的跳过/排除规则是按 mod 或目录生效的。实测本机现有
`mods/DDSCache/GraphicsLib/dds_metadata.json`（155 条）中 **`cache\` 前缀为 0 条**：
31,627 张 `cache/*_normal.png` 一张都没有被烘焙。上游记录还提到它会跳过
`graphics/shaders/`；本机这个版本实际生成了 149 条 `graphics\shaders\...`
（2026-10-24），说明跳过规则随版本有差异——**以 `dds_metadata.json` 的实测结果为准**。
无论规则细节如何，`cache/` 不会被处理，所以需要绕。

**绕法（staging）**：把这些 PNG 硬链接到一个“普通 mod”的普通图片目录：

```
mods/hypernova_dds_staging/
├── mod_info.json
└── graphics/normalcache/*.png   ← 31,627 个硬链接（跨卷时自动退化为复制）
```

DDSCreator 看到的是 `graphics/normalcache/`，不在跳过名单里，于是正常烘焙。
`adopt` 再把 metadata 里的 `ModFolderName` / `RelativeImagePath` / `DDSFilePath`
改写回 `GraphicsLib` + `cache\` 布局。整个过程不修改 GraphicsLib 原文件。

## 2. 前置条件

- 游戏目录含 `mods/GraphicsLib/cache/*_normal.png`（本机 31,627 张）。
- `mods/VramOptimizer/bin/DDSCreator.exe` 可运行；GPU 支持 BC7（近十年显卡均可）。
- staging 与 `GraphicsLib/cache` 在同一磁盘卷时 `prepare` 用硬链接，否则自动复制
  （也可以加 `--copy` 强制复制）。
- 以下命令都在仓库根目录执行，`--game` 默认就是 `Starsector-098-260mods`；
  要换目录时写在子命令之后，例如
  `python tools/dds_normal_cache.py prepare --game Starsector-098-Base`。

## 3. 完整命令序列

### 3.1 prepare：建立 staging

```bash
# 全量 31,627 张（先准备磁盘/时间；硬链接几乎不占空间）
python tools/dds_normal_cache.py prepare

# 或先小样本验证链路（10 张）
python tools/dds_normal_cache.py prepare --limit 10

# 强制复制而不是硬链接
python tools/dds_normal_cache.py prepare --copy
```

产物：`mods/hypernova_dds_staging/graphics/normalcache/*.png` +
`mods/hypernova_dds_staging/mod_info.json`。注意 `prepare` 会跳过已存在的目标文件；
要刷新先删 `mods/hypernova_dds_staging/graphics/normalcache/`。

### 3.2 启用 staging mod

DDSCreator 只处理**已启用**的 mod。二选一：

- 启动器里勾选 `Hypernova DDS staging`；或
- 编辑 `mods/enabled_mods.json`，把 `"hypernova_dds_staging"` 加进 `enabledMods` 数组。

### 3.3 人工运行 DDSCreator（交互式 TUI）

```bash
# 方式一：批处理入口
mods/VramOptimizer/bin/run_dds.bat
# 方式二：直接运行
mods/VramOptimizer/bin/DDSCreator.exe
```

在 TUI 里选 **ProcessMods**。它会处理所有已启用的 mod（已有 DDS 缓存会按
哈希/日期跳过）；如果只想烘 staging，先在 TUI 的 mod 编辑菜单里只保留
`hypernova_dds_staging`。完成后确认：

```
mods/DDSCache/hypernova_dds_staging/dds_metadata.json
mods/DDSCache/hypernova_dds_staging/graphics/normalcache/*.dds
```

### 3.4 adopt：改写并合并到 GraphicsLib 布局

先备份现有 metadata（`adopt` 会整文件重写，虽然会保留非 `cache\` 条目）：

```bash
cp -a mods/DDSCache/GraphicsLib mods/DDSCache/GraphicsLib.bak-before-m1b
```

```bash
# 先 dry-run 看条数与改写结果
python tools/dds_normal_cache.py adopt --dry-run

# 正式采纳
python tools/dds_normal_cache.py adopt
```

`adopt` 的安全行为：

- 只挑 `RelativeImagePath` 以 `graphics\normalcache\` 开头的 staging 条目；
- 任何一条不是 BC7（`dxgiFormat != 98`）、源 DDS 缺失、或 PNG/DDS 尺寸不一致，
  都在写盘前 `exit 2` 失败关闭；
- 目标 `dds_metadata.json` 中已有的 `cache\` 条目会被替换，其余条目（本机 155 条
  `graphics\shaders\...` 等）保留；
- DDS 用硬链接放到 `mods/DDSCache/GraphicsLib/cache/`（失败退化为复制）。

### 3.5 禁用 staging

从 `mods/enabled_mods.json` 移除 `"hypernova_dds_staging"`（或启动器取消勾选）。
它只用于烘焙，运行时不参与。

### 3.6 verify：结构校验

```bash
python tools/dds_normal_cache.py verify
```

检查每个 `cache\` 条目：DDS 文件存在、DX10 头、BC7（98），并用
`RelativeImagePath` 的 basename 到 `mods/GraphicsLib/cache/<basename>` 找源 PNG，
比对 `Width`/`Height` 是否一致。源 PNG 不存在时只打印 warning（无法比对，不计 bad）；
DDS/PNG 损坏或截断时打印 `not a DDS / corrupt` 并返回 2。
全部通过打印 `verified N entries, 0 bad` 并返回 0；有坏条目返回 1；metadata 缺失返回 2。

## 4. 产物布局与 FR 的 key 规则

```
mods/DDSCache/GraphicsLib/
├── dds_metadata.json                 # existing + cache\ 条目
└── cache/
    └── <name>_normal.dds
```

采纳后的条目长这样：

```json
{
  "ModID": "GraphicsLib",
  "ModFolderName": "GraphicsLib",
  "RelativeImagePath": "cache\\<name>_normal.png",
  "ImageType": "Png",
  "DDSFilePath": "\\mods\\DDSCache\\GraphicsLib\\cache\\<name>_normal.dds",
  "CompressionFormat": "BC7",
  "Width": 256,
  "Height": 128,
  "Mean": [0.5, 0.5, 1.0],
  "Weighted": [0.5, 0.5, 1.0],
  "Median": [0.5, 0.5, 1.0]
}
```

> **手改 metadata 时 `Mean` / `Weighted` / `Median` 不能省。** FR 的
> `readTextureData` 会读取这三个字段；缺字段会导致**整个** `dds_metadata.json`
> 加载失败（不是单条失效）。`adopt` 直接复制 DDSCreator 的条目，这三个字段天然存在。

DDSCache（VOpt）按 **`<DDSCache>/<ModFolderName>/dds_metadata.json`** 找条目，
再用条目里的 **`RelativeImagePath`**（反斜杠转正斜杠）作为图像 key 去
`Settings.getSprite(...)` 找纹理，最后按 `DDSFilePath`（拼在游戏根目录后、
反斜杠转正斜杠）读取 DDS。因此：

- `ModFolderName` 必须与图像实际所在 mod 的**文件夹名**一致（`GraphicsLib`）；
- `RelativeImagePath` 必须是该 mod 内的相对路径（`cache\<name>.png`）；
- `DDSFilePath` 必须以 `\mods\DDSCache\GraphicsLib\cache\` 开头；
- `ModID` 只出现在 verbose 日志里，不参与查找（本工具仍统一改成 `GraphicsLib`）。

## 5. A/B 测量

目的：量化 DDS 对“主菜单前法线加载”和菜单耗时的影响。**两组都关掉 agent 补丁**，
避免两条路线混在一起。

```bash
# 安装目录配置：mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
# 当前安装版已有 "textures": { "enabled": true }；A/B 期间改成 false，跑完恢复 true
"textures": { "enabled": false }
```

两组保持 `scripts.enabled` 相同；建议都设为 `false` 以单独观察纹理路径
（设为 `true` 也可以，只是 M-1d 的脚本成本会盖住纹理差异）。

**A（DDS 开）**：`DDSCache/GraphicsLib/cache/*.dds` 与 metadata 就位。

```bash
python tools/smoke_run.py --profile miko-lite --rounds 1 --linger 60 \
  --json-out build/m1b-dds-on.json
python tools/m1b_measure.py \
  --log Starsector-098-260mods/starsector-core/starsector.log \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --json-out build/m1b-dds-on-measure.json
```

**B（DDS 关）**：**不要只改目录名**。FR 的 `DDSIntegration.findDDSMetadata()`
会扫描 `DDSCache` 下任意子目录里以 `dds_metadata.json` 结尾的文件；目录改名后
metadata 仍会被加载，但 DDS 路径全部失效，`readTextureBytes` 会抛
RuntimeException。正确做法二选一：

1. 把 metadata 文件本身改名（推荐，改动最小）：
   ```bash
   mv mods/DDSCache/GraphicsLib/dds_metadata.json \
      mods/DDSCache/GraphicsLib/dds_metadata.json.off
   ```
   `endsWith("dds_metadata.json")` 不再匹配，FR 不会加载它。
2. 把整个目录移出 `DDSCache`：
   ```bash
   mv mods/DDSCache/GraphicsLib mods/GraphicsLib-dds-off
   ```

然后重跑同样的两条命令（输出改 `-off`）。恢复：

```bash
# 方式 1 恢复
mv mods/DDSCache/GraphicsLib/dds_metadata.json.off \
   mods/DDSCache/GraphicsLib/dds_metadata.json

# 方式 2 恢复
mv mods/GraphicsLib-dds-off mods/DDSCache/GraphicsLib
```

读取 `normal_before_menu`、`normal_window_s`、`menu_s` 对比。注意：A/B 都关了
`textures` 补丁，`m1b_measure.py` 的 `gate_ok` 会因为 `patched=false` 而恒为 false，
**这里只看数字，不看 gate**（`gate_ok` 是 agent 主路线的门禁口径）。

预期：

- `normal_before_menu` 应显著下降（DDSCache 命中 `cache\` 条目后不再走 PNG 加载）；
  若仍有大量 `Loading image [cache/..._normal.png]`，说明 metadata 没命中，
  先跑 `verify`、检查 `ModFolderName`/`RelativeImagePath` 与日志里的 DDS 替换行。
- `menu_s` 的收益**有限**：DDS 只降低单张纹理的解码/上传成本，
  不消除约 3 万次纹理对象创建与查找。真正的启动期大收益来自 agent 懒加载补丁；
  DDS 的价值主要是显存（BC7 约省 75%）。

## 6. 质量检查与回滚

**质量检查**：进一场战斗，看舰船/武器/导弹的法线贴图是否正常（金属高光、法线
凹凸、无花屏/条纹）。BC7 是有损压缩，平滑法线渐变可能出现轻微 banding；
与原 PNG 对比，异常就回滚。

**回滚（二选一）**：

1. 整目录还原（推荐，adopt 前已备份）：
   ```bash
   rm -rf mods/DDSCache/GraphicsLib
   mv mods/DDSCache/GraphicsLib.bak-before-m1b mods/DDSCache/GraphicsLib
   ```
2. 只删本路线产物：删除 `mods/DDSCache/GraphicsLib/cache/*.dds`，并从
   `dds_metadata.json` 中删除 `RelativeImagePath` 以 `cache\` 开头的条目
   （其余 GraphicsLib 条目不要动）。若手工重建/新增条目，必须带上
   `Mean` / `Weighted` / `Median`（见 §4），否则 FR 会拒绝整个 metadata 文件。

回滚后重启游戏即可恢复 PNG 路径。staging 目录可整体删除
（`mods/hypernova_dds_staging`），不影响已采纳的硬链接副本。

## 7. 已知限制

- `adopt` 的尺寸校验依赖 PNG IHDR 与 DDS 头；不校验像素内容，BC7 质量只能靠肉眼。
- `prepare` 的硬链接与 `GraphicsLib/cache` 同卷才生效，跨卷自动复制（占空间）。
- DDSCreator 会处理所有已启用 mod；首次全量烘焙可能很久，TUI 里可只选 staging。
- `verify` 只查存在性、DX10/BC7 头和尺寸，不解码像素。
- DDS 路线不改变纹理对象创建次数，不替代 agent 补丁；M-1b 门禁只认 agent 路线。
