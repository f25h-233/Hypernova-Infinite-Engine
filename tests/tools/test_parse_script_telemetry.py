import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/java"))
import parse_script_telemetry as p


def test_no_summary_returns_empty(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"kind":"preload","entries":1}\n', encoding="utf-8")
    assert p.summaries(f) == []


def test_last_summary_wins(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"kind":"summary","hits":1}\n'
                 '{"kind":"summary","hits":2}\n', encoding="utf-8")
    assert p.summaries(f)[-1]["hits"] == 2


def test_malformed_lines_are_skipped(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('not json\n{"kind":"summary","hits":3}\n', encoding="utf-8")
    assert p.summaries(f)[-1]["hits"] == 3
