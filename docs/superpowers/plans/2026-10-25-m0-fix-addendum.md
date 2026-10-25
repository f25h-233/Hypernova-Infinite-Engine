# M0 Fix Addendum — Task 2 / Task 3 审查修正

> 本文件**取代**主计划 `2026-10-25-m0-manifest.md` 中 Task 2 / Task 3 的对应代码与测试。主计划其余部分仍有效。
> 触发：Task 2 review（Important ×2）、Task 3 review（Critical ×1 + Important ×1）。所有数字以 260mods 实测为准。

## A. Task 2 fix

### A1. `tools/mod_index.py` — `MetadataIndex` 增加 `parse_errors`

```python
@dataclass
class MetadataIndex:
    entries: list[MetadataEntry] = field(default_factory=list)
    by_key: dict[tuple[str, str], MetadataEntry] = field(default_factory=dict)
    by_rel: dict[str, list[MetadataEntry]] = field(default_factory=dict)
    fallback_hits: int = 0
    parse_errors: dict[str, str] = field(default_factory=dict)
```

### A2. `read_dds_metadata` — 文件级/记录级解析错误都要落账

把原来的 `try: records = load(path) / except: continue` 与记录循环替换为：

```python
        try:
            records = load(path)
        except Exception as exc:
            index.parse_errors[entry.name] = f"{path.name}: {exc}"
            continue
        if not isinstance(records, list):
            index.parse_errors[entry.name] = f"{path.name}: top-level is not a list"
            continue
        for lineno, record in enumerate(records, 1):
            try:
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
                folder = str(record.get("ModFolderName") or entry.name)
                rel = _norm_rel(str(record.get("RelativeImagePath") or ""))
                if not rel:
                    raise ValueError("empty RelativeImagePath")
                dds_rel = _norm_rel(str(record.get("DDSFilePath") or ""))
                me = MetadataEntry(
                    folder,
                    rel,
                    dds_rel,
                    int(record.get("Width") or 0),
                    int(record.get("Height") or 0),
                )
            except Exception as exc:
                index.parse_errors[entry.name] = f"{path.name} record {lineno}: {exc}"
                continue
            index.entries.append(me)
            index.by_key[(folder.casefold(), rel.casefold())] = me
            index.by_rel.setdefault(rel.casefold(), []).append(me)
```

### A3. `_norm_rel` — 折叠重复斜杠

```python
def _norm_rel(rel: str) -> str:
    out = rel.replace("\\", "/").lstrip("/")
    while "//" in out:
        out = out.replace("//", "/")
    return out
```

### A4. 新增 `build_id_index`（内部 id + 文件名双键）

```python
def build_id_index(
    mods: list[ModRef],
    subdir: str,
    suffixes: frozenset[str],
    id_field: str,
    extra_subdirs: tuple[str, ...] = (),
) -> dict[str, list[AssetRef]]:
    """按文件名 stem 与内部 id 双键索引；内部 id 不符时仍可按文件名命中。"""
    index: dict[str, list[AssetRef]] = {}
    for current in (subdir, *extra_subdirs):
        for mod in mods:
            for asset in iter_assets(mod, current, suffixes):
                try:
                    data = load(asset.absolute)
                except Exception:
                    data = {}
                keys = {Path(asset.rel).stem}
                internal = data.get(id_field) if isinstance(data, dict) else None
                if isinstance(internal, str) and internal.strip():
                    keys.add(internal.strip())
                for key in keys:
                    index.setdefault(key, []).append(asset)
    return index
```

### A5. Task 2 新增测试（`tests/tools/test_mod_index.py`）

