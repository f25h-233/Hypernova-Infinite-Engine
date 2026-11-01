# M2 清单驱动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把运行时 manifest 变成「从 DDSCache metadata 生成、键稳定、覆盖可证明 100%、可按 mod 分级」的可再生工件，并让启动期预取纪律（只允许 L1）有代码与测试证据。

**Architecture:** 纯 Python 数据管线（`mod_index` → `manifest_builder` → `validate_manifest` → `trim_manifest` / `install_manifest`），身份键从「mod 文件夹名 + 相对路径」升级为「`ModID` + 相对路径」、文件夹名只作回退；运行时 schema `hypernova-runtime-1` 不变，per-mod 汇总与 tier override 只存在于完整 manifest。Java 侧只改一处：启动自检的候选集从「L1→L2→L3 顺序取」收紧为「只取 L1」。

**Tech Stack:** Python 3.14（stdlib only，`python -I`）、pytest 9、Java 17（major 61）、JUnit 5、Git Bash（Windows 11）、`tools/smoke_run.py`。

**Spec:** `技术笔记-纹理按需加载.md` §5.4（manifest 数据模型）、§7 M2（清单驱动）、REQ-R1-04/05；OD-02 已裁决 A 全预载（L1 ≤ 8,000）。

---

## Global Constraints

- **L1 ≤ 8,000**（OD-02 A 全预载）。当前 260mods L1 = **6,614**；本计划完成后预期 **6,624**（+10，见 Task 4）。
- **覆盖 100%**：声明的 scope（`mod_non_shader`，含 core）内、所有可解析的已烘焙纹理都必须有 manifest 条目，且源 PNG 与 DDS 都真实存在。禁用 mod 的 metadata 记 `unused`，不算失败。
- **运行时 schema 不变**：`dist/*/manifest-v1.json` 仍是 `{"schema":"hypernova-runtime-1","layers":{L1,L2,L3}}`，只保留 `path/modId/w/h/baked`。per-mod 汇总、tier、覆盖率只写进完整 manifest。
- **完整 manifest schema 保持 `SCHEMA = 1`**：只做向后兼容的字段追加，不改既有字段语义。
- **Python 只用 stdlib**；脚本必须能在 `python -I` 下运行（仓库惯例：脚本内部自己补 `sys.path`）。
- **确定性输出**：同一输入两次生成的 `layers`、`mods`、`stats` 必须逐字节等价（`generated_at` 除外）。
- **只读游戏安装**：生成/校验只读 `--game-root`；唯一写入点是 `install_manifest.py` 的运行时 manifest 目标。
- **Java 仍按 `--release 17` 编译，class major = 61**；不得引入新依赖。
- **不要改 `enabled_mods.json`、`Miko_*.txt`、游戏配置**。
- **Escape hatch**：若计划里的断言数字/测试顺序与实现不符，按实际修正并在报告里说明，无需请示。**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**
- 若 `dds_metadata.json` 的记录没有 `ModID` 字段，回退用 `ModFolderName`（旧版 DDSCreator 兼容）；不得因此报错。

## Review Focus

1. **mod 文件夹改名、`ModID` 不变** → manifest 仍能把 metadata 绑到当前文件夹，`absolutePath`/`ddsPath` 存在，覆盖率仍 100%。测试：Task 2 `test_renamed_mod_folder_resolves_by_mod_id`。
2. **mod 被禁用/移除、DDSCache 仍留着旧 metadata** → 不进覆盖面分母，只进 `metadata_unused`，validator 不报 Critical。测试：Task 2 `test_disabled_mod_metadata_is_excluded`（既有）+ Task 3 覆盖率口径测试。
3. **两个 mod 共享同一相对路径 / 同一个 `ModID` 出现在两个文件夹** → 按 enabled 顺序稳定 first-wins，`(modId,path)` 不重复。测试：Task 2 `test_l3_dedupes_duplicate_mod_id_folders`（既有）+ `test_same_path_first_enabled_wins`（Task 2）。
4. **Base 的 DDSCache 为空**（无缓存副本）→ `source_mode=disk_scan`，L1 仍由 core 静态资产构成，validator 通过（`coverage.metadata=None`、`coverage.baked=1.0`），不能把「没有 metadata」判成失败。测试：Task 3 `test_disk_scan_manifest_passes_without_metadata`。**注意**：stock Base 实际带 DDSCache（7 个缓存、81 条 + 3,204 core），走 `dds_metadata`、baked 3,285/3,285；`disk_scan` 只在临时移走 DDSCache 的副本上验证。
5. **tier override 把整个 mod 推进 L1 导致超限** → validator 必须报 `l1_too_large` Critical，且 `install_manifest.py` 在写盘前拒绝。测试：Task 3 `test_l1_too_large_is_critical`（既有）+ Task 5 `test_install_refuses_to_write_when_critical`。

---

## Pre-flight（controller 在派发前写入 ledger）

- **Mode:** `pipeline`（默认；任务线性，审查与下一任务实现流水重叠）。
- **BASE:** `e81b7c4`（`git rev-parse HEAD`）。
- **OD-02:** A 全预载已裁决；L1 6,614 ≤ 8,000。
- **基线（2026-10-31 `build/m0/260mods/manifest-v1.json`）：** L1 6,614 / L2 18,535 / L3 55,444；metadata 81,554；enabled scope+core 80,278；unused 1,276；closure variants 1814/1797、hulls 1760/1760、weapons 2442/2442、wings 347/347；missing = 17 个 **wing id** 被当成 variant。
- **本计划后的预期：** L1 **6,624** / L2 **18,525** / L3 **55,444**（10 张从 L2 升 L1；Task 2 真实预跑实测，R10）、`closure_refs=1.0`、`coverage.baked=1.0`（expected **80,286**，R9）、`unresolved_baked_count=0`、`mods` 257 行（256 enabled + core）。validator 为 **0 Critical / exit 0**；260mods 有 **1 条聚合既有 `cross_layer_duplicate` Important（覆盖 44 个 key）**（R8）。
- **Task 依赖：** T1 → T2 → T3 → T5；T2 → T4；T7 依赖全部。T6 独立。
- **Touches（写者表）：**
  - T1: `tools/mod_index.py`, `tests/tools/test_mod_index.py`
  - T2: `tools/manifest_builder.py`, `tools/gen_manifest.py`, `tests/tools/test_manifest_builder.py`
  - T3: `tools/validate_manifest.py`, `tests/tools/test_validate_manifest.py`
  - T4: `tools/sprite_closure.py`, `tests/tools/test_sprite_closure.py`, `tests/tools/test_manifest_builder.py`
  - T5: `tools/install_manifest.py`（新）, `tests/tools/test_install_manifest.py`（新）
  - T6: `src/main/java/hypernova/HypernovaPlugin.java`, `tests/java/hypernova/StartupSelfCheckTest.java`（新）
  - T7: `docs/m2-results.md`（新）、`技术笔记-纹理按需加载.md`、memory 文件
- **Rulings（控制器裁决，执行时入 ledger）：**
  1. **R1** 运行时 schema 不变；per-mod 数据只在完整 manifest。
  2. **R2** 覆盖率分母 = 声明 scope 内的 enabled mod + core；禁用/孤儿 metadata 只记 unused。
  3. **R3** 稳定身份 = `(ModID, 相对路径)`；文件夹名是回退；core 的 `ModID` 归一为 `core`。
  4. **R4** tier override 移动该 mod 的全部条目；L1 上限仍由 validator 兜底，不在生成器里静默丢弃。
  5. **R5** L1 闭包根 id 允许是 wing/hull；先经 `wing_data.csv` / hull 索引解析，再判 missing。
  6. **R6** 启动自检只取 L1（REQ-R1-05）；不新增任何启动期预取队列。

---

### Task 1: Metadata 稳定身份（ModID + 路径）

**Files:**
- Modify: `tools/mod_index.py:12-14`（常量）、`:48-62`（MetadataEntry/MetadataIndex）、`:249-292`（read_dds_metadata）
- Test: `tests/tools/test_mod_index.py`

