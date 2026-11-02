import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m28_scene_gate", REPO / "tools/m28_scene_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

ANCHOR = "2026-11-02T00:00:00Z INFO hypernova agent premain; config=test"
STAR = "Fast Rendering: v0.9.7rc2"
SUMMARY_VALUES = {
    "queue": 12,
    "failedParked": 0,
    "sceneUnload": 1,
    "scenePasses": 3,
    "sceneEvictions": 5,
    "sceneEvictMsTotal": 20,
    "sceneEvictMsMax": 7,
    "scenePending": 0,
}


def _summary(**overrides):
    values = dict(SUMMARY_VALUES)
    values.update(overrides)
    return "lazy probe: summary " + " ".join(
        f"{key}={value}" for key, value in values.items())


def _agent(*lines):
    return "\n".join((ANCHOR, *lines)) + "\n"


def _write_run(tmp_path, agent_text, starsector_text):
    agent = tmp_path / "agent.log"
    starsector = tmp_path / "starsector.log"
    agent.write_text(agent_text, encoding="utf-8")
    starsector.write_text(starsector_text, encoding="utf-8")
    return agent, starsector


def _main_args(agent, starsector, *extra):
    return ["--agent-log", str(agent), "--starsector-log", str(starsector),
            *extra]


def test_parse_summary_line_extracts_ints_and_strings():
    parsed = gate.parse_summary_line(
        "lazy probe: summary queue=1 evictPasses=361 sceneUnload=1 "
        "sceneEvictions=42 main=Thread-3")
    assert parsed["evictPasses"] == 361
    assert parsed["sceneUnload"] == 1
    assert parsed["main"] == "Thread-3"


def test_agent_session_uses_last_anchor():
    text = f"{ANCHOR}\nold\n{ANCHOR}\nnew\n"
    session, anchor_line, anchor_count = gate.agent_session(text)
    assert session == "new\n"
    assert anchor_line == 3
    assert anchor_count == 2


def test_agent_session_without_anchor_returns_input():
    session, anchor_line, anchor_count = gate.agent_session("a\nb\n")
    assert session == "a\nb\n"
    assert anchor_line is None
    assert anchor_count == 0


def test_last_summary_uses_last_valid_line():
    text = _agent(_summary(sceneEvictions=1), "noise",
                  _summary(sceneEvictions=7))
    assert gate.last_summary(text)["sceneEvictions"] == 7


def test_last_summary_rejects_missing_anchor():
    with pytest.raises(ValueError, match="agent session anchor"):
        gate.last_summary(_summary())


def test_last_summary_rejects_missing_summary_after_anchor():
    with pytest.raises(ValueError, match="anchor line 1"):
        gate.last_summary(_agent("no summary here"))


def test_last_summary_rejects_summary_failed():
    text = _agent("2026-11-02T00:00:01Z ERROR lazy probe: summary failed")
    with pytest.raises(ValueError, match="sceneUnload"):
        gate.last_summary(text)


def test_last_summary_rejects_old_format_missing_scene_keys():
    text = _agent("2026-11-02T00:00:01Z INFO lazy probe: summary "
                  "queue=1 failedParked=0")
    with pytest.raises(ValueError, match="sceneUnload"):
        gate.last_summary(text)


def test_last_summary_rejects_truncated_summary():
    truncated = _summary().replace(" scenePending=0", " scenePending")
    with pytest.raises(ValueError, match="scenePending"):
        gate.last_summary(_agent(truncated))


def test_find_summary_reports_line_and_anchor_evidence():
    text = f"{ANCHOR}\nnoise\n{_summary(sceneEvictions=9)}\n"
    summary, summary_line, anchor_line, anchor_count = gate.find_summary(text)
    assert summary["sceneEvictions"] == 9
    assert summary_line == 3
    assert anchor_line == 1
    assert anchor_count == 1


