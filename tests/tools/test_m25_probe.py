import json

from m25_probe import main, parse_agent_log

SESSION = """2026-11-01T00:01:00Z INFO hypernova agent premain; config=new
2026-11-01T00:01:01Z INFO lazy probe: index loaded paths=2 invalid=0 in 3 ms; file=x
2026-11-01T00:01:02Z INFO lazy probe: queue lambda hook added to com/fs/graphics/TextureLoader
2026-11-01T00:01:02Z INFO lazy probe: repository lookup hook added to com/fs/graphics/oOoO
2026-11-01T00:01:10Z INFO lazy probe: lambda wired (first queue: type=, path=graphics/a.png)
2026-11-01T00:01:20Z INFO lazy probe: summary queue=10 wouldSkip=7 lookups=4 demand=2 index=2 types={=10} queuedSkip=6 demandQueued=5 hits=3 misses=2 degraded=0
"""


def test_last_session_wins_and_counts_are_parsed():
    text = """2026-11-01T00:00:00Z INFO hypernova agent premain; config=old
2026-11-01T00:00:01Z INFO lazy probe: summary queue=1 wouldSkip=0 lookups=0 demand=0 index=1 types={}
""" + SESSION
    result = parse_agent_log(text)
    assert result["summary"] == {"queue": 10, "would_skip": 7, "lookups": 4, "demand": 2, "index": "2"}
    assert result["index_paths"] == 2
    assert result["queue_hook"] is True
    assert result["lookup_hook"] is True
    assert result["wired"] is True
    assert abs(result["skip_fraction"] - 0.7) < 1e-9
    assert result["operational"] == {
        "queued_skip": 6, "demand_queued": 5, "hits": 3, "misses": 2, "degraded": 0}
    assert abs(result["operational_fraction"] - 5 / 7) < 1e-9
    assert result["agent_errors"] == 0
    assert result["premain_ts"] == "2026-11-01T00:01:00Z"
    assert result["summary_series"] == [{
        "ts": "2026-11-01T00:01:20Z",
        "queue": 10, "would_skip": 7, "lookups": 4, "demand": 2, "index": "2",
        "queued_skip": 6, "demand_queued": 5, "hits": 3, "misses": 2, "degraded": 0,
    }]


def test_no_premain_is_empty_and_not_ok():
    result = parse_agent_log("nothing here\n")
    assert result["wired"] is False
    assert result["summary"] is None
    assert result["skip_fraction"] == 0.0
    assert result["operational_fraction"] == 0.0
    assert result["agent_errors"] == 0


def test_main_ok_requires_zero_errors_index_and_no_degradation(tmp_path):
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps([{"menu_s": 10.0}]), encoding="utf-8")

    good = tmp_path / "good.log"
    good.write_text(SESSION, encoding="utf-8")
    assert main(["--agent-log", str(good), "--smoke-json", str(smoke)]) == 0

    degraded = tmp_path / "degraded.log"
    degraded.write_text(SESSION.replace("degraded=0", "degraded=1"), encoding="utf-8")
    assert main(["--agent-log", str(degraded), "--smoke-json", str(smoke)]) == 1

    errored = tmp_path / "errored.log"
    errored.write_text(SESSION + "2026-11-01T00:01:21Z ERROR lazy probe: boom\n",
                       encoding="utf-8")
    assert main(["--agent-log", str(errored), "--smoke-json", str(smoke)]) == 1

    noindex = tmp_path / "noindex.log"
    noindex.write_text(SESSION.replace("paths=2", "paths=0"), encoding="utf-8")
    assert main(["--agent-log", str(noindex), "--smoke-json", str(smoke)]) == 1
