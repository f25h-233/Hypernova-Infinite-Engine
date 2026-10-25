# M0 覆盖率报告 — 260mods (256 enabled) + JDK28/Miko

- 游戏根：`Starsector-098-260mods`
- 生成时间：2026-10-25T17:29:19+08:00（manifest 于 18:4x 经 Task 5 fix 重建）
- scope：`mod_non_shader`，include_core：`True`
- 数据来源：`dds_metadata`，优先级：`enabled_order_then_core`

## 出口 gate

| 指标 | 结果 | 实测 |
|---|---|---|
| L1 ≤ 8000 | PASS | 6614 |
| closure_refs ≥ 0.95 | PASS | 0.997 |
| l1_sprite_disk ≥ 0.95 | PASS | 1.000 |
| metadata == 1.0 | **不具证据力** | 1.000（构造性恒真，见下） |

## 层级规模

| 层 | 条目数 |
|---|---:|
| L1 | 6614 |
| L2 | 18535 |
| L3 | 55444 |

## 覆盖率

| 指标 | 值 |
|---|---:|
| L1 sprite 落盘 | 100.00% |
| L1 已烘焙 | 99.95% |
| 闭包引用解析（L1 口径） | 99.73% |
| metadata 纳入（**恒真，不可信**） | 1.000 |
| **metadata 真实消费率（L1+L2 / all）** | **30.83%**（25,146 / 81,554） |
| metadata 条目（scope） | 77,074 |
| metadata 条目（core） | 3,204 |
| metadata 条目（all） | 81,554 |
| metadata 未用于任何层（unused） | 1,276 |
| core 条目 | 3,204 |
| 磁盘图片（scope） | 77,371 |
| 未烘焙 | 298 |
| metadata 回退命中 | 0 |

> **`metadata == 1.0` 为什么不能当证据**：L3 的设计就是"其余全部 metadata"，所以 L3 循环会把所有条目标成 seen，分母恒等于分子。真实可用的数字是 **30.83%**：L1+L2（实际会被启动期/运行期消费的部分）只覆盖了全部 metadata 的三成，其余 69% 落在 L3 兜底。这不影响 M0 出口（gate 不依赖 metadata），但**不能用 1.0 宣称"manifest 已覆盖全部纹理需求"**。

## 闭包缺口

| 类别 | 引用 | 解析 |
|---|---:|---:|
| variants | 1814 | 1797 |
| hulls | 1760 | 1760 |
| weapons | 2442 | 2442 |
| wings | 347 | 347 |

- `variant`（17）：全部是 `title_screen_variants.csv` 里的 **wing id**（如 `hii_blaze_wing`、`valk_lightning_wing`），在 `wing_data.csv` 有映射、按 wing 解析可再展开约 10 张 sprite。不是磁盘缺文件。

## 首屏需求覆盖

- 需求记录：30,470 条，唯一路径 30,469 条
- **scope 内需求覆盖：60 / 60 = 100%**
- 全部需求路径覆盖：60 / 30,469 = 0.20%

> **0.20% 的正确解读**：未覆盖的 30,409 条**不是 manifest 的缺口**，而是不在 scope 内：
> - 30,378 条 `cache/*_normal.png` → `mods/GraphicsLib/cache/`（shaderLib 运行时生成的法线缓存，产物而非源资产）
> - 27 条 `graphics/…` → `GraphicsLib` / `shaderLib` 内部资源（scope 排除）
> - 3 条 particle → `fs.common_obf.jar` 内资源
> - 1 条 `launcher_bg.jpg` → `mikohime/` 启动器资源
>
> 也就是说：**scope 内的首屏源纹理需求，manifest 100% 覆盖**。这个指标不参与 gate。

## 附注

- 本报告数字对应 manifest 重建后的产物（Task 5 fix `04e1cb4`）；L1/L2/L3 与跨 CWD validator 均已复验。
- 已修复：81,559 条 `absolutePath` 相对路径 → 全绝对；L3 8 条 `(modId,path)` 重复 → 0；`--no-core` 三层漏 core → 全 0。