```python
def test_metadata_unique_rel_fallback(mini_game):
    md = read_dds_metadata(mini_game)
    hit = md.get("renamed_folder", "graphics/ships/h_alpha.png")
    assert hit is not None and hit.mod_folder == "mod_a"
    assert md.fallback_hits == 1


def test_metadata_ambiguous_rel_is_rejected(mini_game):
    import json as _json
    from conftest import _write
    _write(
        mini_game / "mods" / "DDSCache" / "mod_b" / "dds_metadata.json",
        _json.dumps([{
            "ModFolderName": "mod_b",
            "RelativeImagePath": "graphics\\ships\\h_alpha.png",
            "DDSFilePath": "\\mods\\DDSCache\\mod_b\\graphics\\ships\\h_alpha.dds",
            "Width": 1, "Height": 1,
        }]),
    )
    md = read_dds_metadata(mini_game)
    assert md.get("no_such_folder", "graphics/ships/h_alpha.png") is None
    assert md.fallback_hits == 0


def test_metadata_parse_error_is_recorded(mini_game):
    from conftest import _write
    _write(mini_game / "mods" / "DDSCache" / "broken" / "dds_metadata.json", "{not json")
    md = read_dds_metadata(mini_game)
    assert "broken" in md.parse_errors
    assert len(md.entries) == 3


def test_metadata_bad_record_does_not_abort(mini_game):
    import json as _json
    from conftest import _write
    _write(
        mini_game / "mods" / "DDSCache" / "partly" / "dds_metadata.json",
        _json.dumps([
            {"ModFolderName": "partly", "RelativeImagePath": "graphics\\ok.png", "Width": 1, "Height": 1},
            {"ModFolderName": "partly", "RelativeImagePath": "graphics\\bad.png", "Width": "oops", "Height": 1},
            {"ModFolderName": "partly", "RelativeImagePath": "graphics\\ok2.png", "Width": 2, "Height": 2},
        ]),
    )
    md = read_dds_metadata(mini_game)
    assert "partly" in md.parse_errors
    assert [me.rel for me in md.entries if me.mod_folder == "partly"] == [
        "graphics/ok.png", "graphics/ok2.png",
    ]
```

预期：`python -I -m pytest tests/tools/test_mod_index.py -q` → **13 passed**；全量 `tests/tools` 无回归。

---

## B. Task 3 fix

### B1. `build_lookup` — 用内部 id 索引；weapon 追加 `data/shipsystems/wpn`

```python
from mod_index import (
    AssetRef, ModRef, build_id_index, build_image_index, pick, read_wing_map,
)

def build_lookup(mods: list[ModRef]) -> AssetLookup:
    return AssetLookup(
        variants=build_id_index(mods, "variants", frozenset({".variant"}), "variantId"),
        ships=build_id_index(mods, "hulls", frozenset({".ship"}), "hullId"),
        skins=_build_skin_index(mods),
        weapons=build_id_index(
            mods, "weapons", frozenset({".wpn"}), "id", ("shipsystems/wpn",)
        ),
        images=build_image_index(mods),
        wings=read_wing_map(mods),
    )
```

### B2. `_build_skin_index` — `skinHullId` 与文件名双键

```python
                sid = str(data.get("skinHullId") or Path(fn).stem)
                rel = absolute.relative_to(mod.folder).as_posix()
                for key in {sid, Path(fn).stem}:
                    out.setdefault(key, []).append(
                        AssetRef(mod.mod_id, mod.folder, absolute, rel, mod.order)
                    )
```

### B3. `_norm_path` — 折叠 `//`；`add_sprite` — 记录 `missing["sprite"]`

```python
def _norm_path(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rel = value.replace("\\", "/").lstrip("/")
    while "//" in rel:
        rel = rel.replace("//", "/")
    return rel
```

`_Walker.add_sprite` 末尾：

```python
        owner = pick(self.lookup.images.get(key) or [])
        self.result.sprites[key] = SpriteRef(rel, owner)
        if owner is None:
            self.result.stats.miss("sprite", rel)
```

### B4. Task 3 新增测试（`tests/tools/test_sprite_closure.py`）

```python
def test_index_by_internal_ids_and_shipsystems_wpn(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "file_stem.variant",
        '{"variantId": "internal_v", "hullId": "h_alpha", '
        '"weaponGroups": [{"weapons": {"WS1": "internal_w"}}]}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "shipsystems" / "wpn" / "internal_w.wpn",
        '{"id": "internal_w", "turretSprite": "graphics/weapons/w_gun_t.png"}',
    )
    result = build_closure(["internal_v"], _lookup(mini_game))
    assert "graphics/ships/h_alpha.png" in result.sprites
    assert "graphics/weapons/w_gun_t.png" in result.sprites
    assert result.stats.weapons_resolved == 1


def test_double_slash_sprite_is_normalized(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_alpha.ship",
        '{"hullId": "h_alpha", "hullSize": "CRUISER", '
        '"spriteName": "graphics//ships//h_alpha.png"}',
    )
    result = build_closure(["va_one"], _lookup(mini_game))
    assert "graphics/ships/h_alpha.png" in result.sprites
    assert result.sprites["graphics/ships/h_alpha.png"].owner is not None
    assert "sprite" not in result.stats.missing


def test_missing_sprite_is_recorded(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_bad_sprite.variant",
        '{"variantId": "va_bad_sprite", "hullId": "h_bad_sprite"}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_bad_sprite.ship",
        '{"hullId": "h_bad_sprite", "hullSize": "FRIGATE", '
        '"spriteName": "graphics/ships/nope.png"}',
    )
    result = build_closure(["va_bad_sprite"], _lookup(mini_game))
    assert result.stats.missing["sprite"] == ["graphics/ships/nope.png"]
```