**Interfaces:**
- Consumes: 无（本任务是最底层）
- Produces:
  - `CORE_MOD_ID = "core"`
  - `normalize_mod_id(value: str) -> str`
  - `MetadataEntry(mod_folder: str, rel: str, dds_rel: str, width: int, height: int, mod_id: str = "")`
  - `MetadataIndex.by_modid_rel: dict[tuple[str, str], list[MetadataEntry]]`
  - `MetadataIndex.resolve(mod_id: str, mod_folder: str, rel: str, exclude_core: bool = False) -> MetadataEntry | None`
  - `MetadataIndex.get(...)` 行为不变（Task 2 仍会用到）

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_mod_index.py` 末尾追加（文件顶部已有 `import json` 风格；若无则用局部 import）：

```python
def test_metadata_resolve_uses_mod_id_after_folder_rename(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "DDSCache" / "old_c_folder" / "dds_metadata.json",
        json.dumps([{
            "ModID": "mod_c",
            "ModFolderName": "old_c_folder",
            "RelativeImagePath": "graphics\\c.png",
            "DDSFilePath": "\\mods\\DDSCache\\old_c_folder\\graphics\\c.dds",
            "Width": 3,
            "Height": 4,
        }]),
    )
    md = read_dds_metadata(mini_game)
    hit = md.resolve("mod_c", "new_c_folder", "graphics/c.png")
    assert hit is not None
    assert hit.mod_folder == "old_c_folder"
    assert hit.mod_id == "mod_c"


def test_metadata_resolve_prefers_exact_folder(mini_game):
    md = read_dds_metadata(mini_game)
    hit = md.resolve("mod_a", "mod_a", "graphics/ships/h_alpha.png")
    assert hit is not None and hit.mod_folder == "mod_a"


def test_metadata_core_mod_id_is_normalized(mini_game):
    md = read_dds_metadata(mini_game)
    hit = md.resolve("core", "renamed-core", "graphics/ships/h_core.png")
    assert hit is not None and hit.mod_id == "core"


def test_metadata_resolve_ambiguous_mod_id_returns_none(mini_game):
    from conftest import _write
    for folder, rel in (("dup_a", "graphics/dup.png"), ("dup_b", "graphics/dup.png")):
        _write(
            mini_game / "mods" / "DDSCache" / folder / "dds_metadata.json",
            json.dumps([{
                "ModID": "mod_dup",
                "ModFolderName": folder,
                "RelativeImagePath": rel.replace("/", "\\"),
                "DDSFilePath": "\\mods\\DDSCache\\{}\\graphics\\dup.dds".format(folder),
                "Width": 1,
                "Height": 1,
            }]),
        )
    md = read_dds_metadata(mini_game)
    assert md.resolve("mod_dup", "renamed", "graphics/dup.png") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_mod_index.py -q`
Expected: FAIL —— `AttributeError: 'MetadataIndex' object has no attribute 'resolve'`（或 `MetadataEntry` 无 `mod_id`）。

- [ ] **Step 3: 实现**

在 `tools/mod_index.py` 顶部常量区加：

```python
CORE_MOD_ID = "core"
```

在 `CORE_FOLDER` 之后加函数：

```python
def normalize_mod_id(value: str) -> str:
    """DDSCache 给 core 写的 ModID 是 starsector-core；清单/运行时统一用 core。"""
    text = str(value or "")
    return CORE_MOD_ID if text.casefold() == CORE_FOLDER else text
```

把 `MetadataEntry` 改为：

```python
@dataclass(frozen=True)
class MetadataEntry:
    mod_folder: str
    rel: str
    dds_rel: str
    width: int
    height: int
    mod_id: str = ""
```

在 `MetadataIndex` 的 `by_rel` 后加字段与方法：

```python
    by_modid_rel: dict[tuple[str, str], list[MetadataEntry]] = field(default_factory=dict)
    ...
    def resolve(self, mod_id: str, mod_folder: str, rel: str,
                exclude_core: bool = False) -> MetadataEntry | None:
        """按稳定身份 (ModID, 相对路径) 解析；文件夹名只作回退。

        顺序：当前文件夹精确命中 → (ModID, 路径) 唯一命中 → 旧版唯一路径回退。
        文件夹改名后 metadata 的 ModFolderName 仍是旧名，但 ModID 不变，
        第二步能把条目重新绑到当前 mod。
        """
        key = (mod_folder.casefold(), rel.casefold())
        hit = self.by_key.get(key)
        if hit is not None:
            if exclude_core and hit.mod_folder.casefold() == CORE_FOLDER:
                return None
            return hit
        candidates = [
            me
            for me in (self.by_modid_rel.get(
                (normalize_mod_id(mod_id).casefold(), rel.casefold())
            ) or [])
            if not (exclude_core and me.mod_folder.casefold() == CORE_FOLDER)
        ]
        if len(candidates) == 1:
            return candidates[0]
        return self.get(mod_folder, rel, exclude_core=exclude_core)
```

在 `read_dds_metadata` 的记录解析处，把 `MetadataEntry(...)` 构造改为：

```python
                mod_folder = str(record.get("ModFolderName") or entry.name)
                rel = _norm_rel(str(record.get("RelativeImagePath") or ""))
                if not rel:
                    raise ValueError("empty RelativeImagePath")
                dds_rel = _norm_rel(str(record.get("DDSFilePath") or ""))
                mod_id = normalize_mod_id(str(record.get("ModID") or mod_folder))
                me = MetadataEntry(
                    mod_folder,
                    rel,
                    dds_rel,
                    int(record.get("Width") or 0),
                    int(record.get("Height") or 0),
                    mod_id,
                )
```

在 `index.by_key[...] = me` 之后加：

```python
            index.by_modid_rel.setdefault(
                (me.mod_id.casefold(), rel.casefold()), []
            ).append(me)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_mod_index.py -q`
Expected: PASS（含既有 11 个测试；`test_metadata_index_backslash_and_fallback` 等不回归）。

- [ ] **Step 5: 提交**

```bash
git add tools/mod_index.py tests/tools/test_mod_index.py
git commit -m "feat(m2): add stable mod-id metadata identity"
```

---

### Task 2: Manifest 生成器 — 稳定解析、覆盖率、per-mod 汇总、tier override

**Files:**
- Modify: `tools/manifest_builder.py`（`_sprite_entry`、`_metadata_entry`、新增 `apply_tier_overrides` / `build_mods_summary` / `load_tier_overrides`、`build_manifest`）
- Modify: `tools/gen_manifest.py`（`--tiers`）
- Test: `tests/tools/test_manifest_builder.py`

**Interfaces:**
- Consumes:
  - Task 1 的 `MetadataEntry.mod_id`、`MetadataIndex.resolve(mod_id, mod_folder, rel, exclude_core=False)`、`normalize_mod_id`
  - 既有 `scan_mods` / `build_lookup` / `read_dds_metadata` / `build_closure` / `core_assets_result`
- Produces:
  - `build_manifest(game_root, scope="mod_non_shader", include_core=True, include_l2=True, variant_limit=0, tier_overrides: dict[str, str] | None = None) -> BuildResult`
  - `load_tier_overrides(path: Path) -> dict[str, str]`
  - `apply_tier_overrides(layers, overrides, known_ids) -> tuple[dict[str, list[dict]], list[str]]`
  - `build_mods_summary(scan, layers, tier_map) -> list[dict]`
  - manifest 顶层新增 `mods: list[dict]`
  - `stats.coverage.baked_expected: int`、`stats.coverage.baked_resolved: int`、`stats.coverage.baked: float`
  - `stats.unresolved_baked: list[str]`（最多 100 条）、`stats.unresolved_baked_count: int`
  - `stats.tiers: dict[str, str]`、`stats.tiers_unknown: list[str]`

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_manifest_builder.py` 末尾追加：

