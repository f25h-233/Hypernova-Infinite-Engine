import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m28_scene_gate", REPO / "tools/m28_scene_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_parse_summary_line_extracts_ints_and_strings():
    parsed = gate.parse_summary_line(
        "lazy probe: summary queue=1 evictPasses=361 sceneUnload=1 "
        "sceneEvictions=42 main=Thread-3")
    assert parsed["evictPasses"] == 361
    assert parsed["sceneUnload"] == 1
    assert parsed["main"] == "Thread-3"


def test_last_summary_uses_last_matching_line():
    text = ("lazy probe: summary sceneEvictions=1\n"
            "noise\n"
            "lazy probe: summary sceneEvictions=7\n")
    assert gate.last_summary(text)["sceneEvictions"] == 7


def test_last_summary_rejects_missing_line():
    with pytest.raises(ValueError):
        gate.last_summary("nothing here")


def test_last_session_slices_after_anchor():
    text = ("old Fast Rendering: v0.9.5\nold\n"
            "Fast Rendering: v0.9.7rc2\nnew\n")
    assert gate.last_session(text).startswith(
        "Fast Rendering: v0.9.7rc2\nnew")


def test_count_texture_errors_counts_all_five():
    text = ("Failed to load texture\nVerifyError\nClassFormatError\n"
            "AsyncException\nisStateCorrupted\n")
    errors = gate.count_texture_errors(text)
    assert errors == {name: 1 for name in gate.TEXTURE_ERRORS}
    assert sum(errors.values()) == 5


def test_summarize_gpu_skips_empty_samples():
    rows = [(0.0, 100.0, None), (1.0, None, None), (2.0, 300.0, 50.0)]
    gpu = gate.summarize_gpu(rows)
    assert gpu["samples"] == 3
    assert gpu["dedicated_mb"] == {"min": 100.0, "median": 200.0, "max": 300.0}
    assert gpu["shared_mb"] == {"min": 50.0, "median": 50.0, "max": 50.0}


def test_build_report_exposes_scene_fields():
    agent = "lazy probe: summary scenePasses=8 sceneEvictions=64 failedParked=0\n"
    starsector = "Fast Rendering: v0.9.7rc2\nFailed to load texture\n"
    report = gate.build_report(agent, starsector)
    assert report["scene_passes"] == 8
    assert report["scene_evictions"] == 64
    assert report["texture_errors_total"] == 1
    assert report["failed_parked"] == 0
