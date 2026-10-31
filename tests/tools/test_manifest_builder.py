import json
import subprocess
import sys
from pathlib import Path

from conftest import _png, _write
from l1_core import CORE_STATIC, PLANET_FIELDS, PLANET_TYPES
from manifest_builder import build_manifest


def _seed_core(mini_game):
    for rel in CORE_STATIC:
        p = mini_game / "starsector-core" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_png(2, 2))
    planets = {}
    for t in PLANET_TYPES:
        planets[t] = {f: f"graphics/planets/{t}_{f}.jpg" for f in PLANET_FIELDS}
        for f in PLANET_FIELDS:
            p = mini_game / "starsector-core" / planets[t][f]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(_png(2, 2))
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        json.dumps(planets),
    )


def _build(mini_game, **kwargs):
    _seed_core(mini_game)
    return build_manifest(mini_game, **kwargs).manifest


def test_l1_contains_core_and_closure(mini_game):
    m = _build(mini_game)
    paths = {e["path"] for e in m["layers"]["L1"]}
    assert "graphics/ui/starsector_title_alpha.png" in paths
    assert "graphics/ships/h_alpha.png" in paths
    assert "graphics/weapons/w_gun_t.png" in paths
    assert "graphics/ships/h_module.png" in paths
    assert "graphics/ships/h_fighter.png" in paths
    assert "graphics/ships/h_core.png" in paths


def test_l2_entity_pool_contains_orphan_variant(mini_game):
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_orphan.variant",
        '{"variantId": "va_orphan", "hullId": "h_orphan"}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_orphan.ship",
        '{"hullId": "h_orphan", "hullSize": "FRIGATE", '
        '"spriteName": "graphics/ships/h_orphan.png"}',
    )
    p = mini_game / "mods" / "mod_a" / "graphics" / "ships" / "h_orphan.png"
    p.write_bytes(_png(5, 5))
    m = _build(mini_game)
    l2 = {e["path"] for e in m["layers"]["L2"]}
    assert "graphics/ships/h_orphan.png" in l2


def test_l3_contains_remaining_metadata_and_disk_images(mini_game):
    p = mini_game / "mods" / "mod_a" / "graphics" / "other.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_png(9, 9))
    m = _build(mini_game)
    l3 = {e["path"] for e in m["layers"]["L3"]}
    assert "graphics/other.png" in l3
    assert "graphics/unlisted.png" in l3
    assert "graphics/ships/h_alpha.png" not in l3


def test_scope_and_stats(mini_game):
    m = _build(mini_game)
    stats = m["stats"]
    assert stats["scope"] == "mod_non_shader"
    assert stats["metadata_entries"] == 2
    assert stats["core_entries"] == 1
    assert stats["baked"] == 2
    assert stats["coverage"]["metadata"] == 1.0
    assert stats["coverage"]["closure_refs"] == 1.0
    assert stats["coverage"]["l1_sprite_disk"] == 1.0


def test_no_l2_and_no_core(mini_game):
    m = _build(mini_game, include_l2=False, include_core=False)
    assert m["layers"]["L2"] == []
    assert m["stats"]["core_entries"] == 0


def test_manifest_is_deterministic(mini_game):
    a = _build(mini_game)
    b = _build(mini_game)
    assert a["layers"] == b["layers"]
    assert a["stats"] == b["stats"]


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