预期：`python -I -m pytest tests/tools/test_sprite_closure.py -q` → **8 passed**；全量 `tests/tools` 无回归。

---

## C. 下游已同步（主计划已含）

- Task 5 `stats.metadata_parse_errors` + `coverage.metadata = 0.0`（有解析错误时）。
- Task 6 validator：`metadata_parse_errors` 非空 → **Critical**。
- 260mods 实测期望更新：L1 **6,577**、L2 **25,108**；missing 残留 variant 3 / hull 0 / weapon 16；仍须 `L1 ≤ 8,000`、`closure_refs ≥ 0.95`。

## C2. Task 4 fix（planets.json 解析错误落账）

### C2.1 `tools/l1_core.py` — 增加 `CoreAssets` 结果类型

```python
from dataclasses import dataclass, field


@dataclass
class CoreAssets:
    paths: list[str] = field(default_factory=list)
    parse_errors: dict[str, str] = field(default_factory=dict)


def _dedupe(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for path in paths:
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def core_assets_result(game_root: Path) -> CoreAssets:
    paths = list(CORE_STATIC)
    errors: dict[str, str] = {}
    config = game_root / "starsector-core" / "data" / "config" / "planets.json"
    if config.is_file():
        try:
            planets = load(config)
        except Exception as exc:
            errors[str(config)] = f"{config.name}: {exc}"
            planets = {}
        if isinstance(planets, dict):
            for planet_type in PLANET_TYPES:
                entry = planets.get(planet_type)
                if not isinstance(entry, dict):
                    continue
                for field_name in PLANET_FIELDS:
                    value = entry.get(field_name)
                    if isinstance(value, str) and value.strip():
                        paths.append(value.replace("\\", "/").lstrip("/"))
        else:
            errors[str(config)] = f"{config.name}: top-level is not an object"
    return CoreAssets(_dedupe(paths), errors)


def core_assets(game_root: Path) -> list[str]:
    return core_assets_result(game_root).paths
```

保留 `core_assets()` 作为薄包装，现有测试不用改。

### C2.2 Task 4 新增测试（`tests/tools/test_l1_core.py`）

```python
def test_bad_planets_json_is_recorded_not_swallowed(mini_game):
    from l1_core import core_assets_result
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        "{not json",
    )
    result = core_assets_result(mini_game)
    assert result.paths == CORE_STATIC
    assert any("planets.json" in key for key in result.parse_errors)


def test_good_planets_json_has_no_errors(mini_game):
    from l1_core import core_assets_result
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        '{"desert": {"texture": "graphics/planets/desert.jpg"}}',
    )
    result = core_assets_result(mini_game)
    assert result.parse_errors == {}
    assert "graphics/planets/desert.jpg" in result.paths
```

预期：`python -I -m pytest tests/tools/test_image_probe.py tests/tools/test_l1_core.py -q` → **8 passed**。

### C2.3 Task 5 消费方式

- `from l1_core import core_assets_result`
- `core = core_assets_result(game_root)`；L1 遍历 `core.paths`。
- `stats` 增加 `"core_parse_errors": core.parse_errors`。
- Task 6 validator：`stats.core_parse_errors` 非空 → **Critical**。
- Task 8 报告“闭包缺口”节列出 `core_parse_errors`。

## D. Task 6 fix（validator 假绿）

> 触发：Task 6 review 的 F1–F4 四条 Important。三条会让 validator 在缺失/错误数据上返回 exit 0，直接威胁 M0 出口证据。

### D1. `stats` / `coverage` 整块缺失 → Critical（F1）

在 `validate()` 里 `layers` 检查之后、读取 `stats` 之前插入：

```python
    stats = manifest.get("stats")
    if not isinstance(stats, dict):
        findings.append(Finding("Critical", "missing_stats", "manifest.stats is missing"))
        return findings
    coverage = stats.get("coverage")
    if not isinstance(coverage, dict):
        findings.append(
            Finding("Critical", "missing_coverage", "manifest.stats.coverage is missing")
        )
        return findings
```

