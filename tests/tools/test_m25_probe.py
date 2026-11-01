from m25_probe import parse_agent_log


def test_last_session_wins_and_counts_are_parsed():
    text = """2026-11-01T00:00:00Z INFO hypernova agent premain; config=old
2026-11-01T00:00:01Z INFO lazy probe: summary queue=1 wouldSkip=0 lookups=0 demand=0 index=1 types={}
2026-11-01T00:01:00Z INFO hypernova agent premain; config=new
2026-11-01T00:01:01Z INFO lazy probe: index loaded paths=2 invalid=0 in 3 ms; file=x
2026-11-01T00:01:02Z INFO lazy probe: queue lambda hook added to com/fs/graphics/TextureLoader
2026-11-01T00:01:02Z INFO lazy probe: repository lookup hook added to com/fs/graphics/oOoO
2026-11-01T00:01:10Z INFO lazy probe: lambda wired (first queue: type=, path=graphics/a.png)
2026-11-01T00:01:20Z INFO lazy probe: summary queue=10 wouldSkip=7 lookups=4 demand=2 index=2 types={=10}
"""
    result = parse_agent_log(text)
    assert result["summary"] == {"queue": 10, "would_skip": 7, "lookups": 4, "demand": 2, "index": "2"}
    assert result["index_paths"] == 2
    assert result["queue_hook"] is True
    assert result["lookup_hook"] is True
    assert result["wired"] is True
    assert abs(result["skip_fraction"] - 0.7) < 1e-9


def test_no_premain_is_empty_and_not_ok():
    result = parse_agent_log("nothing here\n")
    assert result["wired"] is False
    assert result["summary"] is None
    assert result["skip_fraction"] == 0.0
