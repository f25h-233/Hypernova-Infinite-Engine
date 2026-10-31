import json

from install_manifest import DEFAULT_REL, install
from test_manifest_builder import _seed_core


def test_install_writes_runtime_manifest(mini_game):
    _seed_core(mini_game)
    result = install(mini_game)
    assert result.out == mini_game / DEFAULT_REL
    assert result.out.is_file()
    data = json.loads(result.out.read_text(encoding="utf-8"))
    assert data["schema"] == "hypernova-runtime-1"
    assert len(data["layers"]["L1"]) == len(result.full["layers"]["L1"])
    assert not any(f.severity == "Critical" for f in result.findings)


def test_install_refuses_to_write_when_critical(mini_game):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    result = install(mini_game, out=out, max_l1=1)
    assert any(f.severity == "Critical" for f in result.findings)
    assert not out.exists()


def test_install_is_idempotent(mini_game):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    install(mini_game, out=out)
    first = out.read_bytes()
    install(mini_game, out=out)
    assert out.read_bytes() == first


def test_install_applies_tiers(mini_game):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    result = install(mini_game, out=out, tiers={"mod_a": "L3"})
    assert all(e["modId"] != "mod_a" for e in result.full["layers"]["L1"])
    runtime = json.loads(out.read_text(encoding="utf-8"))
    assert all(e["modId"] != "mod_a" for e in runtime["layers"]["L1"])
    assert any(e["modId"] == "mod_a" for e in runtime["layers"]["L3"])


def test_install_rejects_invalid_tier(mini_game):
    import pytest
    _seed_core(mini_game)
    with pytest.raises(ValueError):
        install(mini_game, out=mini_game / "runtime.json", tiers={"mod_a": "L9"})