并删除原实现里的 `stats = manifest.get("stats") or {}` 与 `coverage = stats.get("coverage") or {}`。

### D2. metadata 覆盖率不达标 → Critical（F2）

```python
    meta_cov = coverage.get("metadata")
    if meta_cov is not None and float(meta_cov) < 1.0:
        findings.append(
            Finding("Critical", "coverage_metadata", f"metadata={meta_cov} < 1.0")
        )
```

### D3. 让 `game_root` 真正参与校验（F3）

对 `baked=True` 的条目，额外要求 `ddsPath` 落在 `game_root` 之内：

```python
def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True
```

在 `_entry_findings` 的 `baked` 分支里：

```python
    if entry["baked"]:
        dds = entry.get("ddsPath")
        if not dds or not Path(str(dds)).is_file():
            out.append(
                Finding("Critical", "missing_dds", f"{layer}: baked entry has no DDS {path}")
            )
        elif not _inside_root(Path(str(dds)), game_root):
            out.append(
                Finding(
                    "Critical",
                    "dds_outside_root",
                    f"{layer}: DDS outside game root {dds}",
                )
            )
```

另外，`main()` 在调用 `validate` 前校验 `--game-root` 必须存在：

```python
    if not args.game_root.is_dir():
        print(f"[Critical] bad_game_root: {args.game_root} is not a directory", file=sys.stderr)
        return 1
```

### D4. 补 6 条能红的测试（F4）

```python
def test_missing_stats_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m.pop("stats", None)
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_stats" in codes


def test_missing_coverage_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"].pop("coverage", None)
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_coverage" in codes


def test_metadata_coverage_below_one_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"]["metadata"] = 0.5
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "coverage_metadata" in codes


def test_dds_outside_game_root_is_critical(mini_game, tmp_path):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    baked = next(e for e in m["layers"]["L1"] if e["baked"])
    outside = tmp_path / "elsewhere.dds"
    outside.write_bytes(b"DDS ")
    baked["ddsPath"] = str(outside)
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "dds_outside_root" in codes


def test_bad_game_root_cli_exits_nonzero(mini_game, tmp_path):
    import subprocess, sys
    from pathlib import Path
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    out = tmp_path / "m.json"
    out.write_text(json.dumps(build_manifest(mini_game, include_l2=False).manifest), encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-I", str(root / "tools" / "validate_manifest.py"),
         "--manifest", str(out), "--game-root", str(tmp_path / "nope")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1
    assert "bad_game_root" in (proc.stdout + proc.stderr)


def test_entry_schema_missing_key_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"][0].pop("src")
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "entry_schema" in codes
```

预期：`python -I -m pytest tests/tools/test_validate_manifest.py -q` → **14 passed**；全量 `tests/tools` → **63 passed**。

---

## D5. Task 6 fix 第二轮（复审 F4 NOT ADDRESSED + 假测试）

> 触发：`task-6-fix-review.md`。F1/F3 有残余，F4 只补了 6 个 code 中的 2 个，另发现 `test_bad_game_root_cli_exits_nonzero` 是**假绿**。

### D5.1 假测试根因与修法

`bad_game_root` 的断言用 `"bad_game_root" in (stdout + stderr)`，而 pytest 的 `tmp_path` 目录名是 `test_bad_game_root_cli_exits_n0`，路径出现在 stderr 里就命中——删掉 CLI 守卫测试仍绿。

修法：
1. CLI 输出改成带前缀的稳定标记：`[Critical] bad_game_root: <path> is not a directory`（已有 `[Critical]` 前缀，保持不变）。
2. 测试里断言**精确前缀**，并把临时目录换成中性名字，避免路径污染：

```python
def test_bad_game_root_cli_exits_nonzero(mini_game, tmp_path):
    import subprocess, sys
    from pathlib import Path
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    work = tmp_path / "work"
    work.mkdir()
    out = work / "m.json"
    out.write_text(json.dumps(build_manifest(mini_game, include_l2=False).manifest), encoding="utf-8")
    missing_root = tmp_path / "absent_root"
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-I", str(root / "tools" / "validate_manifest.py"),
         "--manifest", str(out), "--game-root", str(missing_root)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1
    lines = (proc.stdout + proc.stderr).splitlines()
    assert any(line.startswith("[Critical] bad_game_root:") for line in lines)
```

### D5.2 F1 残余：`coverage={}` 与 gate 键缺失仍放行

在 `validate()` 的 `missing_coverage` 检查之后追加：

