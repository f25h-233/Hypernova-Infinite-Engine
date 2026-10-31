import json
import os
import sys
from pathlib import Path

# pytest under `python -I` does not put the repo root on sys.path; tools/ is not
# a package and tests/conftest.py only inserts tools/ itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.m3_phase import _read, main, parse_agent, parse_session, phases


def _line(ms, logger, msg, thread="main"):
    return f"{ms:>6d} [{thread}] INFO  {logger}  - {msg}\n"


def _session_log(mod_anchor=True, menu=True):
    text = _line(100, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2")
    text += _line(7000, "com.genir.renderer.overrides.loading.FileLoaderFast",
                  "Cached 229754 files in 4146ms")
    if mod_anchor:
        text += _line(45000, "com.fs.starfarer.loading.scripts.ScriptStore",
                      "Loading jar files")
    if menu:
        text += _line(61000, "sound.H",
                      "Playing music with id [miscallenous_main_menu.ogg]")
    return text


def _agent_log(mods_mark=True):
    text = "2026-10-31T00:00:00Z INFO hypernova agent premain; config=x\n"
    text += "2026-10-31T00:00:01Z INFO timeline: loader.start rel_ms=100 epoch_ms=1000\n"
    text += "2026-10-31T00:00:02Z INFO timeline: loader.end rel_ms=5000 epoch_ms=5900\n"
    text += "2026-10-31T00:00:03Z INFO timeline: dds.start rel_ms=5010 epoch_ms=5910\n"
    text += "2026-10-31T00:00:04Z INFO timeline: dds.end rel_ms=5500 epoch_ms=6400\n"
    text += "2026-10-31T00:00:05Z INFO timeline: script.loader rel_ms=5200 epoch_ms=6100\n"
    if mods_mark:
        text += "2026-10-31T00:00:06Z INFO timeline: mods.start rel_ms=41000 epoch_ms=41900\n"
    text += "2026-10-31T00:00:07Z INFO timeline: script.first rel_ms=26000 epoch_ms=26900\n"
    text += ("2026-10-31T00:00:08Z INFO find span: first_epoch_ms=25000, "
             "last_epoch_ms=65000, span_ms=40000, finds=10, hits=9, misses=1\n")
    text += ("2026-10-31T00:00:09Z INFO find span: first_epoch_ms=25000, "
             "last_epoch_ms=95000, span_ms=70000, finds=20, hits=9, misses=11\n")
    text += ("2026-10-31T00:00:10Z INFO scripts cache preloaded: key=k, "
             "entries=2113, bytes=1, in 7 ms\n")
    return text


def test_picks_last_session_menu_crawl_and_mod_anchor():
    text = (
        _line(500, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2")
        + _line(60000, "sound.H", "Playing music with id [miscallenous_main_menu.ogg]")
        + _session_log()
    )
    _, start_ms, menu_ms, crawl, mod_anchor_ms = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 60900
    assert crawl == {"files": 229754, "ms": 4146}
    assert mod_anchor_ms == 44900


def test_parses_timeline_find_span_and_phases():
    marks, preload, find_spans = parse_agent(_agent_log())
    assert marks["loader.start"]["rel_ms"] == 100
    assert find_spans == [(25000, 65000), (25000, 95000)]
    assert preload == {"entries": 2113, "ms": 7}

    phases_ms, approx, script_span = phases(marks, 60900, 44900, find_spans)
    assert phases_ms == {
        "initFileLoaders": 5400,
        "initSpecStore": 35500,
        "initMods": 19900,
    }
    assert approx == []
    assert script_span == 40000


def test_missing_mods_start_uses_game_log_fallback_and_marks_approximate():
    marks, _, find_span = parse_agent(_agent_log(mods_mark=False))
    phases_ms, approx, _ = phases(marks, 60900, 44900, find_span)
    # dds.end=5500, fallback mod init=44900, menu=60900
    assert phases_ms == {
        "initFileLoaders": 5400,
        "initSpecStore": 39400,
        "initMods": 16000,
    }
    assert approx == ["initSpecStore", "initMods"]


def test_missing_anchors_produce_no_invented_values():
    marks = {"loader.start": {"rel_ms": 100, "epoch_ms": 1000}}
    phases_ms, approx, script_span = phases(marks, 60900, None, None)
    assert phases_ms == {}
    assert approx == []
    assert script_span is None


def test_missing_anchor_raises():
    import pytest
    with pytest.raises(SystemExit):
        parse_session("no session here\n")


def test_read_decodes_concatenated_log_bytes(tmp_path):
    # Regression: _read() used str.join on bytes, which raises TypeError.
    first = tmp_path / "starsector.log.1"
    second = tmp_path / "starsector.log"
    first.write_bytes(
        _line(100, "com.genir.renderer.agent.Agent",
              "Fast Rendering: v0.9.7rc2").encode("utf-8"))
    second.write_bytes(
        _line(5000, "sound.H",
              "Playing music with id [miscallenous_main_menu.ogg]").encode("utf-8"))
    text = _read([str(first), str(second)])
    assert "Fast Rendering: v0.9.7rc2" in text
    assert "miscallenous_main_menu.ogg" in text
    _, start_ms, menu_ms, _, _ = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 4900


def test_main_writes_schema_json_and_exit_zero(tmp_path):
    game = tmp_path / "starsector.log"
    game.write_text(_session_log(), encoding="utf-8")
    agent = tmp_path / "scripts-agent.log"
    agent.write_text(_agent_log(), encoding="utf-8")
    out = tmp_path / "phase.json"

    rc = main(["--log", str(game), "--agent-log", str(agent), "--json-out", str(out)])

    assert rc == 0
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {
        "session_start_ms", "menu_ms", "crawl", "timeline", "phases_ms",
        "phases_approximate", "scriptSpanMs", "preload"}
    assert data["session_start_ms"] == 100
    assert data["menu_ms"] == 60900
    assert data["crawl"] == {"files": 229754, "ms": 4146}
    assert data["timeline"]["loader.start"] == {"rel_ms": 100, "epoch_ms": 1000}
    assert data["phases_ms"] == {
        "initFileLoaders": 5400,
        "initSpecStore": 35500,
        "initMods": 19900,
    }
    assert data["phases_approximate"] == []
    assert data["scriptSpanMs"] == 40000
    assert data["preload"] == {"entries": 2113, "ms": 7}
    assert isinstance(data["scriptSpanMs"], int)


def test_main_returns_one_and_writes_json_without_menu(tmp_path):
    game = tmp_path / "starsector.log"
    game.write_text(
        _line(100, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2"),
        encoding="utf-8")
    out = tmp_path / "phase.json"

    rc = main(["--log", str(game), "--json-out", str(out)])

    assert rc == 1
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["menu_ms"] is None
    assert data["session_start_ms"] == 100


def test_read_orders_rotated_logs_by_mtime_oldest_first(tmp_path):
    stale = tmp_path / "stale.log"
    fresh = tmp_path / "fresh.log"
    stale.write_bytes(
        _line(500, "com.genir.renderer.agent.Agent",
              "Fast Rendering: v0.9.7rc2").encode("utf-8")
        + _line(60500, "sound.H",
                "Playing music with id [miscallenous_main_menu.ogg]").encode("utf-8"))
    fresh.write_bytes(
        _line(100, "com.genir.renderer.agent.Agent",
              "Fast Rendering: v0.9.7rc2").encode("utf-8")
        + _line(8100, "sound.H",
                "Playing music with id [miscallenous_main_menu.ogg]").encode("utf-8"))
    os.utime(stale, (1_000_000, 1_000_000))
    os.utime(fresh, (2_000_000, 2_000_000))

    # Passed newest-first; _read must reorder by mtime so the last session is fresh.
    text = _read([str(fresh), str(stale)])
    _, start_ms, menu_ms, _, _ = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 8000
