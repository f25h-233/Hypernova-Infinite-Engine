import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
_spec = importlib.util.spec_from_file_location("m25_ab", TOOLS / "m25_ab.py")
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)


def test_lazy_stats_parses_summary():
    text = ("2026-11-01T00:00:00Z INFO hypernova agent premain\n"
            "2026-11-01T00:01:00Z INFO lazy probe: summary queue=52604 wouldSkip=45785 "
            "lookups=1 demand=1 index=73446 types={} queuedSkip=45785 demandQueued=1 hits=1 "
            "misses=0 degraded=0 skipped=45785 proxies=45785 materialized=7325 deferred=0 "
            "failed=0 disabled=0 main=Thread-3 loading=Thread-7-FR-Main-Loader\n")
    s = ab.lazy_stats_from_text(text)
    assert s["skipped"] == 45785
    assert s["materialized"] == 7325
    assert s["failed"] == 0


def test_lazy_stats_parses_current_summary_with_pending_and_drained():
    # Task 2 F1 added pending/drained between deferred and failed; the parser
    # must tolerate the new fields (the brief's regex did not).
    text = ("2026-11-01T07:39:11Z INFO hypernova agent premain\n"
            "2026-11-01T07:40:21Z INFO lazy probe: summary queue=52604 wouldSkip=45785 "
            "lookups=60863 demand=17243 index=73446 "
            "types={TEXTURE_ALPHA_ADDER=1,TEXTURE=52603} queuedSkip=45785 "
            "demandQueued=3208 hits=3208 misses=0 degraded=0 skipped=45784 "
            "proxies=45784 materialized=81 deferred=0 pending=0 drained=45784 "
            "failed=0 disabled=0 main=main loading=Thread-4-FR-Main-Loader\n")
    s = ab.lazy_stats_from_text(text)
    assert s == {"skipped": 45784, "proxies": 45784, "materialized": 81,
                 "deferred": 0, "failed": 0, "disabled": 0}


def test_lazy_stats_only_uses_the_last_session():
    text = ("2026-11-01T00:00:00Z INFO hypernova agent premain\n"
            "2026-11-01T00:00:10Z INFO lazy probe: summary queue=1 skipped=111 "
            "proxies=111 materialized=11 deferred=0 failed=0 disabled=0 main=main "
            "loading=none\n"
            "2026-11-01T01:00:00Z INFO hypernova agent premain\n"
            "2026-11-01T01:00:10Z INFO lazy probe: summary queue=2 skipped=222 "
            "proxies=222 materialized=22 deferred=0 failed=0 disabled=0 main=main "
            "loading=none\n")
    assert ab.lazy_stats_from_text(text)["skipped"] == 222


def test_lazy_stats_empty_without_summary():
    assert ab.lazy_stats_from_text(
        "2026-11-01T00:00:00Z INFO hypernova agent premain\nno lazy here\n") == {}


def test_median_handles_odd_even_and_empty():
    assert ab.median([3, 1, 2]) == 2
    assert ab.median([10, 2, 4, 6]) == 5
    assert ab.median([]) is None


def _fake_log(tmp_path, monkeypatch, data: bytes) -> Path:
    game = tmp_path / "game"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    log = core / "starsector.log"
    log.write_bytes(data)
    monkeypatch.setattr(ab, "ROOT", tmp_path)
    monkeypatch.setattr(ab, "PROFILES", {"fake": {"game": "game"}})
    return log


def test_archive_round_ignores_errors_from_earlier_sessions(tmp_path, monkeypatch):
    _fake_log(tmp_path, monkeypatch,
              b"Fast Rendering: v0.9.7rc2\nFailed to load texture old\n"
              b"Fast Rendering: v0.9.7rc2\nall clean\n")
    out = tmp_path / "out"
    row = ab.archive_round("fake", "c", 1, out)
    assert row["log"] == str(out / "ab-c1.log")
    assert (out / "ab-c1.log").is_file()
    assert row == {"log": str(out / "ab-c1.log"),
                   "failed": 0, "verify": 0, "class_errors": 0}


def test_archive_round_counts_last_session_errors(tmp_path, monkeypatch):
    _fake_log(tmp_path, monkeypatch,
              b"Fast Rendering: v0.9.7rc2\nok\n"
              b"Fast Rendering: v0.9.7rc2\n"
              b"Failed to load texture graphics/x.png\n"
              b"java.lang.VerifyError: bad\n"
              b"java.lang.ClassFormatError: bad\n")
    row = ab.archive_round("fake", "t", 2, tmp_path / "out")
    assert row["failed"] == 1
    assert row["verify"] == 1
    assert row["class_errors"] == 1
