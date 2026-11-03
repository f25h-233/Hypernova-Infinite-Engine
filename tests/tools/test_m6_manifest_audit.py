import hashlib
import json
from pathlib import Path

import pytest

from install_manifest import install
from m6_manifest_audit import (
    DEFAULT_REL,
    HYPERNOVA_REL,
    audit_fail_open,
    audit_installed,
    main,
)
from test_manifest_builder import _seed_core


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_hypernova(
    root: Path,
    *,
    textures_enabled: bool = False,
    lazy: bool = False,
    eviction: bool = False,
    scene_unload: bool = False,
    include_scene: bool = True,
) -> None:
    eviction_cfg = {"enabled": eviction}
    if include_scene:
        eviction_cfg["scene_unload"] = {"enabled": scene_unload}
    _write(
        root / HYPERNOVA_REL,
        json.dumps({
            "textures": {
                "enabled": textures_enabled,
                "lazy": {"enabled": lazy, "eviction": eviction_cfg},
            }
        }),
    )


def _seed_hypernova_raw(root: Path, config: dict) -> None:
    _write(root / HYPERNOVA_REL, json.dumps(config))


def _skip_paths(root: Path) -> tuple[Path, Path]:
    skip_dir = root / DEFAULT_REL.parent
    return skip_dir / "lazy-skip-v1.txt", skip_dir / "lazy-skip-v2.txt"


def _seed_empty_manifest(root: Path) -> str:
    manifest = root / DEFAULT_REL
    _write(
        manifest,
        json.dumps({"schema": "hypernova-runtime-1", "layers": {}}),
    )
    generation = hashlib.sha256(manifest.read_bytes()).hexdigest()
    skip_v1, skip_v2 = _skip_paths(root)
    _write(skip_v1, f"# generation={generation}\n")
    _write(skip_v2, f"# generation={generation}\n")
    return generation


def test_audit_installed_reports_healthy_generation(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game)
    install(mini_game)
    report = audit_installed(mini_game)
    assert report["ok"] is True
    assert report["manifest"]["exists"] is True
    assert report["manifest"]["sha256"] == report["skip_v1"]["generation"]
    assert report["manifest"]["sha256"] == report["skip_v2"]["generation"]
    assert report["host_pollution"]["found"] == []
    assert report["defaults"]["textures_enabled"] is False
    assert report["defaults"]["textures_enabled_explicit"] is True
    assert report["defaults"]["lazy"] is False
    assert report["defaults"]["eviction"] is False
    assert report["defaults"]["scene_unload"] is False


