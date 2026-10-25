import json

import pytest

from mod_index import (
    build_image_index,
    build_index,
    in_scope,
    load_enabled_ids,
    pick,
    read_dds_metadata,
    read_title_variants,
    read_wing_map,
    scan_mods,
)


def test_enabled_ids_order(mini_game):
    assert load_enabled_ids(mini_game) == [
        "mod_a", "mod_b", "mod_[x]", "mod_中文", "shaderLib", "GraphicsLib", "missing_mod",
    ]


def test_scan_mods_handles_brackets_chinese_and_missing(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    ids = [m.mod_id for m in scan.mods]
    assert ids[:4] == ["mod_a", "mod_b", "mod_[x]", "mod_中文"]
    assert ids[-1] == "core"
    assert scan.missing_ids == ["missing_mod"]
    assert scan.parse_errors == {}


def test_scan_mods_duplicate_id(mini_game):
    from conftest import _write
    _write(mini_game / "mods" / "mod_a_copy" / "mod_info.json", '{"id": "mod_a"}')
    scan = scan_mods(mini_game, ["mod_a"])
    assert scan.duplicate_ids == {"mod_a": ["mod_a", "mod_a_copy"]}
    assert scan.mods[0].folder.name == "mod_a"


def test_pick_prefers_enabled_order(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    index = build_index(scan.mods, "variants", frozenset({".variant"}))
    chosen = pick(index["va_one"])
    assert chosen.mod_id == "mod_a"


def test_title_variants_comments_quotes_and_core(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    tv = read_title_variants(scan.mods)
    assert tv.ids == ["va_one", "va_two", "v_core"]
    assert tv.sources["va_one"] == ["mod_a"]


def test_wing_map(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    assert read_wing_map(scan.mods) == {"wing_one": "wing_one_Fighter"}


def test_image_index_is_case_insensitive(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    images = build_image_index(scan.mods)
    assert images["graphics/ships/h_alpha.png"][0].mod_id == "mod_a"
    assert len(images["graphics/ships/h_alpha.png"]) == 2


def test_metadata_index_backslash_and_fallback(mini_game):
    md = read_dds_metadata(mini_game)
    assert len(md.entries) == 3
    hit = md.get("mod_a", "graphics/ships/h_alpha.png")
    assert (hit.width, hit.height) == (64, 32)
    assert hit.dds_rel == "mods/DDSCache/mod_a/graphics/ships/h_alpha.dds"
    assert md.get("Mod_A", "GRAPHICS/SHIPS/H_ALPHA.PNG") is not None


def test_scope_counts(mini_game):
    md = read_dds_metadata(mini_game)
    assert [me.mod_folder for me in md.entries if in_scope(me, "all_mod_metadata")] == ["mod_a", "mod_a"]
    assert [me.mod_folder for me in md.entries if in_scope(me, "mod_non_shader")] == ["mod_a", "mod_a"]
    assert not in_scope(md.get("starsector-core", "graphics/ships/h_core.png"), "all_mod_metadata")
