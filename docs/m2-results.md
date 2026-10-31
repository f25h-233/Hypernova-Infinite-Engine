# M2 manifest 驱动结果

> 日期：2026-11-01
> 代码基线：`9c45d81`（main；M2 Task 1–6 已合并）
> 环境：Starsector 0.98a-RC8；260mods（256 enabled + core，257 行）；Base（11 enabled mods）
> 范围：M2 = manifest 数据层（生成 / 校验 / 安装）。通用纹理懒加载不在 M2，见 §1.3。

## 1. 结论

### 1.1 数据层门禁

- **REQ-R1-04 通过（数据层）**：manifest 由 `dds_metadata.json` 生成；260mods 已烘焙覆盖率
  **80,286 / 80,286 = 1.0**，`unresolved_baked_count=0`；无 DDSCache 的 Base 走
  `source_mode=disk_scan` 降级，`coverage.metadata=None`、`coverage.baked=1.0`。
- **REQ-R1-05 通过（数据层 + 单元测试）**：L1/L2/L3 三层稳定；L1 **6,624 ≤ 8,000**；
  per-mod `mods[]` 汇总与三层逐项相等；启动自检候选只取 L1（`StartupSelfCheckTest`）。
  运行时冒烟门禁见 §5，本任务按控制器指令未启动游戏。
- **validator**：260mods 与 Base 均 **exit 0、0 Critical**。260mods 有 **44 条既有
  `cross_layer_duplicate` Important**（同一引擎 key 跨层，L1 优先），按 R8 记录，不是失败；
  本文不声称 “OK: no findings”。
- **每 mod 分级可用**：`mods[]` 每行带 `tier`（`auto|L1|L2|L3`）；tier override 是生成期参数，
  移动该 mod 的全部条目，L1 上限由 validator 兜底。本次验收未传 override，故实际
  `stats.tiers={}`。

### 1.2 关键数字

| 项目 | 260mods | Base（降级路径） |
|---|---:|---:|
| L1 | **6,624** | 185 |
| L2 | **18,525** | 509 |
| L3 | **55,444** | 2,612 |
| 合计 | **80,593** | 3,306 |
| `coverage.metadata` | 1.0 | `None` |
| `coverage.baked` | **80,286/80,286 = 1.0** | 0/0 → 1.0（expected=0 约定） |
| `unresolved_baked_count` | **0** | 0 |
| `closure_refs` | 1.0 | 1.0 |
| validator | exit 0 / 0 Critical | exit 0 / 0 Critical |
| 生成耗时 | 183.0 s | 2.7 s |

### 1.3 范围裁决（R7）

M2 只交付 **manifest 数据层**：生成器、校验器、按 mod 分级、安装器。L1/tier 是后续懒加载的
输入，M2 **不**实现通用纹理懒加载。通用懒加载另开 **M2.5**：agent 侧
`TextureLoader.queueImage` 过滤 + 非 L1 代理/按需补加载，带 A/B、回滚、失败可见门禁。
理由：纯 mod 没有 `queueImage` 拦截点；M-1b 只覆盖法线；ADR-05 已把旧 M3 代理纹理方向移出范围。

## 2. 260mods 真实生成与校验

命令（`build/m2/260mods/`）：

```bash
python -I tools/gen_manifest.py --game-root Starsector-098-260mods \
  --out build/m2/260mods/manifest-v1.json
python -I tools/validate_manifest.py \
  --manifest build/m2/260mods/manifest-v1.json \
  --game-root Starsector-098-260mods
```

### 2.1 stats

| 指标 | 实测 |
|---|---:|
| `generated_at` | 2026-11-01T01:06:21+08:00 |
| `enabled_mods` | 256 |
| `metadata_entries`（scope） | 77,082 |
| `metadata_entries_core` | 3,204 |
| `metadata_entries_all` | 81,554 |
| `metadata_unused` | 1,268 |
| `unbaked` | 298 |
| `disk_images` | 77,371 |
| `l1_count` / `l2_count` / `l3_count` | 6,624 / 18,525 / 55,444 |
| 三层合计 | 80,593 |
| `coverage.l1_sprite_disk` | 1.0 |
| `coverage.l1_baked` | 6,621 / 6,624 = 0.999547（3 张无 metadata，走 `header_probe`） |
| `coverage.metadata` | 1.0 |
| `coverage.closure_refs` | 1.0 |
| `coverage.baked_expected` / `baked_resolved` / `baked` | 80,286 / 80,286 / **1.0** |
| `unresolved_baked_count` | 0 |
| `mods[]` 行数 | **257**（256 mod + core） |
| `mods[]` 三层求和 | 6,624 / 18,525 / 55,444（与 `layers` 完全相等） |
| `source_mode` | `dds_metadata` |
| 生成耗时 | 183,024 ms |
| 完整 manifest 大小 | 40,918,117 B |

### 2.2 closure

| 类别 | total / resolved |
|---|---:|
| variants | 1,803 / 1,803 |
| hulls | 1,765 / 1,765 |
| weapons | 2,447 / 2,447 |
| wings | 354 / 354 |

