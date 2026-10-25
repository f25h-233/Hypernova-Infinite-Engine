# M0 覆盖率报告 — Base 10 mods + Zulu 17.0.10

- 游戏根：`Starsector-098-Base`
- 生成时间：2026-10-25T17:27:29+08:00
- scope：`mod_non_shader`，include_core：`True`
- 数据来源：`disk_scan`，优先级：`enabled_order_then_core`

## 出口 gate

| 指标 | 结果 | 实测 |
|---|---|---|
| L1 ≤ 8000 | PASS | 185 |
| closure_refs ≥ 0.95 | PASS | 1.000 |
| l1_sprite_disk ≥ 0.95 | PASS | 1.000 |
| metadata == 1.0 | N/A | N/A |

## 层级规模

| 层 | 条目数 |
|---|---:|
| L1 | 185 |
| L2 | 509 |
| L3 | 2611 |

## 覆盖率

| 指标 | 值 |
|---|---:|
| L1 sprite 落盘 | 100.00% |
| L1 已烘焙 | 0.00% |
| 闭包引用解析 | 100.00% |
| metadata 纳入 | N/A |
| metadata 条目（scope） | 0 |
| core 条目 | 0 |
| 磁盘图片（scope） | 83 |
| 未烘焙 | 83 |
| metadata 回退命中 | 0 |

## 闭包缺口

| 类别 | 引用 | 解析 |
|---|---:|---:|
| variants | 17 | 17 |
| hulls | 17 | 17 |
| weapons | 40 | 40 |
| wings | 5 | 5 |

- 无

## 首屏需求覆盖

- 未提供 demand.jsonl