def test_find_summary_uses_last_anchor_across_sessions():
    text = (f"{ANCHOR}\n{_summary(sceneEvictions=111)}\n"
            f"{ANCHOR}\n{_summary(sceneEvictions=222)}\n")
    summary, summary_line, anchor_line, anchor_count = gate.find_summary(text)
    assert summary["sceneEvictions"] == 222
    assert summary_line == 4
    assert anchor_line == 3
    assert anchor_count == 2


def test_find_summary_rejects_old_format_after_last_anchor():
    text = (f"{ANCHOR}\n{_summary(sceneEvictions=111)}\n"
            f"{ANCHOR}\nlazy probe: summary queue=2 failedParked=0\n")
    with pytest.raises(ValueError, match="anchor line 3"):
        gate.find_summary(text)
    with pytest.raises(ValueError, match="sceneUnload"):
        gate.find_summary(text)


def test_last_session_slices_after_anchor():
    text = f"old Fast Rendering: v0.9.5\nold\n{STAR}\nnew\n"
    session, found, anchor_line, anchor_count = gate.last_session(text)
    assert session == f"{STAR}\nnew\n"
    assert found is True
    assert anchor_line == 3
    assert anchor_count == 2


def test_last_session_without_anchor_reports_missing():
    session, found, anchor_line, anchor_count = gate.last_session("plain")
    assert session == "plain"
    assert found is False
    assert anchor_line is None
    assert anchor_count == 0


def test_count_texture_errors_counts_all_five():
    text = ("Failed to load texture\nVerifyError\nClassFormatError\n"
            "AsyncException\nisStateCorrupted\n")
    errors = gate.count_texture_errors(text)
    assert errors == {name: 1 for name in gate.TEXTURE_ERRORS}
    assert sum(errors.values()) == 5


def test_summarize_gpu_skips_empty_samples():
    rows = [(0.0, 100.0, None), (1.0, None, None),
            (2.0, 300.0, 50.0), (3.0, 100.0, None)]
    gpu = gate.summarize_gpu(rows)
    assert gpu["samples"] == 4
    assert gpu["dedicated_mb"] == {"min": 100.0, "median": 100.0, "max": 300.0}
    assert gpu["shared_mb"] == {"min": 50.0, "median": 50.0, "max": 50.0}


def test_summarize_gpu_empty_input_has_none_stats():
    gpu = gate.summarize_gpu([])
    assert gpu["samples"] == 0
    assert gpu["dedicated_mb"] is None
    assert gpu["shared_mb"] is None


def test_summarize_gpu_filters_nonfinite_values():
    rows = [(0.0, float("inf"), 10.0), (1.0, float("nan"), 20.0)]
    gpu = gate.summarize_gpu(rows)
    assert gpu["dedicated_mb"] is None
    assert gpu["shared_mb"] == {"min": 10.0, "median": 15.0, "max": 20.0}


def test_read_gpu_csv_reports_bad_rows_and_bom(tmp_path):
    path = tmp_path / "gpu.csv"
    path.write_text(
        "﻿timestamp, dedicated_mb , shared_mb\n"
        "0,100,20\n"
        "1,oops,None\n"
        "2,,\n"
        "3,300,N/A\n"
        "oops,1,2\n",
        encoding="utf-8")
    rows, bad_rows = gate.read_gpu_csv(path)
    assert rows == [
        (0.0, 100.0, 20.0),
        (1.0, None, None),
        (2.0, None, None),
        (3.0, 300.0, None),
    ]
    assert bad_rows == 4


def test_build_report_exposes_scene_fields_and_evidence():
    agent = _agent(_summary(failedParked=2))
    starsector = f"{STAR}\nFailed to load texture\n"
    report = gate.build_report(agent, starsector)
    assert report["scene_unload"] == 1
    assert report["scene_passes"] == 3
    assert report["scene_evictions"] == 5
    assert report["scene_evict_ms_total"] == 20
    assert report["scene_evict_ms_max"] == 7
    assert report["scene_pending"] == 0
    assert report["failed_parked"] == 2
    assert report["texture_errors_total"] == 1
    assert report["summary_line"] == 2
    assert report["agent_session_anchor_line"] == 1
    assert report["agent_session_count"] == 1
    assert report["session_anchor_found"] is True
    assert report["session_anchor_line"] == 1
    assert report["session_count"] == 1