**与 brief 预期值的差异（已核实，不是回归）**：brief 写 `variants=[1797,1797]`、
`wings=[364,364]`，实测为 `[1803,1803]` / `[354,354]`。分解实测：

- 1,124 个标题 variant 根：sprites 6,576、variants 1,797、wings 347。
- 17 个标题 wing 根：sprites 70、variants 16、wings 17。
- 合并去重后：sprites 6,586、variants **1,803**、wings **354**。

即：17 个 wing 根中有 **10 个**已从 variant 根闭包可达（作为其它 variant 的嵌套 `wings`
引用被计入 `wings=347`），所以 wings 只增加 7（347→354），不是简单 347+17=364；同时 17 个
wing 根经 `wing_data.csv` 带出 **6 个**新 variant（1,797→1,803）。关键门禁不受影响：`closure_refs=1.0`、
`missing={}`，闭包 sprite 比修复前多 **10** 张，正是 L1 6,614→**6,624** 的来源（R10）。
brief 的 `[1797,364]` 是未计去重/传递 variant 的投影值。

### 2.3 validator

- 退出码 **0**，**0 Critical**。
- 1 条 Important（聚合）：`cross_layer_duplicate`，覆盖 **44** 个引擎 key；`stats.path_conflicts`
  也正好 44 条，全部为跨层同路径（30 条 L1/L3、14 条 L2/L3）。其中 2 条同路径尺寸不同
  （`graphics/weapons/hammer_barrage_t.png`、`graphics/weapons/null.png`，`content_differs=true`），
  其余 42 条尺寸一致；按引擎 key 语义 L1/L2 优先，不阻塞。
- 无 `duplicate_entry`（层内无重复 `(modId, path)`）。
- `metadata_parse_errors={}`、`core_parse_errors={}`。
- `stats.parse_errors={"hull": ["gundam_braw_bro"]}`：单个 hull 解析失败，已被闭包记录；
  `closure_refs` 仍为 1.0，validator 不将其升级为 Critical。
- 4 组既有 duplicate ModID 警告（`ConsoleCommands`/`lw_console`、`GraphicsLib`/`shaderLib`、
  `LazyLib`/`lw_lazylib`、`Particle Engine`/`particleengine`），不阻塞。

## 3. Base：有/无 DDSCache 两条路径

当前 `Starsector-098-Base` 实际带有 `mods/DDSCache`（7 个缓存，81 条 mod metadata + 3,204 条
core metadata）。brief 要验证的是“无 DDSCache 的降级路径”，因此做了两次真实运行：

1. **现状（有 DDSCache）**：`build/m2/base-with-dds/`。
2. **降级路径（临时移走 DDSCache）**：`build/m2/base/`；运行后已立即恢复
   `Starsector-098-Base/mods/DDSCache`（7 个目录确认还原）。

| 指标 | 有 DDSCache（现状） | 无 DDSCache（降级） |
|---|---:|---:|
| `source_mode` | `dds_metadata` | **`disk_scan`** |
| `metadata_entries`（scope） | 81 | 0 |
| `metadata_entries_core` | 3,204 | 0 |
| `coverage.metadata` | 1.0 | **`None`** |
| `coverage.baked` | 3,285/3,285 = 1.0 | 0/0 → **1.0** |
| `unresolved_baked_count` | 0 | 0 |
| `coverage.l1_sprite_disk` | 1.0 | 1.0 |
| `coverage.l1_baked` | 0.983784 | 0.0（全部 header_probe/spec_scan） |
| `coverage.closure_refs` | 1.0 | 1.0 |
| L1 / L2 / L3 | 185 / 509 / 2,612 | 185 / 509 / 2,612 |
| 合计 | 3,306 | 3,306 |
| closure（variants/hulls/weapons/wings） | 17/17、17/17、40/40、5/5 | 同左 |
| validator | `OK: no findings`，exit 0 | **`OK: no findings`，exit 0** |
| 生成耗时 | 4,175 ms | 2,706 ms |

降级路径满足预期：`source_mode=disk_scan`、`coverage.metadata=None`、`coverage.baked=1.0`、
validator 0 Critical，L1 保持 core 静态集 185。

## 4. 四类 fixture 证据

| 类别 | 测试 |
|---|---|
| 改名 | `test_mod_index.py::test_metadata_resolve_uses_mod_id_after_folder_rename`；`test_manifest_builder.py::test_renamed_mod_folder_resolves_by_mod_id` |
| 禁用 | `test_manifest_builder.py::test_disabled_mod_metadata_is_excluded` |
| duplicate | `test_mod_index.py::test_scan_mods_duplicate_id`；`test_manifest_builder.py::test_l3_dedupes_duplicate_mod_id_folders`、`test_same_path_first_enabled_wins`；`test_validate_manifest.py::test_duplicate_path_in_layer_is_important`、`test_cross_layer_duplicate_is_important` |
| 空 DDSCache | `test_validate_manifest.py::test_disk_scan_manifest_passes_without_metadata`；外加 §3 的真实 Base `disk_scan` 运行 |

