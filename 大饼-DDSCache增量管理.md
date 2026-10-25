# 大饼：DDSCache 增量管理器

> 状态：未立项。与 `技术笔记-纹理按需加载.md`（纹理按需加载）是**两个独立问题**，只共享 manifest 基础设施。

## 一、要解决的问题

现在只要往 `mods/` 加一个 mod，就得跑 `烘焙DDS缓存.bat` → 选 `ProcessMods` → **全量重烘 40 分钟**（260mods 规模）。减 mod 也一样，还得手动清孤儿缓存。

## 二、实测依据（本机 2026-10-25，260mods）

`mods/DDSCache/<folder>/dds_metadata.json` 每条记录自带增量所需的全部字段：

| 字段 | 实测含义 | 用途 |
|---|---|---|
| `RelativeImagePath` | 源图的 mod 内相对路径 | 定位源文件 |
| `ImageEditDateDate` | **= 源 PNG 的 mtime**（实测秒级一致） | 判断“变没变” |
| `DDSCreationDate` | = 生成的 DDS 文件 mtime | 判断 DDS 是否存在且新鲜 |
| `ImageHash` | **不是** SHA-256（4/4 实测不匹配），是 VOpt 自有哈希 | 不用于变更判定 |
| `DDSFilePath` | DDS 落地位置（反斜杠绝对路径） | 清理孤儿 |
| `Width` / `Height` / `CompressionFormat` | 尺寸与 BC7 | 校验 |
| `VOptVersion` | 烘焙器版本（实测 `VOpt v1.0.45`） | 版本变化时全量重烘 |

规模：233 个 DDSCache 文件夹、81,554 条记录；启用 mod 侧 77,381 张图（scope 内）。

## 三、设计

```
enabled_mods.json → 每个 mod 的图片清单
        ↓
对每张图：os.stat(mtime) 对比 ImageEditDateDate
   ├─ 无记录          → 新增，待烘
   ├─ mtime 比记录新   → 修改，待重烘
   ├─ 记录在、源文件没了 → 删除，清 metadata + DDS
   └─ mtime 未变       → 跳过
        ↓
只烘「新增 + 修改」；清理孤儿 DDS
        ↓
按 mod 粒度更新各自的 dds_metadata.json
```

**判定只用 mtime，不用哈希**：`ImageHash` 算法未知；mtime 在复制/解压后可能变新，但那是“多烘一次”，方向安全（绝不会漏烘）。

**预期收益**：加/改一个 mod 从 40 分钟降到 1–3 分钟；删 mod 只清文件，秒级。

## 四、三个障碍

1. **DDSCreator 是交互式 .NET exe，无 CLI**。要么逆向命令行参数，要么自己实现 BC7（`texconv`/`DirectXTex`），格式头要对齐 VOpt。
2. **`ImageHash` 语义未知**，无法做内容级校验，只能信 mtime。
3. **VOpt 版本变化**必须全量重烘（可用 `VOptVersion` 检测）。

## 五、出口标准（若立项）

- 加一个 mod 后，增量烘焙耗时 ≤ 该 mod 图片数 × 3 ms。
- 全量校验：`manifest` 引用与实际 DDS 集合无遗漏、无孤儿。
- 删 mod 后，DDSCache 中该 mod 的记录与文件全部清除，其他 mod 不受影响。

## 六、与现有工作的关系

- 复用 M0 的 `tools/mod_index.py`（mod 扫描、metadata 读取、路径归一化）与 `tools/hn_json.py`。
- **不进入** M0–M3 的里程碑；纹理按需加载不依赖本项。
- 若要推进，建议单独立项（暂记 M-D），先做只读原型：扫描并输出“待烘/待删/可跳过”三份清单，不实际烘焙。