```python
    for required in ("l1_sprite_disk", "closure_refs"):
        if required not in coverage:
            findings.append(
                Finding("Critical", "missing_coverage", f"coverage.{required} is missing")
            )
```

（`metadata` 允许缺失——Base 无 DDSCache 时是 N/A。）

### D5.3 F3 残余：未烘焙条目的 `absolutePath` 也要在根内

在 `_entry_findings` 的 `elif not Path(absolute).is_file()` 分支之后、`baked` 判断之前追加：

```python
    if absolute and Path(absolute).is_file() and not _inside_root(Path(absolute), game_root):
        out.append(
            Finding("Critical", "asset_outside_root", f"{layer}: asset outside game root {absolute}")
        )
```

### D5.4 F4 残余：补 5 条能红测试

```python
def test_bad_path_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"][0]["path"] = "../escape.png"
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "bad_path" in codes


def test_missing_dds_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    baked = next(e for e in m["layers"]["L1"] if e["baked"])
    baked["ddsPath"] = str(mini_game / "nope.dds")
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_dds" in codes


def test_layers_not_dict_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L2"] = "oops"
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "layers" in codes


def test_empty_absolute_path_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"][0]["absolutePath"] = ""
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_file" in codes


def test_coverage_closure_refs_below_threshold_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"]["closure_refs"] = 0.5
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "coverage_closure_refs" in codes


def test_coverage_missing_gate_key_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"].pop("closure_refs")
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_coverage" in codes
```

预期：`test_validate_manifest.py` → **20 passed**；全量 `tests/tools` → **69 passed**。修后必须重跑 Base / 260mods 两个真实环境并记录 exit code。

---

## F. Task 5 fix（manifest 组装）

> 触发：`task-5-review.md`（Spec ❌，F1–F6 六条 Important）。F3 已实测确认：81,559 条 `absolutePath` 全是相对路径，换 CWD 跑同一份 manifest 会冒出 81,559 条 Critical。

### F1. 全路径绝对化（最优先）

`build_manifest` 入口处统一解析一次根，之后所有路径用 `root` 拼：

```python
def build_manifest(
    game_root: Path,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    variant_limit: int = 0,
) -> BuildResult:
    root = Path(game_root).resolve()
    ...
```

把函数体内所有 `game_root` 改为 `root`（`_sprite_entry` / `_metadata_entry` / `_folder_path` 的调用点一并传 `root`）。`_folder_path` 与 `_sprite_entry` 内部对传入值再 `.resolve()` 一次，确保 `Path.as_posix()` 产出绝对路径。

### F2. `metadata_entries` / `disk_images` / `unbaked` 同人口

三个数必须都只统计 **scope 内、已启用 mod + core**：

```python
    enabled_folders = {m.folder.name.casefold() for m in scan.mods}
    scope_meta = [
        me for me in metadata.entries
        if in_scope(me, scope) and me.mod_folder.casefold() in enabled_folders
    ]
    core_meta = [
        me for me in metadata.entries
        if me.mod_folder.casefold() == "starsector-core" and include_core
    ]
```

`disk_images` / `unbaked` 用同一 `scope_meta` + `core_meta` 计算分母，并在 `stats` 里增加：

```python
        "metadata_entries_scope": len(scope_meta),
        "metadata_entries_core": len(core_meta),
        "metadata_entries_all": len(metadata.entries),
```

报告里三个数必须能对上 `78,040 + 3,204 = 81,244`（若某些 DDSCache 文件夹属于未启用 mod，差额写进 `stats.metadata_unused`）。

### F3. L3 去重收敛到 `(modId, path)`

L3 写入前用与 validator 相同的键：

```python
    l3_keys: set[tuple[str, str]] = set()
    def add_l3(entry: dict) -> None:
        key = (str(entry["modId"]).casefold(), str(entry["path"]).casefold())
        if key in l3_keys:
            return
        l3_keys.add(key)
        l3.append(entry)
```

把 `l3.append(...)` 全部换成 `add_l3(...)`。同 id 多文件夹（`ConsoleCommands` vs `lw_console`）应在 `folder_to_id` 阶段合并到同一 `modId`，只保留 `enabled_mods.json` 顺序在前的那份，并在 `stats.conflicts.duplicate_mod_ids` 里已有记录。

### F4. `--no-core` 语义修正

`include_core=False` 时：

- L1 不得加入 `CORE_STATIC` / `planets.json` 资产；
- L2 的实体池不得包含 core 的 variant/hull/weapon；
- L3 不得加入 `core_meta` / `core_images`。