M2 相关五个测试文件合计 **99 passed**（`test_mod_index.py`、`test_manifest_builder.py`、
`test_validate_manifest.py`、`test_sprite_closure.py`、`test_install_manifest.py`）。

## 5. 安装与运行时冒烟

### 5.1 安装（已执行）

```bash
python -I tools/install_manifest.py --game-root Starsector-098-260mods
```

- 结果：`installed: .../Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json`
- `full: L1=6624 L2=18525 L3=55444 baked=80286/80286 unresolved=0`
- 1 条 Important：`cross_layer_duplicate`（44 keys），与生成阶段一致；exit 0。
- 运行时 manifest：`schema="hypernova-runtime-1"`，仅 `layers`；三层 **6,624 / 18,525 / 55,444**，
  合计 **80,593**；文件 9,110,285 B。
- 安装耗时 333.7 s（含完整生成、校验、裁剪与写盘）。
- 安装前旧 manifest 已备份到 `build/m2/260mods/manifest-v1.json.pre-install.bak`（md5
  `9938023b…`）；新文件 md5 `f5734622…`。
- **写入不是原子操作**：`install()` 直接 `open(target, "w")` + `json.dump`，中途失败可能留下
  半截文件并覆盖旧 manifest；回滚/重装前请保留备份。本文不声称原子写。

### 5.2 冒烟（未由本代理执行，待控制器）

按控制器指令，本任务**没有**运行 `tools/smoke_run.py`，也没有启动游戏。控制器执行时使用：

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --wait-menu 300 --json-out build/m2/smoke.json
```

验收锚点（尚未实测，不得预先记为通过）：

- 到主菜单；
- agent log 含 `Hypernova active: ... manifest=80593 paths`（安装产物合计 80,593）；
- 无 `Hypernova disabled`、无 `selfcheck: FAILED`、无 `Failed to load texture`。

## 6. 测试与构建

| 命令 | 结果 |
|---|---|
| `python -I -m pytest tests/tools -q` | **248 passed, 2 failed**，19.56 s，exit 1 |
| `bash tools/java/run-tests.sh` | **103 found / 103 successful / 0 failed / 0 aborted**，296 ms，exit 0 |
| `bash tools/java/build-mod.sh` | exit 0；产出 jar 与 zip |

- 2 个 pytest 失败均为已知 `tests/tools/test_smoke_check.py`
  （`test_jar_provenance_detects_mismatch`、`test_provenance_mismatch_fails_without_skip`），
  原因是 stale 夹具里的非 zip 字节触发 `BadZipFile`；不是 M2 回归。
- `build-mod.sh`：`build/java/hypernova.jar`（51,188 B）、`build/java/hypernova-0.1.0.zip`
  （297,164 B）；zip 内含 `data/config/hypernova/manifest-v1.json`、`jars/hypernova.jar`、
  `jars/hypernova.agent.jar`。**注意**：该脚本沿用既有逻辑，从 `build/m0/base/manifest-v1.json`
  裁剪打包（本次输出 L1 185 / L2 509 / L3 2,611），不是 260mods 的 80,593；M2 的每安装
  manifest 走 `install_manifest.py`，两者不要混用。

## 7. 回滚与未做

### 7.1 回滚

- 删除 `Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json`
  即回到“无 manifest”状态（组件按既有 manifest 缺失路径处理）；恢复则放回备份文件。
  备份：`build/m2/260mods/manifest-v1.json.pre-install.bak`。
- tier override 是**生成期**参数（`gen_manifest.py --tiers` / `install_manifest.py --tiers`），
  不改变已安装的运行时 manifest；回滚 tier 只需重新生成/安装，不改运行时 schema。
- 由于写入非原子，回滚/重装前必须先保留旧文件；不要在写盘中断后假设旧 manifest 仍完整。

### 7.2 明确未做

- **未实现运行期自动重建 manifest**。用户增删/改名/禁用 mod 后，必须重跑
  `python -I tools/install_manifest.py --game-root <game>`；启动期不会自动重扫。
- **未实现通用纹理懒加载**（M2.5；见 §1.3）。
- **未执行运行时冒烟**（控制器负责；见 §5.2）。
- 未修改 `build-mod.sh` 的打包源（仍用 `build/m0/base`）；这是既有分发路径，不在本任务范围。

## 8. 证据文件

- `build/m2/260mods/manifest-v1.json`、`gen.log`、`validate.log`、`install.log`、
  `manifest-v1.json.pre-install.bak`
- `build/m2/base/manifest-v1.json`、`gen.log`、`validate.log`（无 DDSCache 降级路径）
- `build/m2/base-with-dds/manifest-v1.json`、`gen.log`、`validate.log`（Base 现状）
- `build/m2/pytest.log`、`build/m2/java-tests.log`、`build/m2/build-mod.log`