```python
def test_renamed_mod_folder_resolves_by_mod_id(mini_game):
    from conftest import _png, _write
    p = mini_game / "mods" / "mod_b" / "graphics" / "renamed.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_png(6, 8))
    dds = mini_game / "mods" / "DDSCache" / "old_b" / "graphics" / "renamed.dds"
    dds.parent.mkdir(parents=True, exist_ok=True)
    dds.write_bytes(b"DDS ")
    _write(
        mini_game / "mods" / "DDSCache" / "old_b" / "dds_metadata.json",
        json.dumps([{
            "ModID": "mod_b",
            "ModFolderName": "old_b",
            "RelativeImagePath": "graphics\\renamed.png",
            "DDSFilePath": "\\mods\\DDSCache\\old_b\\graphics\\renamed.dds",
            "Width": 6,
            "Height": 8,
        }]),
    )
    m = _build(mini_game, include_l2=False)
    entry = next(e for e in m["layers"]["L3"] if e["path"] == "graphics/renamed.png")
    assert entry["modId"] == "mod_b"
    assert Path(entry["absolutePath"]) == (
        mini_game / "mods" / "mod_b" / "graphics" / "renamed.png"
    ).resolve()
    assert m["stats"]["coverage"]["baked"] == 1.0
    assert m["stats"]["unresolved_baked_count"] == 0


def test_missing_source_is_unresolved(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "DDSCache" / "mod_a" / "dds_metadata.json",
        json.dumps([{
            "ModID": "mod_a",
            "ModFolderName": "mod_a",
            "RelativeImagePath": "graphics\\missing.png",
            "DDSFilePath": "\\mods\\DDSCache\\mod_a\\graphics\\missing.dds",
            "Width": 1,
            "Height": 1,
        }]),
    )
    m = _build(mini_game, include_l2=False)
    assert m["stats"]["coverage"]["baked"] < 1.0
    assert m["stats"]["unresolved_baked_count"] >= 1


def test_mods_summary_sums_match_layers(mini_game):
    m = _build(mini_game)
    sums = {
        layer: sum(row["layers"][layer] for row in m["mods"])
        for layer in ("L1", "L2", "L3")
    }
    assert sums == {layer: len(m["layers"][layer]) for layer in ("L1", "L2", "L3")}
    assert any(row["modId"] == "core" for row in m["mods"])


def test_tier_override_moves_whole_mod(mini_game):
    m = _build(mini_game, include_l2=False, tier_overrides={"mod_a": "L3"})
    assert all(e["modId"] != "mod_a" for e in m["layers"]["L1"])
    assert any(e["modId"] == "mod_a" for e in m["layers"]["L3"])
    summary = {row["modId"]: row for row in m["mods"]}
    assert summary["mod_a"]["tier"] == "L3"
    assert summary["mod_a"]["layers"]["L1"] == 0
    assert m["stats"]["tiers"] == {"mod_a": "L3"}


def test_unknown_tier_mod_is_reported_not_applied(mini_game):
    m = _build(mini_game, tier_overrides={"no_such_mod": "L1"})
    assert m["stats"]["tiers_unknown"] == ["no_such_mod"]
    assert "no_such_mod" not in m["stats"]["tiers"]


def test_invalid_tier_raises(mini_game):
    import pytest
    with pytest.raises(ValueError):
        _build(mini_game, tier_overrides={"mod_a": "L9"})


def test_same_path_first_enabled_wins(mini_game):
    """mod_a 与 mod_b 都有 graphics/ships/h_alpha.png；enabled 顺序 mod_a 在前。"""
    m = _build(mini_game, include_l2=False)
    hits = [
        e for e in m["layers"]["L1"] + m["layers"]["L2"] + m["layers"]["L3"]
        if e["path"] == "graphics/ships/h_alpha.png"
    ]
    assert len(hits) == 1
    assert hits[0]["modId"] == "mod_a"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_manifest_builder.py -q`
Expected: FAIL —— `KeyError: 'baked'` / `KeyError: 'mods'` / `TypeError: build_manifest() got an unexpected keyword argument 'tier_overrides'`。

- [ ] **Step 3: 实现**

**(a) 导入与常量。** 在 `tools/manifest_builder.py` 顶部：

```python
import json
from pathlib import Path
...
from mod_index import (
    CORE_FOLDER,
    MetadataEntry,
    ...
)
...
SCHEMA = 1
LAYERS = ("L1", "L2", "L3")
```

**(b) 新助手函数**（放在 `_folder_path` 之后）：

```python
def load_tier_overrides(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    mods = data.get("mods") if isinstance(data, dict) else None
    if not isinstance(mods, dict):
        raise ValueError('tiers file must be {"mods": {"<modId>": "L1|L2|L3"}}')
    return {str(k): str(v).upper() for k, v in mods.items()}


def apply_tier_overrides(layers: dict[str, list[dict]], overrides: dict[str, str],
                         known_ids: set[str]) -> tuple[dict[str, list[dict]], list[str]]:
    """把指定 mod 的全部条目移到目标层；未知 mod 只报告、不移动。"""
    if not overrides:
        return {name: list(layers.get(name, [])) for name in LAYERS}, []
    forced: dict[str, str] = {}
    unknown: list[str] = []
    for raw_key, raw_layer in overrides.items():
        key = str(raw_key).casefold()
        layer = str(raw_layer).upper()
        if layer not in LAYERS:
            raise ValueError(f"unknown tier {raw_layer!r} for mod {raw_key!r}")
        if key not in known_ids:
            unknown.append(str(raw_key))
            continue
        forced[key] = layer
    out: dict[str, list[dict]] = {name: [] for name in LAYERS}
    seen: dict[str, set[tuple[str, str]]] = {name: set() for name in LAYERS}
    for name in LAYERS:
        for entry in layers.get(name, []):
            target = forced.get(str(entry.get("modId", "")).casefold(), name)
            key = (
                str(entry.get("modId", "")).casefold(),
                str(entry.get("path", "")).casefold(),
            )
            if key in seen[target]:
                continue
            seen[target].add(key)
            out[target].append(entry)
    return out, unknown


def build_mods_summary(scan, layers: dict[str, list[dict]],
                       tier_map: dict[str, str]) -> list[dict]:
    """每个 mod 的分层条目数；包含零纹理 mod，保证 validator 能守恒校验。"""
    agg: dict[str, dict] = {}
    for name in LAYERS:
        for entry in layers.get(name, []):
            mid = str(entry.get("modId", "unknown"))
            rec = agg.setdefault(mid.casefold(), {
                "modId": mid,
                "folder": "",
                "order": -1,
                "baked": 0,
                "unbaked": 0,
                "layers": {layer: 0 for layer in LAYERS},
            })
            rec["layers"][name] += 1
            if entry.get("baked"):
                rec["baked"] += 1
            else:
                rec["unbaked"] += 1
    for mod in scan.mods:
        mid = "core" if mod.is_core else mod.mod_id
        rec = agg.setdefault(mid.casefold(), {
            "modId": mid,
            "folder": "",
            "order": -1,
            "baked": 0,
            "unbaked": 0,
            "layers": {layer: 0 for layer in LAYERS},
        })
        rec["folder"] = CORE_FOLDER if mod.is_core else mod.folder.name
        rec["order"] = mod.order
    out = []
    for key, rec in agg.items():
        rec["tier"] = tier_map.get(key, "auto")
        out.append(rec)
    out.sort(key=lambda r: (
        r["order"] if r["order"] >= 0 else 10 ** 9,
        r["modId"].casefold(),
    ))
    return out
```

**(c) `_sprite_entry`**：把 metadata 查找改成 `resolve`，`owner_key` 改用 mod id。

```python
def _sprite_entry(
    rel: str,
    lookup: AssetLookup,
    metadata: MetadataIndex,
    game_root: Path,
    include_core: bool = True,
) -> tuple[dict, tuple[str, str] | None]:
    root = Path(game_root).resolve()
    owner = pick(lookup.images.get(rel.casefold()) or [])
    meta: MetadataEntry | None = None
    if owner is not None:
        meta = metadata.resolve(
            owner.mod_id, owner.folder.name, rel, exclude_core=not include_core
        )
    else:
        candidates = [
            me
            for me in (metadata.by_rel.get(rel.casefold()) or [])
            if include_core or me.mod_folder.casefold() != CORE_FOLDER
        ]
        if len(candidates) == 1:
            meta = candidates[0]

    if owner is not None:
        absolute = owner.absolute.resolve().as_posix()
        mod_id = owner.mod_id
    elif meta is not None:
        absolute = (_folder_path(root, meta.mod_folder) / meta.rel).resolve().as_posix()
        mod_id = "core" if meta.mod_folder.casefold() == CORE_FOLDER else meta.mod_folder
    else:
        absolute = ""
        mod_id = "unknown"

    dds = None
    w = h = 0
    baked = False
    src = "spec_scan"
    if meta is not None:
        baked = True
        src = "dds_metadata"
        w, h = meta.width, meta.height
        if meta.dds_rel:
            dds = (root / meta.dds_rel).resolve().as_posix()
    elif owner is not None:
        w, h = probe(owner.absolute)
        src = "header_probe" if w and h else "spec_scan"

    owner_key = None
    if owner is not None:
        owner_key = (owner.mod_id.casefold(), rel.casefold())
    elif meta is not None:
        owner_key = (meta.mod_id.casefold(), meta.rel.casefold())
    return _entry(mod_id, rel, absolute, dds, w, h, baked, src), owner_key
```