做法：`core = core_assets_result(game_root)` 后仅当 `include_core` 才 `for rel in core.paths: add_sprite(rel)`；`build_lookup` 增加 `include_core` 过滤（或在 `scan_mods(..., include_core=include_core)` 时不追加 core ModRef）。

### F5. 补 6 条能红测试

```python
def test_paths_are_absolute(mini_game):
    m = _build(mini_game)
    for layer in ("L1", "L2", "L3"):
        for e in m["layers"][layer]:
            assert Path(e["absolutePath"]).is_absolute(), e
            if e["ddsPath"]:
                assert Path(e["ddsPath"]).is_absolute(), e


def test_metadata_counts_share_one_population(mini_game):
    m = _build(mini_game)
    s = m["stats"]
    assert s["metadata_entries"] + s["metadata_entries_core"] == s["metadata_entries_all"]
    assert s["metadata_entries_all"] == 3  # fixture: mod_a×2 + core×1


def test_l3_has_no_duplicate_modid_path(mini_game):
    m = _build(mini_game)
    keys = [(e["modId"], e["path"].casefold()) for e in m["layers"]["L3"]]
    assert len(keys) == len(set(keys))


def test_no_core_excludes_core_from_all_layers(mini_game):
    m = _build(mini_game, include_core=False)
    for layer in ("L1", "L2", "L3"):
        assert all(e["modId"] != "core" for e in m["layers"][layer]), layer
    assert m["stats"]["core_entries"] == 0


def test_metadata_parse_error_zeroes_coverage(mini_game):
    from conftest import _write
    _seed_core(mini_game)
    _write(mini_game / "mods" / "DDSCache" / "broken" / "dds_metadata.json", "{not json")
    m = build_manifest(mini_game, include_l2=False).manifest
    assert m["stats"]["coverage"]["metadata"] == 0.0


def test_variant_limit_truncates_pool(mini_game):
    a = _build(mini_game, variant_limit=1)
    b = _build(mini_game)
    assert len(a["layers"]["L2"]) <= len(b["layers"]["L2"])
```

预期：`test_manifest_builder.py` → **13 passed**；全量 `tests/tools` → **75 passed**。
修后必须重新生成 Base / 260mods 两份 manifest，并用 `cd` 到另一个目录跑 validator，确认不再出现 `missing_file`。

---

## G. Task 5 fix 第二轮（收口轮，只做三条）

> 触发：`task-5-fix-review.md`。生产数据已正确（相对路径 0、跨 CWD exit 0），但三条新测试不抗变异，且 `--no-core` 在 260mods 真实数据上漏出 core 条目。

### G1. `--no-core` 下 `by_rel` 回退必须排除 core（真实缺陷）

`_sprite_entry` 的 `by_rel` 唯一回退会把 `starsector-core` 的 metadata 拉回来（260mods 实测 L1 125 / L2 268 条 core）。

给 `_sprite_entry` 增加参数：

```python
def _sprite_entry(
    rel: str,
    lookup: AssetLookup,
    metadata: MetadataIndex,
    game_root: Path,
    include_core: bool = True,
) -> tuple[dict, tuple[str, str] | None]:
    ...
    else:
        candidates = [
            me for me in (metadata.by_rel.get(rel.casefold()) or [])
            if include_core or me.mod_folder.casefold() != "starsector-core"
        ]
        if len(candidates) == 1:
            meta = candidates[0]
```

所有调用点传 `include_core=include_core`。

### G2. 补三条抗变异的 fixture 测试

