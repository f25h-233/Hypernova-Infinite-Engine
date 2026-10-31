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


def test_picks_last_session_and_menu():
    text = (
        _line(500, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2")
        + _line(60000, "sound.H", "Playing music with id [miscallenous_main_menu.ogg]")
        + _line(100, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2")
        + _line(7000, "com.genir.renderer.overrides.loading.FileLoaderFast",
                "Cached 229754 files in 4146ms")
        + _line(61000, "sound.H", "Playing music with id [miscallenous_main_menu.ogg]")
    )
    _, start_ms, menu_ms, crawl = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 60900
    assert crawl == {"files": 229754, "ms": 4146}


def test_parses_agent_timeline_and_preload():
    agent = (
        "2026-10-31T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-10-31T00:00:01Z INFO timeline: initFileLoaders.start rel_ms=100 epoch_ms=1000\n"
        "2026-10-31T00:00:05Z INFO timeline: initFileLoaders.end rel_ms=5000 epoch_ms=5900\n"
        "2026-10-31T00:00:06Z INFO scripts cache preloaded: key=k, entries=2113, bytes=1, in 7 ms\n"
    )
    marks, preload = parse_agent(agent)
    assert marks["initFileLoaders.start"]["rel_ms"] == 100
    assert phases(marks)["initFileLoaders"] == 4900
    assert preload == {"entries": 2113, "ms": 7}


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
    _, start_ms, menu_ms, _ = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 4900


def test_main_writes_schema_json_and_exit_zero(tmp_path):
    game = tmp_path / "starsector.log"
    game.write_text(
        _line(100, "com.genir.renderer.agent.Agent", "Fast Rendering: v0.9.7rc2")
        + _line(7000, "com.genir.renderer.overrides.loading.FileLoaderFast",
                "Cached 229754 files in 4146ms")
        + _line(61000, "sound.H", "Playing music with id [miscallenous_main_menu.ogg]"),
        encoding="utf-8")
    agent = tmp_path / "scripts-agent.log"
    agent.write_text(
        "2026-10-31T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-10-31T00:00:01Z INFO timeline: initFileLoaders.start rel_ms=100 epoch_ms=1000\n"
        "2026-10-31T00:00:05Z INFO timeline: initFileLoaders.end rel_ms=5000 epoch_ms=5900\n"
        "2026-10-31T00:00:06Z INFO scripts cache preloaded: key=k, entries=2113, bytes=1, in 7 ms\n",
        encoding="utf-8")
    out = tmp_path / "phase.json"

    rc = main(["--log", str(game), "--agent-log", str(agent), "--json-out", str(out)])

    assert rc == 0
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {
        "session_start_ms", "menu_ms", "crawl", "timeline", "phases_ms", "preload"}
    assert data["session_start_ms"] == 100
    assert data["menu_ms"] == 60900
    assert data["crawl"] == {"files": 229754, "ms": 4146}
    assert data["timeline"]["initFileLoaders.start"] == {"rel_ms": 100, "epoch_ms": 1000}
    assert data["phases_ms"]["initFileLoaders"] == 4900
    assert data["preload"] == {"entries": 2113, "ms": 7}
    assert isinstance(data["session_start_ms"], int)
    assert isinstance(data["menu_ms"], int)
    assert isinstance(data["crawl"], dict)
    assert isinstance(data["timeline"], dict)
    assert isinstance(data["phases_ms"], dict)
    assert isinstance(data["preload"], dict)


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
    _, start_ms, menu_ms, _ = parse_session(text)
    assert start_ms == 100
    assert menu_ms == 8000
