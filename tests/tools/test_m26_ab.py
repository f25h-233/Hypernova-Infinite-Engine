import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
_spec = importlib.util.spec_from_file_location("m26_ab", TOOLS / "m26_ab.py")
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)


def test_stats_parses_extended_summary():
    text = ("2026-11-01T00:00:00Z INFO hypernova agent premain\n"
            "2026-11-01T00:01:00Z INFO lazy probe: summary queue=52604 "
            "wouldSkip=45785 skipped=45784 proxies=45784 materialized=87 "
            "deferred=0 pending=0 drained=45784 reregistered=1 failed=0 "
            "disabled=0 main=main loading=Thread-4-FR-Main-Loader "
            "lateRegistered=0 lateLoaded=0 dimMismatch=0 dds=1 ddsHit=86 "
            "ddsFallback=1 ddsDisabled=0 ddsDimMismatch=0 eviction=1 "
            "evicted=3 evictedBytes=1024 rematerialized=2 evictPasses=1 "
            "liveBytes=100 placeholder=99 oldIdDeleted=0 evictSkipped=0 selftest=1\n")
    s = ab.stats_from_text(text)
    assert s["skipped"] == 45784
    assert s["ddsHit"] == 86
    assert s["ddsDisabled"] == 0
    assert s["evicted"] == 3
    assert s["selftest"] == 1
    assert s["loading"] == "Thread-4-FR-Main-Loader"


def test_stats_only_uses_last_session():
    text = ("premain\nlazy probe: summary skipped=111 failed=0 disabled=0\n"
            "premain\nlazy probe: summary skipped=222 failed=0 disabled=0\n")
    assert ab.stats_from_text(text)["skipped"] == 222


def test_flags_control_and_treatment():
    assert ab._flags(False, True, False, False) == [
        "-Dhypernova.textures.lazy=false"]
    flags = ab._flags(True, True, True, True)
    assert "-Dhypernova.textures.lazy=true" in flags
    assert "-Dhypernova.textures.lazy.dds=true" in flags
    assert "-Dhypernova.textures.lazy.eviction=true" in flags
    assert "-Dhypernova.textures.lazy.selftest=true" in flags
    no_dds = ab._flags(True, False, False, False)
    assert "-Dhypernova.textures.lazy.dds=false" in no_dds


def test_median():
    assert ab.median([3, 1, 2]) == 2
    assert ab.median([10, 2, 4, 6]) == 5
    assert ab.median([]) is None


def test_archive_round_slices_last_session(tmp_path, monkeypatch):
    game = tmp_path / "game"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    log = core / "starsector.log"
    log.write_bytes(b"Fast Rendering: v0.9.7rc2\nold failed texture\n"
                    b"Fast Rendering: v0.9.7rc2\nclean session\n")
    monkeypatch.setattr(ab, "ROOT", tmp_path)
    monkeypatch.setattr(ab, "PROFILES", {"fake": {"game": "game"}})
    row = ab.archive_round("fake", "c", 1, tmp_path / "out")
    data = Path(row["log"]).read_bytes()
    assert b"old failed texture" not in data
    assert b"clean session" in data
    assert row["failed"] == 0


def _row(menu_s, ok=True):
    return {"menu_s": menu_s, "ok": ok, "failed": 0, "verify": 0,
            "class_errors": 0, "async_errors": 0, "corrupted": 0}


def test_main_pairs_and_gates(tmp_path, monkeypatch):
    calls = []

    def fake_run(profile, lazy, dds, eviction, selftest, out, wait, linger):
        calls.append((lazy, dds, eviction, selftest))
        return _row(50.0 if not lazy else 51.0)

    monkeypatch.setattr(ab, "run_round", fake_run)
    monkeypatch.setattr(ab, "archive_round", lambda *a, **k: {
        "log": None, "failed": 0, "verify": 0, "class_errors": 0,
        "async_errors": 0, "corrupted": 0})
    monkeypatch.setattr(ab, "stats_from_text", lambda text: {
        "skipped": 45784, "failed": 0, "disabled": 0, "dimMismatch": 0,
        "ddsDisabled": 0, "ddsHit": 80, "selftest": 1})
    monkeypatch.setattr(ab, "free_physical_mb", lambda: 20_000.0)
    agent = tmp_path / "agent.log"
    agent.write_text("premain\n", encoding="utf-8")
    out = tmp_path / "ab.json"
    assert ab.main(["--rounds", "2", "--agent-log", str(agent),
                    "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["control_median"] == 50.0
    assert result["treatment_median"] == 51.0
    assert result["paired_deltas_s"] == [1.0, 1.0]
    assert result["paired_median_s"] == 1.0
    assert result["gates"]["treatment_dds_hit_positive"] is True
    assert calls == [(False, False, False, False), (True, True, False, False),
                     (False, False, False, False), (True, True, False, False)]
