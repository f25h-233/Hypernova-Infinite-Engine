# M0 覆盖率报告 — 260mods (256 enabled) + JDK28/Miko

- 游戏根：`Starsector-098-260mods`
- 生成时间：2026-10-25T17:29:19+08:00
- scope：`mod_non_shader`，include_core：`True`
- 数据来源：`dds_metadata`，优先级：`enabled_order_then_core`

## 出口 gate

| 指标 | 结果 | 实测 |
|---|---|---|
| L1 ≤ 8000 | PASS | 6614 |
| closure_refs ≥ 0.95 | PASS | 0.997 |
| l1_sprite_disk ≥ 0.95 | PASS | 1.000 |
| metadata == 1.0 | PASS | 1.000 |

## 层级规模

| 层 | 条目数 |
|---|---:|
| L1 | 6614 |
| L2 | 18535 |
| L3 | 56410 |

## 覆盖率

| 指标 | 值 |
|---|---:|
| L1 sprite 落盘 | 100.00% |
| L1 已烘焙 | 99.95% |
| 闭包引用解析 | 99.73% |
| metadata 纳入 | 100.00% |
| metadata 条目（scope） | 78040 |
| core 条目 | 3204 |
| 磁盘图片（scope） | 77371 |
| 未烘焙 | 298 |
| metadata 回退命中 | 0 |

## 闭包缺口

| 类别 | 引用 | 解析 |
|---|---:|---:|
| variants | 1814 | 1797 |
| hulls | 1760 | 1760 |
| weapons | 2442 | 2442 |
| wings | 347 | 347 |

- `variant`（17）：Avali_aerospace_fighter_wing, hii_beambomber_wing, hii_blaze2_wing, hii_blaze_wing, hii_fiirkan2_wing, hii_fiirkan_wing, hii_heeshk_wing, hii_raachok_wing

## 首屏需求覆盖

- 需求记录：30470 条，唯一路径 30469 条
- manifest 覆盖：60 / 30469 = 0.20%
- 已覆盖样例：graphics/NeighborPost/backgrounds/NP_background01.png, graphics/armaa/backgrounds/armaa_atmo.jpg, graphics/armaa/backgrounds/armaa_atmo2.jpg, graphics/armaa/backgrounds/armaa_atmo3.jpg, graphics/armaa/backgrounds/armaa_city2.jpg, graphics/armaa/backgrounds/armaa_gravion.jpg, graphics/armaa/backgrounds/armaa_gravion_2.jpg, graphics/armaa/backgrounds/armaa_shaft.png
- 未覆盖路径前缀：cache (30378), graphics (30), .. (1)
