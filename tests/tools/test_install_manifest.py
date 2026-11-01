import json

import pytest

import install_manifest as install_module
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


def test_install_failure_keeps_old_manifest_and_no_tmp(mini_game, monkeypatch):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    install(mini_game, out=out)
    before = out.read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated json.dump failure")

    monkeypatch.setattr(install_module.json, "dump", boom)
    with pytest.raises(RuntimeError):
        install(mini_game, out=out)
    assert out.read_bytes() == before
    assert not out.with_name(out.name + ".tmp").exists()


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


def test_install_writes_lazy_skip_file(mini_game):
    _seed_core(mini_game)
    result = install(mini_game)
    assert result.skip_file == result.out.parent / "lazy-skip-v1.txt"
    assert result.skip_file.is_file()
    lines = result.skip_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result.skip_count
    assert all(len(line.split("\t")) == 3 for line in lines)
    # L1 path must not be in the skip file
    l1 = {e["path"] for e in result.runtime["layers"]["L1"]}
    assert all(line.split("\t")[0] not in l1 for line in lines)


def test_critical_install_does_not_write_skip_file(mini_game):
    _seed_core(mini_game)
    result = install(mini_game, max_l1=1)
    assert any(f.severity == "Critical" for f in result.findings)
    assert result.skip_file is None
    assert result.skip_count == 0
