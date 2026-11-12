"""Probe cache and parallel probing: player-side manifest generation speed."""
import json
import os
from pathlib import Path

import manifest_builder as mb
from manifest_builder import build_manifest
from install_manifest import install
from test_manifest_builder import _seed_core
from conftest import _png


def _build(mini_game, cache: Path | None = None, workers: int = 1):
    return build_manifest(
        mini_game, probe_cache=cache, probe_workers=workers
    ).manifest


def _entry(manifest: dict, path: str) -> dict:
    for layer in ("L1", "L2", "L3"):
        for entry in manifest["layers"][layer]:
            if entry["path"] == path:
                return entry
    raise AssertionError(f"{path} not found in manifest")


def test_second_build_reuses_probe_cache(mini_game, monkeypatch):
    cache = mini_game / "probe-cache.json"
    first = _build(mini_game, cache)
    assert first["stats"]["probe"]["probes"] > 0, "fixture must contain unbaked images"
    assert cache.is_file()

    def boom(path):
        raise AssertionError(f"probe() called despite warm cache: {path}")

    monkeypatch.setattr(mb, "probe", boom)
    second = _build(mini_game, cache)
    assert second["layers"] == first["layers"]
    assert second["stats"]["probe"]["cache_hits"] == first["stats"]["probe"]["candidates"]
    assert second["stats"]["probe"]["probes"] == 0


def test_probe_cache_invalidates_when_image_changes(mini_game):
    cache = mini_game / "probe-cache.json"
    _build(mini_game, cache)
    p = mini_game / "mods" / "mod_a" / "graphics" / "unlisted.png"
    p.write_bytes(_png(11, 13))
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    m = _build(mini_game, cache)
    entry = _entry(m, "graphics/unlisted.png")
    assert (entry["w"], entry["h"]) == (11, 13)
    assert m["stats"]["probe"]["probes"] >= 1


def test_corrupt_probe_cache_is_ignored(mini_game):
    cache = mini_game / "probe-cache.json"
    cache.write_text("{not json", encoding="utf-8")
    m = _build(mini_game, cache)
    entry = _entry(m, "graphics/unlisted.png")
    assert (entry["w"], entry["h"]) == (3, 3)
    json.loads(cache.read_text(encoding="utf-8"))
    assert m["stats"]["probe"]["probes"] > 0


def test_probe_cache_is_pruned_to_current_images(mini_game):
    cache = mini_game / "probe-cache.json"
    _build(mini_game, cache)
    p = mini_game / "mods" / "mod_a" / "graphics" / "unlisted.png"
    p.unlink()
    _build(mini_game, cache)
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert not any("unlisted.png" in key.casefold() for key in data["entries"])


def test_parallel_probe_matches_sequential(mini_game):
    sequential = _build(mini_game, workers=1)
    parallel = _build(mini_game, workers=8)
    assert parallel["layers"] == sequential["layers"]
    assert parallel["stats"]["probe"] == sequential["stats"]["probe"]


def test_probe_cache_write_failure_is_non_fatal(mini_game, monkeypatch):
    import probe_cache as probe_cache_module

    def boom(*args, **kwargs):
        raise RuntimeError("simulated cache write failure")

    monkeypatch.setattr(probe_cache_module.json, "dump", boom)
    m = _build(mini_game, mini_game / "probe-cache.json")
    assert m["layers"]["L1"]


def test_install_writes_probe_cache(mini_game, monkeypatch):
    _seed_core(mini_game)
    result = install(mini_game)
    assert result.probe_cache is not None
    assert result.probe_cache.is_file()
    assert result.full["stats"]["probe"]["probes"] > 0

    def boom(path):
        raise AssertionError(f"probe() called despite warm cache: {path}")

    monkeypatch.setattr(mb, "probe", boom)
    second = install(mini_game)
    assert second.full["stats"]["probe"]["probes"] == 0
    assert second.full["layers"] == result.full["layers"]
