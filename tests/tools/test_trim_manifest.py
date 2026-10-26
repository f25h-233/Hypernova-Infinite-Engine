import json

from trim_manifest import trim


def _entry(path="graphics/ships/a.png", **extra):
    e = {"path": path, "modId": "mod_a", "w": 64, "h": 32, "baked": True,
         "absolutePath": "/game/mods/mod_a/" + path, "ddsPath": "x.dds", "src": "hull"}
    e.update(extra)
    return e


def test_trim_drops_runtime_unneeded_fields():
    out = trim({"layers": {"L1": [_entry()], "L2": [], "L3": []}})
    assert out["schema"] == "hypernova-runtime-1"
    e = out["layers"]["L1"][0]
    assert e == {"path": "graphics/ships/a.png", "modId": "mod_a", "w": 64, "h": 32, "baked": True}
    assert "absolutePath" not in e and "ddsPath" not in e and "src" not in e


def test_trim_keeps_all_three_layers_even_when_source_omits_them():
    out = trim({"layers": {"L1": [_entry()]}})
    assert set(out["layers"]) == {"L1", "L2", "L3"}
    assert out["layers"]["L2"] == []
    assert out["layers"]["L3"] == []


def test_trim_drops_entries_without_path():
    out = trim({"layers": {"L1": [_entry(), {"modId": "m"}, _entry("b.png")]}})
    assert [e["path"] for e in out["layers"]["L1"]] == ["graphics/ships/a.png", "b.png"]


def test_trim_applies_defaults():
    out = trim({"layers": {"L3": [{"path": "p.png", "modId": "m"}]}})
    e = out["layers"]["L3"][0]
    assert e["w"] == 0 and e["h"] == 0 and e["baked"] is False


def test_trim_output_is_parseable_and_single_line_json(tmp_path):
    # install-manifest.sh 用同一份逻辑；这里锁住 CLI 行为（源缺失必须非零退出）。
    from trim_manifest import main

    src = tmp_path / "big.json"
    src.write_text(json.dumps({"layers": {"L1": [_entry()]}}), encoding="utf-8")
    out = tmp_path / "dist" / "manifest-v1.json"
    assert main(["--src", str(src), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["layers"]["L1"]) == 1


def test_trim_missing_source_fails(tmp_path):
    from trim_manifest import main

    assert main(["--src", str(tmp_path / "nope.json"), "--out", str(tmp_path / "o.json")]) == 1
    assert not (tmp_path / "o.json").exists()