**(d) `_metadata_entry`**：用当前文件夹重建绝对路径。

```python
def _metadata_entry(me: MetadataEntry, game_root: Path,
                    folder_to_id: dict[str, str],
                    folder_by_modid: dict[str, str],
                    current_folders: set[str]) -> dict:
    is_core = me.mod_folder.casefold() == CORE_FOLDER
    if is_core:
        folder = CORE_FOLDER
    elif me.mod_folder.casefold() in current_folders:
        folder = me.mod_folder
    else:
        folder = folder_by_modid.get(me.mod_id.casefold(), me.mod_folder)
    absolute = (_folder_path(game_root, folder) / me.rel).resolve().as_posix()
    dds = (
        (Path(game_root).resolve() / me.dds_rel).resolve().as_posix()
        if me.dds_rel
        else None
    )
    if is_core:
        mod_id = "core"
    else:
        mod_id = folder_to_id.get(folder.casefold()) or me.mod_id or folder
    return _entry(
        mod_id, me.rel, absolute, dds, me.width, me.height, True, "dds_metadata"
    )
```

**(e) `build_manifest`**：改签名，加入稳定身份集合、tier 应用、覆盖率与 mods 汇总。完整函数体如下（替换原函数）：

```python
def build_manifest(
    game_root: Path,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    variant_limit: int = 0,
    tier_overrides: dict[str, str] | None = None,
) -> BuildResult:
    root = Path(game_root).resolve()
    enabled = load_enabled_ids(root)
    scan = scan_mods(root, enabled, include_core=include_core)
    lookup = build_lookup(scan.mods)
    title = read_title_variants(scan.mods)
    metadata = read_dds_metadata(root)

    enabled_ids = {str(i).casefold() for i in enabled}
    enabled_folders = {m.folder.name.casefold() for m in scan.mods if not m.is_core}
    current_folders = set(enabled_folders)
    folder_by_modid = {
        m.mod_id.casefold(): m.folder.name for m in scan.mods if not m.is_core
    }
    folder_to_id = {m.folder.name.casefold(): m.mod_id for m in scan.mods}
    known_ids = {
        ("core" if m.is_core else m.mod_id).casefold() for m in scan.mods
    }

    l1: list[dict] = []
    seen_paths: set[str] = set()
    seen_meta: set[tuple[str, str]] = set()

    def add_sprite(rel: str) -> None:
        key = rel.casefold()
        if key in seen_paths:
            return
        seen_paths.add(key)
        entry, owner_key = _sprite_entry(
            rel, lookup, metadata, root, include_core=include_core
        )
        l1.append(entry)
        if owner_key:
            seen_meta.add(owner_key)

    core: CoreAssets = core_assets_result(root) if include_core else CoreAssets()
    for rel in core.paths:
        add_sprite(rel)

    title_closure = build_closure(title.ids, lookup)
    for ref in title_closure.sprites.values():
        add_sprite(ref.rel)

    l2: list[dict] = []
    if include_l2:
        variants = sorted(lookup.variants)
        if variant_limit and variant_limit > 0:
            variants = variants[:variant_limit]
        pool = build_closure(variants, lookup)
        for ref in pool.sprites.values():
            key = ref.rel.casefold()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            entry, owner_key = _sprite_entry(
                ref.rel, lookup, metadata, root, include_core=include_core
            )
            l2.append(entry)
            if owner_key:
                seen_meta.add(owner_key)

    l3: list[dict] = []
    l3_keys: set[tuple[str, str]] = set()

    def add_l3(entry: dict) -> None:
        key = (str(entry["modId"]).casefold(), str(entry["path"]).casefold())
        if key in l3_keys:
            return
        l3_keys.add(key)
        l3.append(entry)

    # 同人口：metadata 计数、磁盘图计数、未烘焙计数都只覆盖已启用 mod（含 core）。
    scope_meta = [
        me
        for me in metadata.entries
        if in_scope(me, scope)
        and (
            me.mod_id.casefold() in enabled_ids
            or me.mod_folder.casefold() in enabled_folders
        )
    ]
    core_meta = [
        me
        for me in metadata.entries
        if me.mod_folder.casefold() == CORE_FOLDER and include_core
    ]
    for me in scope_meta + core_meta:
        key = (me.mod_id.casefold(), me.rel.casefold())
        if key in seen_meta:
            continue
        seen_meta.add(key)
        add_l3(
            _metadata_entry(
                me, root, folder_to_id, folder_by_modid, current_folders
            )
        )

    scope_images = []
    core_images = []
    for assets in lookup.images.values():
        for asset in assets:
            if asset.mod_id == "core":
                if include_core:
                    core_images.append(asset)
            elif folder_in_scope(asset.folder.name, scope):
                scope_images.append(asset)
    meta_keys = {
        (me.mod_id.casefold(), me.rel.casefold())
        for me in scope_meta + core_meta
    }
    for asset in scope_images + core_images:
        key = (asset.mod_id.casefold(), asset.rel.casefold())
        if key in meta_keys or asset.rel.casefold() in seen_paths:
            continue
        w, h = probe(asset.absolute)
        add_l3(
            _entry(
                asset.mod_id,
                asset.rel,
                asset.absolute.resolve().as_posix(),
                None,
                w,
                h,
                False,
                "header_probe" if w and h else "spec_scan",
            )
        )

    tiers_normalized = {
        str(k).casefold(): str(v).upper() for k, v in (tier_overrides or {}).items()
    }
    layers, tiers_unknown = apply_tier_overrides(
        {"L1": l1, "L2": l2, "L3": l3}, tier_overrides or {}, known_ids
    )
    l1, l2, l3 = layers["L1"], layers["L2"], layers["L3"]

    path_conflicts: list[dict] = []
    path_records: dict[str, dict] = {}
    for layer_name, entries in (("L1", l1), ("L2", l2), ("L3", l3)):
        for e in entries:
            key = str(e["path"]).casefold()
            rec = path_records.setdefault(
                key, {"path": e["path"], "layers": [], "sizes": []}
            )
            if layer_name not in rec["layers"]:
                rec["layers"].append(layer_name)
            size = f"{e['w']}x{e['h']}"
            if size not in rec["sizes"]:
                rec["sizes"].append(size)
    for rec in path_records.values():
        if len(rec["layers"]) > 1:
            path_conflicts.append(
                {**rec, "content_differs": len(rec["sizes"]) > 1}
            )

    l1_disk = sum(
        1 for e in l1 if e["absolutePath"] and Path(e["absolutePath"]).is_file()
    )
    l1_baked = sum(1 for e in l1 if e["baked"])
    refs_total = sum(
        getattr(title_closure.stats, name)
        for name in (
            "variants_total",
            "hulls_total",
            "weapons_total",
            "wings_total",
        )
    )
    refs_ok = sum(
        getattr(title_closure.stats, name)
        for name in (
            "variants_resolved",
            "hulls_resolved",
            "weapons_resolved",
            "wings_resolved",
        )
    )
    meta_total = len(scope_meta)
    meta_all = len(scope_meta) + len(core_meta)
    meta_seen = sum(
        1
        for me in scope_meta + core_meta
        if (me.mod_id.casefold(), me.rel.casefold()) in seen_meta
    )
    disk_images = len(scope_images)
    scope_meta_keys = {
        (me.mod_id.casefold(), me.rel.casefold()) for me in scope_meta
    }
    unbaked = sum(
        1
        for asset in scope_images
        if (asset.mod_id.casefold(), asset.rel.casefold()) not in scope_meta_keys
    )

    by_meta_key: dict[tuple[str, str], dict] = {}
    for entries in (l1, l2, l3):
        for entry in entries:
            by_meta_key[
                (str(entry["modId"]).casefold(), str(entry["path"]).casefold())
            ] = entry
    baked_expected = len(scope_meta) + len(core_meta)
    baked_resolved = 0
    unresolved: list[str] = []
    for me in scope_meta + core_meta:
        entry = by_meta_key.get((me.mod_id.casefold(), me.rel.casefold()))
        absolute_ok = (
            entry is not None
            and bool(entry.get("absolutePath"))
            and Path(str(entry["absolutePath"])).is_file()
        )
        dds_ok = (
            entry is not None
            and bool(entry.get("ddsPath"))
            and Path(str(entry["ddsPath"])).is_file()
        )
        if absolute_ok and dds_ok:
            baked_resolved += 1
        else:
            unresolved.append(f"{me.mod_id}/{me.rel}")
    unresolved.sort()

    closure_stats = title_closure.stats
    manifest = {
        "schema": SCHEMA,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline": {
            "game": "0.98a-RC8",
            "fr": None,
            "enabled_mods": len(enabled),
        },
        "scope": scope,
        "include_core": include_core,
        "layers": {"L1": l1, "L2": l2, "L3": l3},
        "mods": build_mods_summary(
            scan, {"L1": l1, "L2": l2, "L3": l3}, tiers_normalized
        ),
        "stats": {
            "scope": scope,
            "include_core": include_core,
            "metadata_entries": meta_total,
            "metadata_entries_scope": meta_total,
            "metadata_entries_core": len(core_meta),
            "metadata_entries_all": len(metadata.entries),
            "metadata_unused": len(metadata.entries) - meta_all,
            "baked": meta_total,
            "unbaked": unbaked,
            "disk_images": disk_images,
            "core_entries": len(core_meta),
            "l1_count": len(l1),
            "l2_count": len(l2),
            "l3_count": len(l3),
            "closure": {
                "variants": [closure_stats.variants_total, closure_stats.variants_resolved],
                "hulls": [closure_stats.hulls_total, closure_stats.hulls_resolved],
                "weapons": [closure_stats.weapons_total, closure_stats.weapons_resolved],
                "wings": [closure_stats.wings_total, closure_stats.wings_resolved],
            },
            "coverage": {
                "l1_sprite_disk": (l1_disk / len(l1)) if l1 else 0.0,
                "l1_baked": (l1_baked / len(l1)) if l1 else 1.0,
                "closure_refs": (refs_ok / refs_total) if refs_total else 1.0,
                "metadata": (
                    0.0
                    if metadata.parse_errors
                    else ((meta_seen / meta_all) if meta_all else None)
                ),
                "baked_expected": baked_expected,
                "baked_resolved": baked_resolved,
                "baked": (baked_resolved / baked_expected) if baked_expected else 1.0,
            },
            "unresolved_baked": unresolved[:100],
            "unresolved_baked_count": len(unresolved),
            "tiers": {
                key: layer for key, layer in tiers_normalized.items()
                if key in known_ids
            },
            "tiers_unknown": tiers_unknown,
            "missing": closure_stats.missing,
            "parse_errors": closure_stats.parse_errors,
            "path_conflicts": path_conflicts,
            "conflicts": {
                "duplicate_mod_ids": scan.duplicate_ids,
                "mod_parse_errors": scan.parse_errors,
                "missing_mod_ids": scan.missing_ids,
            },
            "metadata_fallback_hits": metadata.fallback_hits,
            "metadata_parse_errors": metadata.parse_errors,
            "core_parse_errors": core.parse_errors,
            "core_parse_errors_skipped": not include_core,
            "source_mode": "disk_scan" if meta_all == 0 else "dds_metadata",
            "precedence": "enabled_order_then_core",
        },
    }
    warnings = []
    if scan.missing_ids:
        warnings.append(f"missing mods: {scan.missing_ids}")
    if scan.duplicate_ids:
        warnings.append(f"duplicate mod ids: {scan.duplicate_ids}")
    if tiers_unknown:
        warnings.append(f"unknown tier mods: {tiers_unknown}")
    return BuildResult(manifest, warnings)
```