```python
def test_paths_absolute_against_relative_game_root(mini_game, monkeypatch):
    """回归：入口忘记 resolve() 时，用相对 game_root 必须仍产出绝对路径。"""
    monkeypatch.chdir(mini_game.parent)
    m = build_manifest(Path(mini_game.name), include_l2=False).manifest
    for e in m["layers"]["L1"]:
        assert Path(e["absolutePath"]).is_absolute(), e


def test_disabled_mod_metadata_is_excluded(mini_game):
    """回归：去掉 enabled_folders 过滤会让额外 1 条 metadata 混进 L3。"""
    import json as _json
    from conftest import _write
    _write(
        mini_game / "mods" / "DDSCache" / "not_enabled" / "dds_metadata.json",
        _json.dumps([{
            "ModFolderName": "not_enabled",
            "RelativeImagePath": "graphics/x.png",
            "DDSFilePath": "\\mods\\DDSCache\\not_enabled\\graphics\\x.dds",
            "Width": 1, "Height": 1,
        }]),
    )
    m = build_manifest(mini_game, include_l2=False).manifest
    assert m["stats"]["metadata_unused"] >= 1
    assert all(e["modId"] != "not_enabled" for e in m["layers"]["L3"])


def test_l3_dedupes_duplicate_mod_id_folders(mini_game):
    """回归：改回 l3.append 会让同 id 双文件夹产出重复键。"""
    import json as _json
    from conftest import _write
    _write(mini_game / "mods" / "mod_a_copy" / "mod_info.json", '{"id": "mod_a"}')
    _write(
        mini_game / "mods" / "DDSCache" / "mod_a_copy" / "dds_metadata.json",
        _json.dumps([{
            "ModFolderName": "mod_a_copy",
            "RelativeImagePath": "graphics/ships/h_alpha.png",
            "DDSFilePath": "\\mods\\DDSCache\\mod_a_copy\\graphics\\ships\\h_alpha.dds",
            "Width": 64, "Height": 32,
        }]),
    )
    m = build_manifest(mini_game, include_l2=False).manifest
    keys = [(e["modId"], e["path"].casefold()) for e in m["layers"]["L3"]]
    assert len(keys) == len(set(keys))
```

### G3. `--no-core` 真实数据复验

修完 G1 后重新生成 260mods 的 `--no-core` manifest：

```bash
python -I tools/gen_manifest.py --game-root Starsector-098-260mods --no-core --out build/m0/260mods/manifest-nocore.json
python -I -c "import json;m=json.load(open('build/m0/260mods/manifest-nocore.json',encoding='utf-8'));print({L:sum(1 for e in m['layers'][L] if e['modId']=='core') for L in ('L1','L2','L3')})"
```

必须三层全 0。修完重跑正式两份 manifest（`base` / `260mods`），确认数字未变（L1 6,614 / L2 18,535 / L3 55,444）。

### G4. 明确 `include_core=False` 时 `core_parse_errors` 语义

在 `stats` 里增加：

```python
        "core_parse_errors_skipped": not include_core,
```

Task 6 的 validator 只在 `core_parse_errors` 非空时判 Critical，`skipped=True` 时不判——两者不冲突，无需改 validator。

预期：`test_manifest_builder.py` → **16 passed**；全量 `tests/tools` → **78 passed**。

---

## H. M0.1 收口（最终 review 的 4 条必修）

> 触发：`final-review.md` 的 I-2 / I-4 / I-5 / I-7。四条都**不改 gate 数字**，但都影响"出口仪器可信度"。

### H1. I-5：validator 不许对空输入 PASS

三处一起改：

1. **`schema` 类型严格化**（`validate_manifest.py`）：

```python
    if type(manifest.get("schema")) is not int or manifest.get("schema") != 1:
        findings.append(
            Finding("Critical", "schema", f"expected integer schema 1, got {manifest.get('schema')!r}")
        )
```

2. **空 L1 → Critical**：

```python
    if not layers["L1"]:
        findings.append(Finding("Critical", "empty_l1", "L1 layer is empty"))
```

3. **`l1_count` 与层长交叉校验**：

```python
    stats_l1 = stats.get("l1_count")
    if stats_l1 is not None and int(stats_l1) != len(layers["L1"]):
        findings.append(
            Finding(
                "Critical",
                "l1_count_mismatch",
                f"stats.l1_count={stats_l1} != len(L1)={len(layers['L1'])}",
            )
        )
```

4. `build_manifest` 里空 L1 时不再返回 1.0：

```python
                "l1_sprite_disk": (l1_disk / len(l1)) if l1 else 0.0,
```

### H2. I-4：跨层同一引擎 key 唯一性

validator 在层循环之后加：

```python
    key_layers: dict[str, set[str]] = {}
    for name in ("L1", "L2", "L3"):
        for entry in layers[name]:
            key = str(entry.get("path", "")).casefold()
            key_layers.setdefault(key, set()).add(name)
    cross = {k: v for k, v in key_layers.items() if len(v) > 1}
    if cross:
        findings.append(
            Finding(
                "Important",
                "cross_layer_duplicate",
                f"{len(cross)} engine key(s) appear in multiple layers: "
                + ", ".join(sorted(cross)[:5]),
            )
        )
```

builder 侧记录内容冲突，`stats` 增：

```python
        "path_conflicts": path_conflicts,  # list[{path, layers, sizes, same_content}]
```

