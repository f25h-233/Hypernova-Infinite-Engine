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


def test_no_core_get_excludes_core_fallback(mini_game):
    md = read_dds_metadata(mini_game)
    # by_rel 唯一回退路径
    assert md.get("renamed", "graphics/ships/h_core.png", exclude_core=True) is None
    assert md.get("renamed", "graphics/ships/h_core.png", exclude_core=False) is not None
    # by_key 直命中路径
    assert md.get("starsector-core", "graphics/ships/h_core.png", exclude_core=True) is None
    assert md.get("starsector-core", "graphics/ships/h_core.png", exclude_core=False) is not None


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
