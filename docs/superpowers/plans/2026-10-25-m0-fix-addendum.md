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

## D. 执行顺序（避免 `mod_index.py` 写冲突）

1. 先派 Task 2 fix（A1–A5），等它 commit；
2. 再派 Task 3 fix（B1–B4），它依赖 `build_id_index`；
3. 两个 fix 都必须过 scoped re-review。
