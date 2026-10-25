from coverage_report import render_report


def _manifest():
    return {
        "schema": 1,
        "layers": {
            "L1": [
                {"modId": "mod_a", "path": "graphics/a.png", "absolutePath": "/tmp/x",
                 "ddsPath": None, "w": 1, "h": 1, "baked": False, "src": "spec_scan"}
            ],
            "L2": [],
            "L3": [],
        },
        "stats": {
            "scope": "mod_non_shader",
            "include_core": True,
            "metadata_entries": 0,
            "core_entries": 0,
            "l1_count": 1,
            "l2_count": 0,
            "l3_count": 0,
            "coverage": {
                "l1_sprite_disk": 1.0,
                "closure_refs": 1.0,
                "metadata": None,
            },
            "missing": {"variant": ["v_missing"]},
            "parse_errors": {},
        },
    }


def test_report_contains_gate_and_missing(tmp_path):
    demand = [{"path": "graphics/a.png", "session": 1, "line": 1, "ms": 1, "thread": "main"}]
    text = render_report(_manifest(), demand, "fixture", tmp_path)
    assert "| L1 ≤ 8000 | PASS | 1 |" in text
    assert "| closure_refs ≥ 0.95 | PASS | 1.000 |" in text
    assert "v_missing" in text
    assert "graphics/a.png" in text


def test_report_fails_gate_when_coverage_low(tmp_path):
    m = _manifest()
    m["stats"]["coverage"]["closure_refs"] = 0.5
    text = render_report(m, [], "fixture", tmp_path)
    assert "| closure_refs ≥ 0.95 | FAIL | 0.500 |" in text
