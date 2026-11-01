import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("smoke_check", REPO / "tools" / "java" / "smoke-check.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

HEAD_BEAT = ("HYPERNOVA_TICK 3001 SchedulerStats[queued=12, loaded=10, failed=0, "
             "ticks=3001, nanosLastTick=194000, backlog=2]")
OLD_BEAT = ("HYPERNOVA_TICK 1 backlog=0 stats=SchedulerStats[queued=0, loaded=0, failed=0, "
            "ticks=195, nanosLastTick=2800, backlog=0]")


def test_head_heartbeat_parses():
    beats = smoke.parse_heartbeats([HEAD_BEAT])
    assert len(beats) == 1
    assert beats[0] == {"tick": 3001, "queued": 12, "loaded": 10, "failed": 0,
                        "ticks": 3001, "nanos": 194000, "backlog": 2}


def test_legacy_heartbeat_is_detected():
    assert smoke.parse_heartbeats([OLD_BEAT]) == []
    assert smoke.old_format_heartbeats([OLD_BEAT]) == [OLD_BEAT]
    assert smoke.old_format_heartbeats([HEAD_BEAT]) == []


def test_percentile_nearest_rank():
    assert smoke.percentile([], 99) is None
    assert smoke.percentile([5], 99) == 5
    values = list(range(1, 101))  # 1..100
    assert smoke.percentile(values, 50) == 50
    assert smoke.percentile(values, 99) == 99
    assert smoke.percentile([3, 1, 2], 99) == 3


def _zip_bytes(member: str, data: bytes) -> bytes:
    """Real zip bytes: jar_provenance hashes entry name+CRC+size, not raw bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, data)
    return buf.getvalue()


def test_jar_provenance_detects_mismatch(tmp_path):
    installed = tmp_path / "installed.jar"
    build = tmp_path / "build.jar"
    installed.write_bytes(_zip_bytes("hypernova/Plugin.class", b"old"))
    build.write_bytes(_zip_bytes("hypernova/Plugin.class", b"new"))
    ok, detail = smoke.jar_provenance(installed, build)
    assert not ok and "sha=" in detail
    build.write_bytes(installed.read_bytes())
    ok, detail = smoke.jar_provenance(installed, build)
    assert ok and "1 entries sha=" in detail


def test_jar_provenance_missing_build_output(tmp_path):
    installed = tmp_path / "installed.jar"
    installed.write_bytes(b"x")
    ok, _ = smoke.jar_provenance(installed, tmp_path / "nope.jar")
    assert not ok


def _make_game(tmp_path: Path, *, log: str, telemetry: list[dict], probe_paths: int = 0,
               installed_jar: bytes = b"jar") -> Path:
    game = tmp_path / "game"
    mod = game / "mods" / "hypernova_infinite_engine"
    (mod / "data/config/hypernova").mkdir(parents=True)
    (mod / "jars").mkdir(parents=True)
    (game / "mods/enabled_mods.json").write_text(
        json.dumps({"enabledMods": ["hypernova_infinite_engine"]}), encoding="utf-8")
    (mod / "data/config/hypernova/manifest-v1.json").write_text("{}", encoding="utf-8")
    (mod / "jars/hypernova.jar").write_bytes(installed_jar)
    (mod / "data/config/hypernova/hypernova.json").write_text(
        json.dumps({"startup_probe_paths": probe_paths}), encoding="utf-8")
    core = game / "starsector-core"
    core.mkdir()
    (core / "starsector.log").write_text(smoke.BANNER + "\n" + log, encoding="utf-8")
    tl = game / "saves/common/hypernova/telemetry.jsonl.data"
    tl.parent.mkdir(parents=True)
    tl.write_text("\n".join(json.dumps(r) for r in telemetry) + "\n", encoding="utf-8")
    return game


GOOD_LOG = "\n".join([
    "Hypernova active: ok, manifest=3305 paths",
    "attachCampaign: done, transientScript=true",
    HEAD_BEAT,
])


def _rows(n_loaded=50, nanos=100_000):
    return [{"t": 1, "kind": "loaded", "path": f"p{i}.png", "nanos": nanos,
             "thread": "main", "detail": "core"} for i in range(n_loaded)]


def test_end_to_end_pass(tmp_path, capsys):
    game = _make_game(tmp_path, log=GOOD_LOG, telemetry=_rows())
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "loaded p99 <= 2 ms" in out
    assert "heartbeat format is HEAD" in out


def test_legacy_heartbeat_fails(tmp_path, capsys):
    game = _make_game(tmp_path, log="Hypernova active: ok\nattachCampaign: done\n" + OLD_BEAT,
                      telemetry=_rows())
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  heartbeat format is HEAD" in out


def test_probe_enabled_requires_selfcheck_pass(tmp_path, capsys):
    game = _make_game(tmp_path, log=GOOD_LOG, telemetry=_rows(), probe_paths=8)
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 1
    assert "FAIL  selfcheck RESULT PASS" in capsys.readouterr().out

    game2 = _make_game(tmp_path / "b", log=GOOD_LOG + "\nselfcheck: RESULT 8/8 PASS",
                       telemetry=_rows(), probe_paths=8)
    assert smoke.main(["--game", str(game2), "--skip-provenance"]) == 0


def test_probe_disabled_skips_selfcheck(tmp_path, capsys):
    game = _make_game(tmp_path, log=GOOD_LOG, telemetry=_rows(), probe_paths=0)
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 0
    assert "SKIP  selfcheck RESULT PASS" in capsys.readouterr().out


def test_loaded_p99_over_budget_fails(tmp_path, capsys):
    game = _make_game(tmp_path, log=GOOD_LOG,
                      telemetry=_rows(n_loaded=100, nanos=3_000_000))
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 1
    assert "FAIL  loaded p99 <= 2 ms" in capsys.readouterr().out


def test_provenance_mismatch_fails_without_skip(tmp_path, capsys):
    game = _make_game(tmp_path, log=GOOD_LOG, telemetry=_rows(),
                      installed_jar=_zip_bytes("hypernova/Plugin.class",
                                               b"definitely-not-build"))
    assert smoke.main(["--game", str(game)]) == 1
    assert "FAIL  installed jar matches build output" in capsys.readouterr().out


def test_missing_thread_field_fails(tmp_path, capsys):
    rows = _rows()
    for r in rows:
        r.pop("thread")
    game = _make_game(tmp_path, log=GOOD_LOG, telemetry=rows)
    assert smoke.main(["--game", str(game), "--skip-provenance"]) == 1
    assert "FAIL  telemetry has thread field" in capsys.readouterr().out
