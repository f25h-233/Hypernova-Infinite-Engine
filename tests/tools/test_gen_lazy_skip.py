import json

from gen_lazy_skip import build_skip, build_skip_v2, main, write_skip_v2


def test_build_skip_excludes_l1_invalid_blacklist_and_duplicates():
    manifest = {
        "schema": "hypernova-runtime-1",
        "layers": {
            "L1": [{"path": "graphics/l1.png", "w": 1, "h": 1}],
            "L2": [
                {"path": "graphics/l2.png", "w": 2, "h": 3},
                {"path": "graphics/l1.png", "w": 1, "h": 1},
                {"path": "graphics/l2.png", "w": 2, "h": 3},
            ],
            "L3": [
                {"path": "graphics/l3.png", "w": 4, "h": 5},
                {"path": "graphics/bad.png", "w": 0, "h": 5},
                {"path": "graphics/missing.png"},
                {"path": "graphics/ui/bottomright1.png", "w": 8, "h": 8},
            ],
        },
    }
    rows, stats = build_skip(manifest)
    assert rows == [("graphics/l2.png", 2, 3), ("graphics/l3.png", 4, 5)]
    assert stats["skip"] == 2
    assert stats["excluded_l1"] == 1
    assert stats["excluded_invalid"] == 2
    assert stats["excluded_blacklist"] == 1
    assert stats["excluded_duplicate"] == 1


def test_cli_writes_sorted_lines_and_json(tmp_path):
    manifest = tmp_path / "manifest-v1.json"
    manifest.write_text(json.dumps({
        "layers": {
            "L1": [{"path": "graphics/a.png", "w": 1, "h": 1}],
            "L2": [{"path": "graphics/z.png", "w": 9, "h": 8}],
            "L3": [{"path": "graphics/b.png", "w": 3, "h": 4}],
        }
    }), encoding="utf-8")
    out = tmp_path / "lazy-skip-v1.txt"
    json_out = tmp_path / "stats.json"
    assert main(["--manifest", str(manifest), "--out", str(out),
                 "--json-out", str(json_out)]) == 0
    assert out.read_text(encoding="utf-8") == "graphics/b.png\t3\t4\ngraphics/z.png\t9\t8\n"
    assert not (tmp_path / "lazy-skip-v1.txt.tmp").exists()
    stats = json.loads(json_out.read_text(encoding="utf-8"))["stats"]
    assert stats["skip"] == 2


def test_cli_missing_manifest_exits_2(tmp_path):
    assert main(["--manifest", str(tmp_path / "nope.json"),
                 "--out", str(tmp_path / "out.txt")]) == 2


def test_build_skip_v2_carries_abs_and_dds():
    manifest = {
        "layers": {
            "L1": [{"path": "graphics/l1.png"}],
            "L2": [
                {"path": "graphics/l2.png", "w": 2, "h": 3,
                 "absolutePath": "D:/m/l2.png", "ddsPath": "D:/d/l2.dds", "baked": True},
                {"path": "graphics/l1.png", "w": 1, "h": 1},
            ],
            "L3": [
                {"path": "graphics/l3.png", "w": 4, "h": 5,
                 "absolutePath": "D:/m/l3.png", "baked": False},
                {"path": "graphics/ui/bottomright1.png", "w": 8, "h": 8},
            ],
        },
    }
    rows, stats = build_skip_v2(manifest)
    assert rows == [
        ("graphics/l2.png", 2, 3, "D:/m/l2.png", "D:/d/l2.dds", True),
        ("graphics/l3.png", 4, 5, "D:/m/l3.png", "", False),
    ]
    assert stats["skip"] == 2
    assert stats["dds"] == 1
    assert stats["excluded_l1"] == 1
    assert stats["excluded_blacklist"] == 1


def test_write_skip_v2_header_and_columns(tmp_path):
    out = tmp_path / "lazy-skip-v2.txt"
    write_skip_v2(out, [("graphics/a.png", 2, 3, "D:/m/a.png", "D:/d/a.dds", True)],
                  header="# generation=abc")
    text = out.read_text(encoding="utf-8")
    assert text == ("# generation=abc\n"
                    "graphics/a.png\t2\t3\tD:/m/a.png\tD:/d/a.dds\t1\n")
