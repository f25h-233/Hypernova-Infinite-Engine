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

    # 未烘焙条目的绝对路径也必须在 game_root 内
    plain = next(e for e in m["layers"]["L1"] if not e["baked"])
    outside_png = tmp_path / "elsewhere.png"
    outside_png.write_bytes(b"\x89PNG\r\n\x1a\n")
    plain["absolutePath"] = str(outside_png)
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "asset_outside_root" in codes


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


def test_entry_schema_missing_key_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["layers"]["L1"][0].pop("src")
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "entry_schema" in codes


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
    assert isinstance(m["stats"]["path_conflicts"], list)
