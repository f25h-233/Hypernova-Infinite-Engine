import json
import sys
from pathlib import Path

import pytest

# pytest under `python -I` does not put the repo root on sys.path; tools/ is not
# a package and tests/conftest.py only inserts tools/ itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.m3_ab import load_menu_s, summarize


def _write(path, values):
    path.write_text(json.dumps([
        {"ok": True, "menu_s": v} for v in values
    ]), encoding="utf-8")


def test_median_and_delta(tmp_path):
    c = tmp_path / "c.json"
    t = tmp_path / "t.json"
    _write(c, [60.0, 61.0, 62.0])
    _write(t, [55.0, 56.0, 57.0])
    s = summarize(c, t)
    assert s["control_median_s"] == 61.0
    assert s["treatment_median_s"] == 56.0
    assert s["delta_s"] == 5.0
    assert s["delta_pct"] == pytest.approx(8.2, abs=0.1)


def test_rejects_no_ok_round(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([{"ok": False, "reason": "menu-timeout"}]))
    with pytest.raises(SystemExit):
        load_menu_s(p)
