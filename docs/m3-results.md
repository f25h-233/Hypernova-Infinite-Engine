# M3（0–50 s 桶）结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2（fr.jar SHA-256 5f811d32…）
> 基线：M-1f warm 中位 60.6 s；G-01' ≤48.5 s

## 1. 同日 control 相位（miko-lite-phase，3 轮）

| 轮 | menu_s | crawl files | crawl ms | initFileLoaders ms | initSpecStore ms | initMods ms | preload |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 73.6 | 229754 | 5146 | n/a | n/a | n/a | hit |
| 2 | 73.1 | 229754 | 5567 | n/a | n/a | n/a | hit |
| 3 | 68.1 | 229754 | 4591 | n/a | n/a | n/a | hit |
| 中位 | 73.1 | 229754 | 5146 | n/a | n/a | n/a | hit |

> 说明：本轮安装的 agent jar（2026-10-31 11:26）早于 Task 1 的 timeline 代码，`timeline` 为空是预期的；按 Task 2 逃逸舱，用 `crawl.ms` 代理 `initFileLoaders`（FR 中 `initFileLoaders` = crawl + DDS init，侦察实测 DDS 62 ms）。`initSpecStore` / `initMods` 待 Task 5 装新 jar 后复核。

## 2. 归因

- 目录枚举：crawl 229,754 files，4,591 / 5,146 / 5,567 ms，中位 **5,146 ms**（约为 menu 的 7.0%）。三轮文件数完全一致，说明枚举成本稳定、可被索引直接削减。
- spec/JSON 解析：本轮 timeline 为空（旧 jar），`initSpecStore` 未测得，不用猜测值填充。
- mod init：同上，`initMods` 未测得，待 Task 5 新 jar 复核。
- 结论：crawl 中位 5,146 ms ≥ 2,000 ms，代理的 `initFileLoaders` 同样 ≥ 2,000 ms → **GO Task 3/4/5**。同日 control 中位 73.1 s，比 M-1f 的 60.6 s 慢 12.5 s（Review Focus #6 的同日漂移）；后续 A/B 只与同日 control 比，G-01' 另报相对 60.6 s 的口径。

## 3. 杠杆与 A/B

（Task 5 填充）

## 4. 停止条件 / 目标修订

（Task 6 填充）