def test_build_report_rejects_missing_scene_key():
    agent = _agent("lazy probe: summary queue=1 failedParked=0")
    with pytest.raises(ValueError, match="sceneUnload"):
        gate.build_report(agent, f"{STAR}\n")


def test_build_report_rejects_non_int_scene_key():
    agent = _agent(_summary(scenePasses="oops"))
    with pytest.raises(ValueError, match="scenePasses"):
        gate.build_report(agent, f"{STAR}\n")


def test_build_report_marks_missing_session_anchor():
    agent = _agent(_summary())
    report = gate.build_report(agent, "plain\nFailed to load texture\n")
    assert report["session_anchor_found"] is False
    assert report["session_anchor_line"] is None
    assert report["session_count"] == 0
    assert report["texture_errors_total"] == 1


def test_main_clean_strict_returns_zero(tmp_path, capsys):
    agent, starsector = _write_run(tmp_path, _agent(_summary()), f"{STAR}\n")
    assert gate.main(_main_args(agent, starsector, "--strict")) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["scene_evictions"] == 5


def test_main_texture_error_returns_one(tmp_path, capsys):
    agent, starsector = _write_run(
        tmp_path, _agent(_summary()), f"{STAR}\nFailed to load texture\n")
    assert gate.main(_main_args(agent, starsector, "--strict")) == 1
    captured = capsys.readouterr()
    assert "texture errors=1" in captured.err
    assert json.loads(captured.out)["texture_errors_total"] == 1


def test_main_require_scene_implies_strict(tmp_path, capsys):
    agent, starsector = _write_run(
        tmp_path, _agent(_summary(sceneEvictions=0)), f"{STAR}\n")
    assert gate.main(_main_args(agent, starsector, "--require-scene")) == 1
    captured = capsys.readouterr()
    assert "require-scene" in captured.err


def test_main_bad_summary_returns_one_and_no_json(tmp_path, capsys):
    out = tmp_path / "out.json"
    agent, starsector = _write_run(
        tmp_path,
        _agent("lazy probe: summary queue=1 failedParked=0"),
        f"{STAR}\n")
    assert gate.main(_main_args(
        agent, starsector, "--strict", "--out", str(out))) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("m28_scene_gate:")
    assert not out.exists()


def test_main_missing_session_anchor_strict_returns_one(tmp_path, capsys):
    agent, starsector = _write_run(
        tmp_path, _agent(_summary()), "no session anchor\n")
    assert gate.main(_main_args(agent, starsector, "--strict")) == 1
    captured = capsys.readouterr()
    assert "no Fast Rendering session anchor" in captured.err


def test_main_empty_gpu_csv_returns_two(tmp_path, capsys):
    agent, starsector = _write_run(tmp_path, _agent(_summary()), f"{STAR}\n")
    gpu = tmp_path / "gpu.csv"
    gpu.write_text("timestamp,dedicated_mb,shared_mb\n", encoding="utf-8")
    assert gate.main(_main_args(
        agent, starsector, "--gpu-csv", str(gpu))) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no valid GPU samples" in captured.err


def test_main_reports_gpu_bad_rows(tmp_path, capsys):
    agent, starsector = _write_run(tmp_path, _agent(_summary()), f"{STAR}\n")
    gpu = tmp_path / "gpu.csv"
    gpu.write_text(
        "timestamp,dedicated_mb,shared_mb\n0,100,20\n1,oops,30\n",
        encoding="utf-8")
    assert gate.main(_main_args(
        agent, starsector, "--gpu-csv", str(gpu))) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["gpu"]["samples"] == 2
    assert report["gpu_bad_rows"] == 1


def test_main_missing_input_file_has_clean_error(tmp_path, capsys):
    _, starsector = _write_run(tmp_path, _agent(_summary()), f"{STAR}\n")
    missing = tmp_path / "missing.log"
    assert gate.main([
        "--agent-log", str(missing),
        "--starsector-log", str(starsector),
    ]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("m28_scene_gate:")