def test_no_core_does_not_borrow_core_metadata_for_mod_sprite(mini_game):
    """回归：`_sprite_entry` 忘记传 exclude_core 时，mod 图会借用 core 的 metadata
    （baked=True、ddsPath 落进 DDSCache/starsector-core）。"""
    _seed_core(mini_game)
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_core_borrow.variant",
        '{"variantId": "va_core_borrow", "hullId": "h_core_borrow"}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_core_borrow.ship",
        '{"hullId": "h_core_borrow", "hullSize": "FRIGATE", '
        '"spriteName": "graphics/ships/core_only.png"}',
    )
    p = mini_game / "mods" / "mod_a" / "graphics" / "ships" / "core_only.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_png(5, 5))
    _write(
        mini_game / "mods" / "DDSCache" / "starsector-core" / "dds_metadata.json",
        json.dumps([{
            "ModFolderName": "starsector-core",
            "RelativeImagePath": "graphics/ships/core_only.png",
            "DDSFilePath": "\\mods\\DDSCache\\starsector-core\\graphics\\ships\\core_only.dds",
            "Width": 4, "Height": 4,
        }]),
    )
    m = build_manifest(mini_game, include_core=False).manifest
    entry = next(
        e
        for e in m["layers"]["L2"]
        if e["path"] == "graphics/ships/core_only.png"
    )
    assert entry["modId"] == "mod_a"
    assert entry["baked"] is False
    assert entry["ddsPath"] is None


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


def test_empty_l1_coverage_is_zero(tmp_path):
    """回归：空 L1 时 l1_sprite_disk 曾返回 1.0，给空输入发通行证。"""
    root = tmp_path / "empty_game"
    _write(root / "mods" / "enabled_mods.json", '{"enabledMods": []}')
    m = build_manifest(root, include_core=False, include_l2=False).manifest
    assert m["layers"]["L1"] == []
    assert m["stats"]["coverage"]["l1_sprite_disk"] == 0.0


def test_variant_limit_truncates_pool(mini_game):
    a = _build(mini_game, variant_limit=1)
    b = _build(mini_game)
    assert len(a["layers"]["L2"]) <= len(b["layers"]["L2"])


def test_paths_absolute_against_relative_game_root(mini_game, monkeypatch):
    """回归：入口忘记 resolve() 时，用相对 game_root 必须仍产出绝对路径。"""
    _seed_core(mini_game)
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
    """回归：改回 l3.append 会让同 id 双文件夹产出重复键。

    F2 的 enabled_folders 过滤会让未启用的 mod_a_copy 文件夹在进 L3 前被剔除，
    因此这里构造当前实现下唯一可达的同 id 双文件夹：一个 mod 的 id 声明为
    "core"，与 starsector-core 的 modId 相同，两个 metadata 条目同 rel 同 id。
    """
    import json as _json
    from conftest import _write
    _write(
        mini_game / "mods" / "enabled_mods.json",
        _json.dumps(
            {
                "enabledMods": [
                    "mod_a",
                    "mod_b",
                    "mod_[x]",
                    "mod_中文",
                    "shaderLib",
                    "GraphicsLib",
                    "core",
                ]
            }
        ),
    )
    _write(mini_game / "mods" / "core_mod" / "mod_info.json", '{"id": "core"}')
    _write(
        mini_game / "mods" / "DDSCache" / "core_mod" / "dds_metadata.json",
        _json.dumps([{
            "ModFolderName": "core_mod",
            "RelativeImagePath": "graphics/ships/h_alpha.png",
            "DDSFilePath": "\\mods\\DDSCache\\core_mod\\graphics\\ships\\h_alpha.dds",
            "Width": 64, "Height": 32,
        }]),
    )
    _write(
        mini_game / "mods" / "DDSCache" / "starsector-core" / "dds_metadata.json",
        _json.dumps([{
            "ModFolderName": "starsector-core",
            "RelativeImagePath": "graphics/ships/h_alpha.png",
            "DDSFilePath": "\\mods\\DDSCache\\starsector-core\\graphics\\ships\\h_alpha.dds",
            "Width": 64, "Height": 32,
        }]),
    )
    m = build_manifest(mini_game, include_l2=False).manifest
    keys = [(e["modId"], e["path"].casefold()) for e in m["layers"]["L3"]]
    assert len(keys) == len(set(keys))


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


def test_cli_writes_manifest(mini_game):
    _seed_core(mini_game)
    out = mini_game / "out.json"
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            str(root / "tools" / "gen_manifest.py"),
            "--game-root",
            str(mini_game),
            "--out",
            str(out),
            "--no-l2",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["layers"]["L1"]