def test_audit_installed_reads_nested_scene_unload(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(
        mini_game,
        textures_enabled=True,
        lazy=True,
        eviction=True,
        scene_unload=True,
    )
    install(mini_game)
    report = audit_installed(mini_game)
    assert report["defaults"]["scene_unload"] is True
    assert report["defaults"]["lazy"] is True
    assert report["defaults"]["eviction"] is True
    assert report["ok"] is False
    assert "default_not_off" in report["findings"]


def test_audit_installed_scene_unload_missing_key_defaults_false(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game, include_scene=False)
    install(mini_game)
    report = audit_installed(mini_game)
    assert report["defaults"]["scene_unload"] is False
    assert report["ok"] is True


def test_audit_installed_flags_generation_mismatch(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game)
    result = install(mini_game)
    result.skip_file.write_text("# generation=deadbeef\n", encoding="utf-8")
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "skip_v1_generation_mismatch" in report["findings"]


def test_audit_installed_flags_missing_generation_header(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game)
    result = install(mini_game)
    result.skip_file.write_text("no header\n", encoding="utf-8")
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "skip_v1_generation_mismatch" in report["findings"]


def test_audit_installed_flags_host_lazy_skip(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game)
    install(mini_game)
    (mini_game / "starsector-core" / "lazy-skip-v2.txt").write_text(
        "x\n", encoding="utf-8"
    )
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "host_lazy_skip" in report["findings"]


def test_audit_installed_flags_missing_skip(mini_game):
    _seed_core(mini_game)
    _seed_hypernova(mini_game)
    result = install(mini_game)
    result.skip_file.unlink()
    result.skip_v2_file.unlink()
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "skip_v1_missing" in report["findings"]
    assert "skip_v2_missing" in report["findings"]


def test_audit_installed_flags_missing_manifest(tmp_path):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    _seed_hypernova(game)
    skip_v1, skip_v2 = _skip_paths(game)
    _write(skip_v1, "# generation=deadbeef\n")
    _write(skip_v2, "# generation=deadbeef\n")
    report = audit_installed(game)
    assert report["ok"] is False
    assert "manifest_missing" in report["findings"]
    assert "skip_v1_generation_unpaired" in report["findings"]
    assert "skip_v2_generation_unpaired" in report["findings"]


def test_audit_installed_flags_empty_manifest(tmp_path):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    _seed_hypernova(game)
    _seed_empty_manifest(game)
    report = audit_installed(game)
    assert report["ok"] is False
    assert report["manifest"]["l1"] == 0
    assert "manifest_empty" in report["findings"]


def test_audit_installed_flags_missing_config_and_core(tmp_path):
    game = tmp_path / "game"
    manifest = game / DEFAULT_REL
    _write(
        manifest,
        json.dumps({
            "schema": "hypernova-runtime-1",
            "layers": {"L1": [{"path": "graphics/ui/x.png"}]},
        }),
    )
    generation = hashlib.sha256(manifest.read_bytes()).hexdigest()
    skip_v1, skip_v2 = _skip_paths(game)
    _write(skip_v1, f"# generation={generation}\n")
    _write(skip_v2, f"# generation={generation}\n")
    report = audit_installed(game)
    assert report["ok"] is False
    assert "hypernova_config_missing" in report["findings"]
    assert "core_dir_missing" in report["findings"]


def test_audit_installed_tolerates_invalid_config_shape(mini_game):
    _seed_core(mini_game)
    _seed_hypernova_raw(mini_game, {"textures": True})
    install(mini_game)
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "hypernova_config_invalid" in report["findings"]
    assert report["defaults"]["textures_enabled"] is True
    assert report["defaults"]["lazy"] is False


def test_audit_fail_open_handles_broken_mods(tmp_path):
    report = audit_fail_open(tmp_path / "fail-open")
    assert report["ok"] is True
    assert report["duplicate_ids"] == {"dup_same": ["dup_a", "dup_b"]}
    assert report["parse_errors"] == {}
    assert report["manifest_written"] is True
    assert report["missing_mod_ids"] == ["missing_mod"]
    assert "tail_mod" in report["scanned_mod_ids"]
    assert report["source_mode"] == "disk_scan"
    assert report["metadata_fallback_hits"] == 0
    assert report["good_mod_baked"] is False


def test_audit_fail_open_covers_dds_and_skip_scenarios(tmp_path):
    report = audit_fail_open(tmp_path / "fail-open")
    scenarios = report["scenarios"]
    assert set(scenarios) == {
        "broken_mods",
        "bad_metadata",
        "missing_dds",
        "missing_skip_rerun",
    }
    bad = scenarios["bad_metadata"]
    assert bad["ok"] is True
    assert bad["manifest_written"] is False
    assert "Critical:metadata_parse_errors" in bad["findings"]
    assert bad["metadata_parse_errors"]
    missing = scenarios["missing_dds"]
    assert missing["ok"] is True
    assert missing["manifest_written"] is False
    assert "Critical:missing_dds" in missing["findings"]
    rerun = scenarios["missing_skip_rerun"]
    assert rerun["ok"] is True
    assert rerun["skip_removed_before_rerun"] is True
    assert rerun["manifest_written"] is True
    assert rerun["generation_matches"] is True


def test_audit_fail_open_accepts_empty_existing_workdir(tmp_path):
    base = tmp_path / "fail-open"
    base.mkdir()
    assert audit_fail_open(base)["ok"] is True


def test_audit_fail_open_rejects_unsafe_workdir(mini_game):
    with pytest.raises(ValueError):
        audit_fail_open(mini_game / "fail-open", game_root=mini_game)
    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError):
        audit_fail_open(repo_root / ".cache" / "m6-test-fail-open")


def test_cli_fail_closed_has_one_line_stderr(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    assert main(["--game-root", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("FATAL:")
    assert len(captured.err.strip().splitlines()) == 1


def test_cli_bad_out_path_is_one_line_failure(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    assert main(["--game-root", str(root), "--out", str(out_dir)]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("FATAL:")
    assert len(captured.err.strip().splitlines()) == 1


def test_cli_fail_open_out_is_explicit(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    out = tmp_path / "evidence.json"
    explicit = tmp_path / "explicit-fail-open.json"
    assert main([
        "--game-root", str(root),
        "--out", str(out),
        "--fail-open-dir", str(tmp_path / "fail-open"),
        "--fail-open-out", str(explicit),
    ]) == 1
    assert out.is_file()
    assert explicit.is_file()
    assert not (tmp_path / "fail-open.json").exists()


def test_cli_rejects_unsafe_fail_open_dir(mini_game, capsys):
    assert main([
        "--game-root", str(mini_game),
        "--fail-open-dir", str(mini_game / "fail-open"),
    ]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("FATAL:")
    assert len(captured.err.strip().splitlines()) == 1
