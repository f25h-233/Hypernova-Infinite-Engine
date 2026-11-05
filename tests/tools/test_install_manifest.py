import hashlib
import json
from pathlib import Path

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
    header = [line for line in lines if line.startswith("#")]
    assert len(header) == 1, "skip file must carry exactly one generation header"
    digest = hashlib.sha256(result.out.read_bytes()).hexdigest()
    assert header[0] == f"# generation={digest}"
    records = [line for line in lines if line and not line.startswith("#")]
    # m9：锁住 skip 真的非空，避免 build_skip 回归为 [] 时下面的断言全部空转。
    assert result.skip_count > 0
    assert len(records) == result.skip_count
    assert all(len(line.split("\t")) == 3 for line in records)
    # L1 path must not be in the skip file
    l1 = {e["path"] for e in result.runtime["layers"]["L1"]}
    assert all(line.split("\t")[0] not in l1 for line in records)


def test_install_writes_lazy_skip_v2(mini_game):
    _seed_core(mini_game)
    result = install(mini_game)
    assert result.skip_v2_file == result.out.parent / "lazy-skip-v2.txt"
    assert result.skip_v2_file.is_file()
    lines = result.skip_v2_file.read_text(encoding="utf-8").splitlines()
    header = [line for line in lines if line.startswith("#")]
    assert header == [f"# generation={hashlib.sha256(result.out.read_bytes()).hexdigest()}"]
    records = [line for line in lines if line and not line.startswith("#")]
    assert result.skip_v2_count > 0
    assert len(records) == result.skip_v2_count
    assert all(len(line.split("\t")) == 6 for line in records)
    v1 = [line.split("\t")[0] for line in
          result.skip_file.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    v2 = [line.split("\t")[0] for line in records]
    assert v1 == v2


def test_install_skip_replace_failure_deletes_old_skip(mini_game, monkeypatch):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    first = install(mini_game, out=out)
    skip_target = first.skip_file
    assert skip_target.is_file()

    new_runtime = {
        "schema": "hypernova-runtime-1",
        "layers": {"L1": [], "L2": [], "L3": []},
    }
    monkeypatch.setattr(install_module, "trim", lambda manifest: new_runtime)
    real_replace = install_module.os.replace

    def flaky_replace(src, dst):
        if Path(dst) == skip_target:
            raise OSError("simulated skip replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(install_module.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="simulated skip replace failure"):
        install(mini_game, out=out)
    # manifest 已换新；旧 skip 被删除，运行期走“skip 缺失 → lazy disabled”，
    # 绝不留下新 manifest + 旧 skip 的跨代 pair。
    assert json.loads(out.read_text(encoding="utf-8")) == new_runtime
    assert not skip_target.exists()
    assert not (skip_target.parent / "lazy-skip-v2.txt").exists()
    assert not out.with_name(out.name + ".tmp").exists()
    assert not skip_target.with_name(skip_target.name + ".tmp").exists()


def test_install_skip_write_failure_keeps_old_pair(mini_game, monkeypatch):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    first = install(mini_game, out=out)
    old_manifest = out.read_bytes()
    old_skip = first.skip_file.read_bytes()

    new_runtime = {
        "schema": "hypernova-runtime-1",
        "layers": {"L1": [], "L2": [], "L3": []},
    }

    def boom(*args, **kwargs):
        raise OSError("simulated skip write failure")

    monkeypatch.setattr(install_module, "trim", lambda manifest: new_runtime)
    monkeypatch.setattr(install_module, "write_skip", boom)
    with pytest.raises(OSError, match="simulated skip write failure"):
        install(mini_game, out=out)
    # skip 写入失败发生在任何 replace 之前：旧 manifest 与旧 skip 都保持不变。
    assert out.read_bytes() == old_manifest
    assert first.skip_file.read_bytes() == old_skip
    assert not out.with_name(out.name + ".tmp").exists()
    assert not first.skip_file.with_name(first.skip_file.name + ".tmp").exists()


def test_install_skip_v2_write_failure_keeps_old_pair(mini_game, monkeypatch):
    _seed_core(mini_game)
    out = mini_game / "runtime.json"
    first = install(mini_game, out=out)
    old_manifest = out.read_bytes()
    old_v1 = first.skip_file.read_bytes()
    old_v2 = first.skip_v2_file.read_bytes()

    def boom(*args, **kwargs):
        raise OSError("simulated v2 write failure")

    monkeypatch.setattr(install_module, "write_skip_v2", boom)
    with pytest.raises(OSError, match="simulated v2 write failure"):
        install(mini_game, out=out)
    assert out.read_bytes() == old_manifest
    assert first.skip_file.read_bytes() == old_v1
    assert first.skip_v2_file.read_bytes() == old_v2
    assert not out.with_name(out.name + ".tmp").exists()
    assert not first.skip_file.with_name(first.skip_file.name + ".tmp").exists()
    assert not first.skip_v2_file.with_name(first.skip_v2_file.name + ".tmp").exists()


def test_install_writes_with_stale_cache_entry(mini_game):
    """线上复现：一条失效 DDSCache 记录不能让玩家拿不到整份清单。"""
    import json as _json
    _seed_core(mini_game)
    cache = mini_game / "mods" / "DDSCache" / "stale_cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "dds_metadata.json").write_text(
        _json.dumps([{
            "ModID": "mod_a",
            "ModFolderName": "mod_a",
            "RelativeImagePath": "graphics\\missing.png",
            "DDSFilePath": "\\mods\\DDSCache\\mod_a\\graphics\\missing.dds",
            "Width": 1,
            "Height": 1,
        }]),
        encoding="utf-8",
    )
    out = mini_game / "runtime.json"
    result = install(mini_game, out=out)
    assert out.is_file(), "stale DDSCache entry must not block manifest writing"
    assert not any(f.severity == "Critical" for f in result.findings)
    assert result.full["stats"]["stale_metadata_count"] >= 1
    assert any("stale" in w.lower() for w in result.warnings)
    skip = result.skip_v2_file.read_text(encoding="utf-8")
    assert "graphics/missing.png" not in skip


def test_critical_install_does_not_write_skip_file(mini_game):
    _seed_core(mini_game)
    result = install(mini_game, max_l1=1)
    assert any(f.severity == "Critical" for f in result.findings)
    assert result.skip_file is None
    assert result.skip_count == 0
    assert result.skip_v2_file is None
    assert result.skip_v2_count == 0


def test_install_without_enabled_list_falls_back_and_warns(tmp_path):
    """玩家没有 mods/enabled_mods.json 时不能崩：按全目录生成并给出提示。"""
    from test_manifest_builder import _png

    game = tmp_path / "game"
    _seed_core(game)
    mod = game / "mods" / "mod_a"
    (mod / "graphics").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id": "mod_a"}', encoding="utf-8")
    (mod / "graphics" / "ship.png").write_bytes(_png(2, 2))

    result = install(game)
    assert result.out.is_file()
    assert any("enabled_mods.json" in w for w in result.warnings)