**(f) `tools/gen_manifest.py`**：加 `--tiers`。

```python
from manifest_builder import build_manifest, load_tier_overrides
...
    parser.add_argument("--tiers", type=Path,
                        help='JSON: {"mods": {"<modId>": "L1|L2|L3"}}')
...
    result = build_manifest(
        args.game_root,
        scope=args.scope,
        include_core=not args.no_core,
        include_l2=not args.no_l2,
        variant_limit=args.variant_limit,
        tier_overrides=load_tier_overrides(args.tiers) if args.tiers else {},
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_manifest_builder.py tests/tools/test_mod_index.py -q`
Expected: PASS。既有 `test_scope_and_stats` 仍为 `metadata_entries == 2`、`coverage.metadata == 1.0`；新测试全绿。

- [ ] **Step 5: 提交**

```bash
git add tools/manifest_builder.py tools/gen_manifest.py tests/tools/test_manifest_builder.py
git commit -m "feat(m2): resolve manifest entries by stable mod id and add per-mod tiers"
```

---

### Task 3: Validator — 100% 烘焙覆盖、per-mod 守恒、tier 校验

**Files:**
- Modify: `tools/validate_manifest.py:122-192`（覆盖率与 stats 检查之后追加）
- Test: `tests/tools/test_validate_manifest.py`

**Interfaces:**
- Consumes: Task 2 的 `stats.coverage.baked`、`stats.unresolved_baked_count`、`stats.unresolved_baked`、`manifest.mods[].layers`、`manifest.mods[].tier`
- Produces: 新增 findings codes — `coverage_baked`、`baked_unresolved`、`mods_summary`、`mods_tier`、`duplicate_mod_summary`、`mods_layer_mismatch`。旧 manifest（无这些字段）保持通过。

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_validate_manifest.py` 末尾追加：

```python
def test_baked_coverage_below_one_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"]["baked"] = 0.5
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "coverage_baked" in codes


def test_baked_unresolved_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["unresolved_baked"] = ["mod_a/graphics/x.png"]
    m["stats"]["unresolved_baked_count"] = 1
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "baked_unresolved" in codes


def test_mods_layer_mismatch_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["mods"][0]["layers"]["L1"] += 1
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "mods_layer_mismatch" in codes


