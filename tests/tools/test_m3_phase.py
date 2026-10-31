import sys
from pathlib import Path

# pytest under `python -I` does not put the repo root on sys.path; tools/ is not
# a package and tests/conftest.py only inserts tools/ itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.m3_phase import _read, parse_session, parse_agent, phases


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
