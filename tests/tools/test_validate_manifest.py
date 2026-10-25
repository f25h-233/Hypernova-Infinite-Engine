import copy
import json

from validate_manifest import validate


def _good(manifest, game_root):
    return [f for f in validate(manifest, game_root) if f.severity == "Critical"]


def test_good_manifest_has_no_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    assert _good(m, mini_game) == []


def test_bad_schema_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["schema"] = 99
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "schema" in codes


def test_missing_absolute_path_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"][0]["absolutePath"] = str(mini_game / "nope.png")
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "missing_file" in codes


def test_duplicate_path_in_layer_is_important(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"].append(copy.deepcopy(m["layers"]["L1"][0]))
    sev = {(f.code, f.severity) for f in validate(m, mini_game)}
    assert ("duplicate_entry", "Important") in sev


def test_l1_too_large_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    findings = validate(m, mini_game, max_l1=1)
    assert any(f.code == "l1_too_large" and f.severity == "Critical" for f in findings)


def test_low_coverage_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"]["l1_sprite_disk"] = 0.5
    findings = validate(m, mini_game)
    assert any(f.code == "coverage_l1_sprite_disk" and f.severity == "Critical" for f in findings)


def test_metadata_parse_errors_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["metadata_parse_errors"] = {"broken": "bad json"}
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "metadata_parse_errors" in codes


def test_core_parse_errors_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["core_parse_errors"] = {"planets.json": "bad json"}
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "core_parse_errors" in codes