def test_duplicate_mod_summary_is_important(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["mods"].append(copy.deepcopy(m["mods"][0]))
    sev = {(f.code, f.severity) for f in validate(m, mini_game)}
    assert ("duplicate_mod_summary", "Important") in sev


def test_bad_mods_tier_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["mods"][0]["tier"] = "L9"
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "mods_tier" in codes


def test_old_manifest_without_new_fields_passes(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m.pop("mods", None)
    for key in ("baked_expected", "baked_resolved", "baked"):
        m["stats"]["coverage"].pop(key, None)
    m["stats"].pop("unresolved_baked", None)
    m["stats"].pop("unresolved_baked_count", None)
    assert _good(m, mini_game) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_validate_manifest.py -q`
Expected: FAIL —— 新 code 未出现（`assert "coverage_baked" in codes` 失败）。

- [ ] **Step 3: 实现**

在 `tools/validate_manifest.py` 的 `validate()` 末尾、`return findings` 之前插入：

```python
    baked_cov = coverage.get("baked")
    if baked_cov is not None and float(baked_cov) < 1.0:
        findings.append(
            Finding("Critical", "coverage_baked", f"baked={baked_cov} < 1.0")
        )
    unresolved_count = stats.get("unresolved_baked_count")
    if unresolved_count:
        sample = stats.get("unresolved_baked") or []
        findings.append(
            Finding(
                "Critical",
                "baked_unresolved",
                f"{unresolved_count} enabled baked texture(s) unresolved: "
                + ", ".join(str(x) for x in sample[:5]),
            )
        )

    mods_summary = manifest.get("mods")
    if mods_summary is not None:
        if not isinstance(mods_summary, list):
            findings.append(
                Finding("Critical", "mods_summary", "mods must be a list")
            )
        else:
            seen_mods: set[str] = set()
            sums = {"L1": 0, "L2": 0, "L3": 0}
            for item in mods_summary:
                if not isinstance(item, dict):
                    findings.append(
                        Finding("Critical", "mods_summary", "mods entry is not an object")
                    )
                    continue
                mid = item.get("modId")
                item_layers = item.get("layers")
                if not isinstance(mid, str) or not mid:
                    findings.append(
                        Finding("Critical", "mods_summary", f"bad modId {mid!r}")
                    )
                    continue
                if mid.casefold() in seen_mods:
                    findings.append(
                        Finding("Important", "duplicate_mod_summary", mid)
                    )
                seen_mods.add(mid.casefold())
                tier = item.get("tier")
                if tier not in (None, "auto", "L1", "L2", "L3"):
                    findings.append(
                        Finding("Critical", "mods_tier", f"{mid}: bad tier {tier!r}")
                    )
                if (
                    not isinstance(item_layers, dict)
                    or any(not isinstance(item_layers.get(k), int) for k in sums)
                ):
                    findings.append(
                        Finding("Critical", "mods_summary", f"{mid}: bad layers")
                    )
                    continue
                for k in sums:
                    sums[k] += item_layers[k]
            for k, total in sums.items():
                expected = len(layers[k]) if isinstance(layers[k], list) else 0
                if total != expected:
                    findings.append(
                        Finding(
                            "Critical",
                            "mods_layer_mismatch",
                            f"{k}: summary={total} != entries={expected}",
                        )
                    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_validate_manifest.py tests/tools/test_manifest_builder.py -q`
Expected: PASS（既有 validator 测试 + 6 个新测试）。

- [ ] **Step 5: 提交**

```bash
git add tools/validate_manifest.py tests/tools/test_validate_manifest.py
git commit -m "feat(m2): gate baked coverage and per-mod manifest sums"
```

---

### Task 4: L1 闭包根 id 的 wing/hull 回退（L1 精确化）

**Files:**
- Modify: `tools/sprite_closure.py:278-290`（`build_closure`）
- Test: `tests/tools/test_sprite_closure.py`、`tests/tools/test_manifest_builder.py`

**Interfaces:**
- Consumes: `AssetLookup.wings`（`read_wing_map`）、`AssetLookup.ships`、`AssetLookup.skins`、`_Walker.add_wing`
- Produces: `build_closure(variant_ids, lookup)` 签名不变；标题 CSV 里写成 wing/hull id 的根 id 现在会被解析，不再记 `missing.variant`。

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_sprite_closure.py` 末尾追加：

```python
def test_title_wing_id_resolves_via_wing_map(mini_game):
    from mod_index import load_enabled_ids, scan_mods
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    lookup = build_lookup(scan.mods)
    result = build_closure(["wing_one"], lookup)
    assert "graphics/ships/h_fighter.png" in result.sprites
    assert "wing_one" not in result.stats.missing.get("variant", [])
    assert result.stats.wings_resolved == 1


def test_unknown_root_id_still_records_variant_miss(mini_game):
    from mod_index import load_enabled_ids, scan_mods
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    lookup = build_lookup(scan.mods)
    result = build_closure(["no_such_variant"], lookup)
    assert "no_such_variant" in result.stats.missing.get("variant", [])
```

在 `tests/tools/test_manifest_builder.py` 末尾追加：

```python
def test_title_csv_wing_id_adds_its_sprites(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "config" / "title_screen_variants.csv",
        "variant id\nva_one\nwing_one\n",
    )
    m = _build(mini_game, include_l2=False)
    paths = {e["path"] for e in m["layers"]["L1"]}
    assert "graphics/ships/h_fighter.png" in paths
    assert "wing_one" not in m["stats"]["missing"].get("variant", [])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_sprite_closure.py -q`
Expected: FAIL —— `assert "wing_one" not in result.stats.missing.get("variant", [])`（当前 `wing_one` 被当 variant，记 missing）。

- [ ] **Step 3: 实现**

把 `build_closure` 替换为：

```python
def build_closure(variant_ids: list[str], lookup: AssetLookup) -> ClosureResult:
    walker = _Walker(lookup)
    for vid in variant_ids:
        # 标题 CSV 偶尔直接写 wing id / hull id（valk_*、hii_* 等 17 条）。
        # 先按真实 variant 解析；解析不到再尝试 wing/hull 身份，最后才记 miss。
        if pick(lookup.variants.get(vid) or []) is not None:
            walker.add_variant(vid)
        elif vid in lookup.wings or vid in lookup.ships or vid in lookup.skins:
            walker.add_wing(vid)
        else:
            walker.add_variant(vid)
    if lookup.skin_errors:
        walker.result.stats.parse_errors.setdefault("skin", []).extend(
            sorted(lookup.skin_errors)
        )
    for key in ("missing", "parse_errors"):
        bucket = getattr(walker.result.stats, key)
        for names in bucket.values():
            names.sort()
    return walker.result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_sprite_closure.py tests/tools/test_manifest_builder.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tools/sprite_closure.py tests/tools/test_sprite_closure.py tests/tools/test_manifest_builder.py
git commit -m "fix(m2): resolve title wing and hull ids before declaring a miss"
```

---

### Task 5: 可重生成的安装器（任意游戏安装）

**Files:**
- Create: `tools/install_manifest.py`
- Test: `tests/tools/test_install_manifest.py`（新建）

**Interfaces:**
- Consumes: Task 2 `build_manifest(..., tier_overrides=...)` / `load_tier_overrides`；`trim_manifest.trim(data)`；`validate_manifest.validate(manifest, game_root, min_coverage=0.95, max_l1=8000)`
- Produces:
  - `InstallResult(full: dict, runtime: dict, out: Path, findings: list[Finding])`
  - `install(game_root: Path, out: Path | None = None, *, tiers: dict[str, str] | None = None, scope: str = "mod_non_shader", include_core: bool = True, include_l2: bool = True, max_l1: int = 8000) -> InstallResult`
  - CLI：`python -I tools/install_manifest.py --game-root <game> [--out <file>] [--tiers <json>] [--scope ...] [--no-core] [--no-l2] [--max-l1 8000]`

- [ ] **Step 1: 写失败测试**

新建 `tests/tools/test_install_manifest.py`：

```python
import json

from install_manifest import DEFAULT_REL, install


def test_install_writes_runtime_manifest(mini_game):
    result = install(mini_game)
    assert result.out == mini_game / DEFAULT_REL
    assert result.out.is_file()
    data = json.loads(result.out.read_text(encoding="utf-8"))
    assert data["schema"] == "hypernova-runtime-1"
    assert len(data["layers"]["L1"]) == len(result.full["layers"]["L1"])
    assert not any(f.severity == "Critical" for f in result.findings)


def test_install_refuses_to_write_when_critical(mini_game):
    out = mini_game / "runtime.json"
    result = install(mini_game, out=out, max_l1=1)
    assert any(f.severity == "Critical" for f in result.findings)
    assert not out.exists()


def test_install_is_idempotent(mini_game):
    out = mini_game / "runtime.json"
    install(mini_game, out=out)
    first = out.read_bytes()
    install(mini_game, out=out)
    assert out.read_bytes() == first


def test_install_applies_tiers(mini_game):
    out = mini_game / "runtime.json"
    result = install(mini_game, out=out, tiers={"mod_a": "L3"})
    assert all(e["modId"] != "mod_a" for e in result.full["layers"]["L1"])
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert all(e["modId"] != "mod_a" for e in runtime["layers"]["L1"])
    assert any(e["modId"] == "mod_a" for e in runtime["layers"]["L3"])


def test_install_rejects_invalid_tier(mini_game):
    import pytest
    with pytest.raises(ValueError):
        install(mini_game, out=mini_game / "runtime.json", tiers={"mod_a": "L9"})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_install_manifest.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'install_manifest'`。

- [ ] **Step 3: 实现**

新建 `tools/install_manifest.py`：

```python
#!/usr/bin/env python3
"""为一个真实游戏安装生成、校验并落盘运行时 manifest。

用法:
    python -I tools/install_manifest.py --game-root Starsector-098-260mods
    python -I tools/install_manifest.py --game-root <game> --out <file>
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manifest_builder import build_manifest, load_tier_overrides  # noqa: E402
from trim_manifest import trim  # noqa: E402
from validate_manifest import Finding, validate  # noqa: E402

DEFAULT_REL = Path(
    "mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json"
)


@dataclass(frozen=True)
class InstallResult:
    full: dict
    runtime: dict
    out: Path
    findings: list[Finding]


def install(
    game_root: Path,
    out: Path | None = None,
    *,
    tiers: dict[str, str] | None = None,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    max_l1: int = 8000,
) -> InstallResult:
    root = Path(game_root).resolve()
    target = Path(out) if out is not None else root / DEFAULT_REL
    built = build_manifest(
        root,
        scope=scope,
        include_core=include_core,
        include_l2=include_l2,
        tier_overrides=tiers or {},
    )
    findings = validate(built.manifest, root, max_l1=max_l1)
    critical = any(f.severity == "Critical" for f in findings)
    runtime: dict = {}
    if not critical:
        runtime = trim(built.manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(runtime, fh, ensure_ascii=False, separators=(",", ":"))
    return InstallResult(built.manifest, runtime, target, findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tiers", type=Path,
                        help='JSON: {"mods": {"<modId>": "L1|L2|L3"}}')
    parser.add_argument("--scope", default="mod_non_shader",
                        choices=["mod_non_shader", "all_mod_metadata"])
    parser.add_argument("--no-core", action="store_true")
    parser.add_argument("--no-l2", action="store_true")
    parser.add_argument("--max-l1", type=int, default=8000)
    args = parser.parse_args(argv)
    tiers = load_tier_overrides(args.tiers) if args.tiers else {}
    result = install(
        args.game_root,
        out=args.out,
        tiers=tiers,
        scope=args.scope,
        include_core=not args.no_core,
        include_l2=not args.no_l2,
        max_l1=args.max_l1,
    )
    stats = result.full["stats"]
    print(
        "full: L1={l1} L2={l2} L3={l3} baked={baked}/{expected} "
        "unresolved={unresolved}".format(
            l1=stats["l1_count"],
            l2=stats["l2_count"],
            l3=stats["l3_count"],
            baked=stats["coverage"]["baked_resolved"],
            expected=stats["coverage"]["baked_expected"],
            unresolved=stats["unresolved_baked_count"],
        )
    )
    for finding in result.findings:
        print(f"[{finding.severity}] {finding.code}: {finding.message}")
    if any(f.severity == "Critical" for f in result.findings):
        print("FATAL: manifest not written (Critical findings)", file=sys.stderr)
        return 1
    print(f"installed: {result.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_install_manifest.py -q`
Expected: PASS（5 个测试）。

- [ ] **Step 5: 提交**

```bash
git add tools/install_manifest.py tests/tools/test_install_manifest.py
git commit -m "feat(m2): add a per-install manifest installer with validation gate"
```

---

### Task 6: 启动自检只取 L1（REQ-R1-05）

**Files:**
- Modify: `src/main/java/hypernova/HypernovaPlugin.java:174-209`（`runFallbackSelfCheck`）
- Test: `tests/java/hypernova/StartupSelfCheckTest.java`（新建）

**Interfaces:**
- Consumes: `hypernova.manifest.TextureManifest.pathsInLayer(Layer.L1)`
- Produces: `static List<String> selfCheckCandidates(TextureManifest manifest, java.util.function.Predicate<String> loaded, int limit)`（包级可见，供测试）

- [ ] **Step 1: 写失败测试**

新建 `tests/java/hypernova/StartupSelfCheckTest.java`：

```java
package hypernova;

import hypernova.manifest.TextureManifest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StartupSelfCheckTest {

    private static JSONObject entry(String path) throws Exception {
        JSONObject e = new JSONObject();
        e.put("path", path);
        e.put("modId", "m");
        return e;
    }

    private static JSONObject manifest(Object... layers) throws Exception {
        JSONObject root = new JSONObject();
        JSONObject l = new JSONObject();
        for (int i = 0; i < layers.length; i += 2) {
            JSONArray arr = new JSONArray();
            for (Object o : (List<?>) layers[i + 1]) {
                arr.put(o);
            }
            l.put((String) layers[i], arr);
        }
        root.put("layers", l);
        return root;
    }

    @Test
    void candidatesComeOnlyFromL1() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png")),
                "L2", List.of(entry("b.png")),
                "L3", List.of(entry("c.png"))));
        assertEquals(List.of("a.png"),
                HypernovaPlugin.selfCheckCandidates(m, p -> false, 10));
    }

    @Test
    void loadedAndLimitAreHonored() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png"), entry("b.png"), entry("c.png")),
                "L2", List.of(),
                "L3", List.of()));
        assertEquals(List.of("b.png", "c.png"),
                HypernovaPlugin.selfCheckCandidates(m, "a.png"::equals, 2));
    }

    @Test
    void zeroLimitReturnsEmpty() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png")),
                "L2", List.of(),
                "L3", List.of()));
        assertEquals(List.of(),
                HypernovaPlugin.selfCheckCandidates(m, p -> false, 0));
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-tests.sh StartupSelfCheckTest`
Expected: 编译失败 —— `selfCheckCandidates` 不存在。

- [ ] **Step 3: 实现**

在 `HypernovaPlugin` 中：

1. 顶部 import 增加：

```java
import java.util.ArrayList;
import java.util.function.Predicate;
```

2. 在 `runFallbackSelfCheck` 之前加：

```java
    /**
     * 启动期只允许 L1 进入本组件队列（REQ-R1-05）。自检是唯一会在
     * 主线程早期取路径的入口，因此这里把候选集硬限制在 L1；L2/L3
     * 只能由运行期触发点按各自层入队。
     */
    static List<String> selfCheckCandidates(TextureManifest manifest,
                                            Predicate<String> loaded,
                                            int limit) {
        List<String> out = new ArrayList<>();
        if (limit <= 0) {
            return out;
        }
        for (String path : manifest.pathsInLayer(hypernova.manifest.Layer.L1)) {
            if (loaded.test(path)) {
                continue;
            }
            out.add(path);
            if (out.size() >= limit) {
                break;
            }
        }
        return out;
    }
```

3. 把 `runFallbackSelfCheck` 开头的候选收集替换为：

```java
        List<String> candidates = selfCheckCandidates(manifest, service::isLoaded, limit);
        log.info("selfcheck: layer=L1 candidates(not-yet-registered)=" + candidates.size());
```

删除原来跨 `Layer.values()` 的三层循环及其 `java.util.ArrayList` 全限定写法。

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-tests.sh StartupSelfCheckTest`
Expected: PASS（3/3）。

再跑全量 Java 套件：
Run: `bash tools/java/run-tests.sh`
Expected: **103 found / 103 pass / 0 fail**（既有套件的实测值；计划早期估计的 110+/109+ 偏高，以实测为准）。

- [ ] **Step 5: 提交**

```bash
git add src/main/java/hypernova/HypernovaPlugin.java tests/java/hypernova/StartupSelfCheckTest.java
git commit -m "fix(m2): restrict startup self-check candidates to L1"
```

---

### Task 7: 验收、结果文档与记忆钩子

**Files:**
- Create: `docs/m2-results.md`
- Modify: `技术笔记-纹理按需加载.md`（§5.4 字段说明、§7 M2 状态、ADR-05 补记）
- Modify: `C:/Users/qwe13/.claude/projects/D--github-Hypernova-Infinite-Engine/memory/hn-next-session.md`、`hn-architecture.md`、`MEMORY.md`（新里程碑状态）
- Evidence: `build/m2/260mods/manifest-v1.json`、`build/m2/base/manifest-v1.json`、validator 输出、pytest/JUnit 输出、smoke JSON

**Interfaces:**
- Consumes: Task 1-6 的全部产出
- Produces: `docs/m2-results.md`；下次会话钩子（先读该文件 + `hn-next-session`）

- [ ] **Step 1: 260mods 生成 + 校验（真实安装）**

```bash
mkdir -p build/m2/260mods
python -I tools/gen_manifest.py --game-root Starsector-098-260mods \
  --out build/m2/260mods/manifest-v1.json
python -I tools/validate_manifest.py \
  --manifest build/m2/260mods/manifest-v1.json \
  --game-root Starsector-098-260mods
```

Expected（全部以实测为准，不符按 escape hatch 报告）：
- validator **exit 0，0 Critical**；260mods 会打印 **1 条聚合既有 `cross_layer_duplicate` Important（覆盖 44 个 key）**（同路径跨层，L1 优先；R8），这是预期，不是失败。
- `l1_count=6624`、`l2_count=18525`、`l3_count=55444`（10 张由 L2 升 L1；R10）。
- `coverage.baked_expected=80286`（稳定 ModID 多纳入 8 条；R9）、`baked_resolved` 相等、`baked=1.0`、`unresolved_baked_count=0`。
- `closure.variants=[1803,1803]`、`closure.wings=[354,354]`（实测；17 个 wing 根 id 中 10 个早已通过 FIGHTER hull 计入 wings，另带出 6 个新 variant）、`closure_refs=1.0`。
- `mods` 257 行；三层求和 = 6,624 / 18,525 / 55,444。

若 `l1_count` 或闭包数字不同：记录实际值，检查是否有新的 title CSV/mod 变化；**不要**改断言来掩盖。

- [ ] **Step 2: Base 生成 + 校验（stock 有 DDSCache；另验无缓存降级）**

```bash
mkdir -p build/m2/base
python -I tools/gen_manifest.py --game-root Starsector-098-Base \
  --out build/m2/base/manifest-v1.json
python -I tools/validate_manifest.py \
  --manifest build/m2/base/manifest-v1.json \
  --game-root Starsector-098-Base
```

Expected（实测）：stock Base **带** DDSCache → `source_mode=dds_metadata`、L1 185 / L2 509 /
L3 2,612、`coverage.baked=3,285/3,285=1.0`、validator **0 Critical / exit 0**。
无缓存降级路径用临时移走 DDSCache 的副本验证：`source_mode=disk_scan`、`coverage.metadata=None`、
`coverage.baked=1.0`（expected=0 的约定）、validator 0 Critical；原 DDSCache 必须还原。

- [ ] **Step 3: 构建并安装新 jar、恢复 M2 manifest，再跑 Base 运行时冒烟**

**环境裁决**：260mods 是 agent-only（256 mods，不含 `hypernova_infinite_engine`），
运行期 mod 在 Base 验证；`smoke-prepare.sh` 在 260mods 会于第 5 步断言中止。冒烟走 Base。

```bash
bash tools/java/build-mod.sh
bash tools/java/smoke-prepare.sh                       # 默认 Base：装新 jar + M0 manifest + probe=8，随后重写 M2 manifest
python -I tools/smoke_run.py --profile base --rounds 1 \
  --wait-menu 300 --json-out build/m2/smoke-base.json
bash tools/java/smoke-restore.sh                        # probe 归 0，并再次重写 M2 manifest
```

Expected：
- Base 运行时 manifest：`hypernova-runtime-1`，L1 185 / L2 509 / L3 2,612（unique 3,306）。
- smoke 到主菜单；`starsector-core/starsector.log` 含
  `Hypernova active: ... manifest=3306 paths, discarded=0, crossLayer=0`。
- 无 `Hypernova disabled`、无 `Failed to load texture`。
- **自检边界**：`smoke_run.py` 只到主菜单、不进 campaign，`startup_probe_paths=8` 不会触发
  `runFallbackSelfCheck`；REQ-R1-05 的 L1-only 由 `StartupSelfCheckTest` 锁定，完整 campaign
  `selfcheck` 仍需手动读档，不计入本次门禁。

- [ ] **Step 4: 全量测试**

```bash
python -I -m pytest tests/tools -q
bash tools/java/run-tests.sh
bash tools/java/build-mod.sh
```

Expected：
- pytest：M2 新增测试全绿；仅 2 个已知失败（`test_smoke_check.py` stale 夹具），总数以实测为准。
- Java：101 → 新增 3 个，`0 failed`、1 个既有 symlink abort。
- `build-mod.sh` 仍产出 jar/zip，且 zip 含 `data/config/hypernova/manifest-v1.json`。

- [ ] **Step 5: 写 `docs/m2-results.md`**

必须包含：
1. 结论：REQ-R1-04/05 通过；coverage 100%；L1 6,624 ≤ 8,000；per-mod tier 可用。
2. 260mods 数字表（L1/L2/L3、metadata、coverage、closure、mods 行数、生成耗时）。
3. Base 降级路径数字。
4. 改名/禁用/duplicate/空 DDSCache 四类 fixture 证据（测试名）。
5. 冒烟证据（menu、manifest 路径数、无 selfcheck 失败）。
6. 回滚：删除/恢复 `data/config/hypernova/manifest-v1.json`；tier override 是生成期参数，不影响已安装 manifest。
7. 明确「未做」：未实现运行期自动重建 manifest；用户改 mod 集合后需重跑 `install_manifest.py`。

- [ ] **Step 6: 回写规格与记忆**

- `技术笔记-纹理按需加载.md`：
  - §7 M2 状态改为「完成（2026-11-01）」，附 `docs/m2-results.md` 与关键数字。
  - §5.4 增补 `mods[]`、`coverage.baked*`、`unresolved_baked*`、`tiers` 字段说明；重申运行时 schema 不变。
  - ADR-05 补记 4：M2 完成、键稳定性规则（ModID + 路径）、tier 语义。
- 记忆：
  - `hn-next-session.md` 首段钩子改为「M2 已完成；下次先读 `docs/m2-results.md` + 本文件；下一里程碑待裁决」。
  - `hn-architecture.md` 追加 2026-11-01 M2 状态。
  - `MEMORY.md` 增加 M2 完成索引行。

- [ ] **Step 7: 提交**

```bash
git add docs/m2-results.md 技术笔记-纹理按需加载.md \
  C:/Users/qwe13/.claude/projects/D--github-Hypernova-Infinite-Engine/memory/hn-next-session.md \
  C:/Users/qwe13/.claude/projects/D--github-Hypernova-Infinite-Engine/memory/hn-architecture.md \
  C:/Users/qwe13/.claude/projects/D--github-Hypernova-Infinite-Engine/memory/MEMORY.md
git commit -m "docs(m2): close the manifest-driven milestone"
```

> 记忆文件不在仓库内，`git add` 会失败；实际只提交仓库内文档，记忆文件直接写入即可。执行者按此注处理并报告。

---

## Self-Review（控制器写完计划后逐项过）

1. **Spec coverage**
   - REQ-R1-04（manifest 由 dds_metadata 生成、100%、无缓存降级）→ T2（生成）、T3（100% 门禁）、T7 Step 2（Base 降级）。
   - REQ-R1-05（L1/L2/L3 分层、启动期只 L1）→ T2（分层与 tier）、T6（自检只 L1，单测锁定）、T7 Step 3（Base 主菜单冒烟证明 manifest 被加载；campaign 自检为手动项）。
   - §7 M2 交付物（生成器、校验器、按 mod 分级）→ T2（生成器 + per-mod 汇总 + tier）、T3（校验器）、T5（安装器）。
   - §7 M2 停止条件（改名/新增 mod → 先解决键稳定性）→ T1/T2（ModID 稳定身份 + 改名 fixture）。
   - OD-02 A 全预载（L1 ≤ 8,000）→ T4（精确化）、T7（实测 6,624）。
2. **Placeholder scan**：无 TBD/TODO；所有新函数有签名与完整实现；所有测试有具体断言。
3. **Type consistency**：`MetadataEntry.mod_id`、`resolve(...)` 在 T1 定义、T2 使用；`stats.coverage.baked` 等在 T2 产出、T3 消费；`install()` 返回 `InstallResult` 在 T5 定义并使用；`selfCheckCandidates` 在 T6 定义并测试。
4. **Review Focus**：5 条均有对应测试（见 Review Focus 列表）。
5. **Proportion**：本计划包含生产代码是因为 implementer 是转录型（SDD 约定）；测试与实现一一对应，无重复抄写规格。

## Exit criteria（M2 出口）

- [ ] `python -I tools/validate_manifest.py --manifest build/m2/260mods/manifest-v1.json --game-root Starsector-098-260mods` → **0 Critical，exit 0**；1 条聚合既有 `cross_layer_duplicate` Important（覆盖 44 个 key）记入 triage（R8）。
- [ ] `coverage.baked == 1.0`、`unresolved_baked_count == 0`、`closure_refs == 1.0`。
- [ ] `l1_count` ≤ 8,000（预期 6,624）。
- [ ] `mods[]` 三层求和与 `layers` 完全相等；per-mod tier 可覆盖。
- [ ] 改名/禁用/duplicate/空 DDSCache 四类 fixture 测试全绿。
- [ ] Java 全量测试 0 failed；Python M2 测试全绿。
- [ ] **Base** 冒烟到主菜单，`starsector.log` 含 `Hypernova active: ... manifest=3306 paths, discarded=0, crossLayer=0`；260mods 是 agent-only，只交出离线 manifest 证据。
- [ ] `docs/m2-results.md` 落盘；规格 §7/§5.4/ADR-05 回写；记忆钩子更新。
