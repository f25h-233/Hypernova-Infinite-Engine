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


def test_baked_coverage_below_one_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    m["stats"]["coverage"]["baked"] = 0.5
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "coverage_baked" in codes


def test_non_finite_baked_coverage_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest

    def codes():
        return {f.code for f in validate(m, mini_game) if f.severity == "Critical"}

    for bad in (
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
        "-Infinity",
        "not-a-number",
    ):
        m["stats"]["coverage"]["baked"] = bad
        assert "coverage_baked" in codes(), bad


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


def test_disk_scan_manifest_passes_without_metadata(mini_game):
    import shutil
    from test_manifest_builder import _seed_core, build_manifest
    shutil.rmtree(mini_game / "mods" / "DDSCache")
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    assert m["stats"]["source_mode"] == "disk_scan"
    assert m["stats"]["coverage"]["metadata"] is None
    assert m["stats"]["coverage"]["baked"] == 1.0
    assert m["stats"]["unresolved_baked_count"] == 0
    assert _good(m, mini_game) == []


def test_baked_coverage_threshold_is_one(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest

    def codes():
        return {f.code for f in validate(m, mini_game) if f.severity == "Critical"}

    m["stats"]["coverage"]["baked"] = 0.95
    assert "coverage_baked" in codes()
    m["stats"]["coverage"]["baked"] = 0.999
    assert "coverage_baked" in codes()
    m["stats"]["coverage"]["baked"] = 1.0
    assert "coverage_baked" not in codes()


def test_valid_mods_tier_has_no_mods_tier(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(
        mini_game, include_l2=False, tier_overrides={"mod_a": "L2"}
    ).manifest
    row = next(r for r in m["mods"] if r["modId"] == "mod_a")
    assert row["tier"] == "L2"
    codes = {f.code for f in validate(m, mini_game) if f.severity == "Critical"}
    assert "mods_tier" not in codes
    assert _good(m, mini_game) == []


def test_string_zero_unresolved_count_is_not_flagged(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest

    def codes():
        return {f.code for f in validate(m, mini_game) if f.severity == "Critical"}

    m["stats"]["unresolved_baked_count"] = "0"
    assert codes() == set()

    # 数字字符串仍按数量处理
    m["stats"]["unresolved_baked"] = ["mod_a/graphics/x.png", "mod_a/graphics/y.png"]
    m["stats"]["unresolved_baked_count"] = "2"
    assert "baked_unresolved" in codes()

    # 无法解释为整数时必须报形状 Critical，不能静默跳过门禁
    m["stats"]["unresolved_baked_count"] = "many"
    assert "baked_unresolved_shape" in codes()
    assert "baked_unresolved" not in codes()


def test_infinite_unresolved_count_does_not_crash(mini_game):
    """json.loads 默认接受 Infinity；非有限值必须报形状 Critical 且不崩溃。"""
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    for bad in (float("inf"), float("-inf")):
        m["stats"]["unresolved_baked_count"] = bad
        findings = validate(m, mini_game)
        codes = {f.code for f in findings if f.severity == "Critical"}
        assert "baked_unresolved_shape" in codes
        assert "baked_unresolved" not in codes


def test_malformed_mods_shape_is_critical(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    base = build_manifest(mini_game, include_l2=False).manifest

    def codes(manifest):
        return {f.code for f in validate(manifest, mini_game) if f.severity == "Critical"}

    m = copy.deepcopy(base)
    m["mods"] = "oops"
    assert "mods_summary" in codes(m)

    m = copy.deepcopy(base)
    m["mods"] = None
    assert "mods_summary" in codes(m)

    m = copy.deepcopy(base)
    m["mods"] = [42]
    assert "mods_summary" in codes(m)

    m = copy.deepcopy(base)
    m["mods"][0]["layers"] = "bad"
    assert "mods_summary" in codes(m)


def test_duplicate_mod_summary_is_case_insensitive(mini_game):
    from test_manifest_builder import _seed_core, build_manifest
    _seed_core(mini_game)
    m = build_manifest(mini_game, include_l2=False).manifest
    zero_entry = next(
        copy.deepcopy(r) for r in m["mods"] if sum(r["layers"].values()) == 0
    )
    zero_entry["modId"] = zero_entry["modId"].upper()
    m["mods"].append(zero_entry)
    sev = {(f.code, f.severity) for f in validate(m, mini_game)}
    assert ("duplicate_mod_summary", "Important") in sev
