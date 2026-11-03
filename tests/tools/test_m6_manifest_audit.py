import json
from pathlib import Path

import pytest

from install_manifest import install
from m6_manifest_audit import audit_fail_open, audit_installed
from test_manifest_builder import _seed_core


def test_audit_installed_reports_healthy_generation(mini_game):
    _seed_core(mini_game)
    install(mini_game)
    report = audit_installed(mini_game)
    assert report["ok"] is True
    assert report["manifest"]["exists"] is True
    assert report["manifest"]["sha256"] == report["skip_v1"]["generation"]
    assert report["manifest"]["sha256"] == report["skip_v2"]["generation"]
    assert report["host_pollution"]["found"] == []
    assert report["defaults"]["lazy"] is False
    assert report["defaults"]["eviction"] is False
    assert report["defaults"]["scene_unload"] is False


def test_audit_installed_flags_generation_mismatch(mini_game):
    _seed_core(mini_game)
    result = install(mini_game)
    result.skip_file.write_text("# generation=deadbeef\n", encoding="utf-8")
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "skip_v1_generation_mismatch" in report["findings"]


def test_audit_installed_flags_host_lazy_skip(mini_game):
    _seed_core(mini_game)
    install(mini_game)
    (mini_game / "starsector-core" / "lazy-skip-v2.txt").write_text(
        "x\n", encoding="utf-8"
    )
    report = audit_installed(mini_game)
    assert report["ok"] is False
    assert "host_lazy_skip" in report["findings"]


def test_audit_fail_open_handles_broken_mods(tmp_path):
    report = audit_fail_open(tmp_path / "fail-open")
    assert report["ok"] is True
    assert report["duplicate_ids"] != {}
    assert report["parse_errors"] == {}
    assert report["manifest_written"] is True