规则：同一 `path` 在不同层出现时，若 `(w,h)` 不同则标 `content_differs=True`（无需哈希，尺寸差异已足以判定）。

### H3. I-7：skin 解析错误落账

`_build_skin_index` 改为返回 `(index, parse_errors)`：

```python
def _build_skin_index(mods: list[ModRef]) -> tuple[dict[str, list[AssetRef]], dict[str, str]]:
    out: dict[str, list[AssetRef]] = {}
    errors: dict[str, str] = {}
    for mod in mods:
        base = mod.folder / "data" / "hulls"
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in filenames:
                if Path(fn).suffix.casefold() != ".skin":
                    continue
                absolute = Path(dirpath) / fn
                try:
                    data = load(absolute)
                    if not isinstance(data, dict):
                        raise ValueError("skin is not an object")
                    sid = str(data.get("skinHullId") or Path(fn).stem)
                except Exception as exc:
                    errors[str(absolute)] = f"{fn}: {exc}"
                    continue
                rel = absolute.relative_to(mod.folder).as_posix()
                for key in {sid, Path(fn).stem}:
                    out.setdefault(key, []).append(
                        AssetRef(mod.mod_id, mod.folder, absolute, rel, mod.order)
                    )
    return out, errors
```

`build_lookup` 把 `skin_errors` 挂到 `AssetLookup` 上；`build_closure` 写入 `stats.parse_errors["skin"]`。

### H4. I-2：`--no-core` 时 `MetadataIndex.get` 也要过滤 core

```python
    def get(self, mod_folder: str, rel: str, exclude_core: bool = False) -> MetadataEntry | None:
        key = (mod_folder.casefold(), rel.casefold())
        hit = self.by_key.get(key)
        if hit is not None:
            if exclude_core and hit.mod_folder.casefold() == "starsector-core":
                return None
            return hit
        candidates = [
            me for me in (self.by_rel.get(rel.casefold()) or [])
            if not (exclude_core and me.mod_folder.casefold() == "starsector-core")
        ]
        if len(candidates) == 1:
            self.fallback_hits += 1
            return candidates[0]
        return None
```

`_sprite_entry` 调用改为 `metadata.get(owner.folder.name, rel, exclude_core=not include_core)`。

### H5. 测试（每条都要能红）

```python
def test_empty_manifest_fails(mini_game):
    empty = {
        "schema": 1,
        "layers": {"L1": [], "L2": [], "L3": []},
        "stats": {"l1_count": 0, "coverage": {"l1_sprite_disk": 1.0, "closure_refs": 1.0, "metadata": None}},
    }
    codes = {f.code for f in validate(empty, mini_game) if f.severity == "Critical"}
    assert "empty_l1" in codes


def test_schema_true_is_rejected(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["schema"] = True
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "schema" in codes


def test_l1_count_mismatch_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["l1_count"] = 9999
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "l1_count_mismatch" in codes


def test_cross_layer_duplicate_is_important(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    dup = dict(m["layers"]["L1"][0])
    m["layers"]["L3"].append(dup)
    sev = {(f.code, f.severity) for f in validate(m, mini_game)}
    assert ("cross_layer_duplicate", "Important") in sev


def test_skin_parse_error_is_recorded(mini_game):
    from conftest import _write
    _write(mini_game / "mods" / "mod_a" / "data" / "hulls" / "skins" / "bad.skin", "{not json")
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    lookup = build_lookup(scan.mods)
    result = build_closure(["va_one"], lookup)
    assert any("bad.skin" in k for k in result.stats.parse_errors.get("skin", []))


def test_no_core_get_excludes_core_fallback(mini_game):
    md = read_dds_metadata(mini_game)
    assert md.get("renamed", "graphics/ships/h_core.png", exclude_core=True) is None
    assert md.get("renamed", "graphics/ships/h_core.png", exclude_core=False) is not None
```

预期：`tests/tools` → **84 passed**。修完重跑两份 manifest + 跨 CWD validator，`l1_count` 不变（Base 185 / 260mods 6,614），validator 出现 `cross_layer_duplicate`（44 个 key 的预期 Important，不阻断 exit 0 之外——**若它导致 exit 1 是非预期，需把该 code 定为 Important 且不影响 exit code**）。

---

## E. 执行顺序（避免 `mod_index.py` 写冲突）

1. 先派 Task 2 fix（A1–A5），等它 commit；
2. 再派 Task 3 fix（B1–B4），它依赖 `build_id_index`；
3. 两个 fix 都必须过 scoped re-review。
