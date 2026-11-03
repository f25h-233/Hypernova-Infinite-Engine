import hashlib
import json
from pathlib import Path

import pytest

from m6_env_snapshot import SNAPSHOT_FILES, main, restore, snapshot


def _seed(root: Path) -> None:
    for rel in SNAPSHOT_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content:{rel}\n", encoding="utf-8")


def test_snapshot_copies_files_and_records_sha256(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    meta = snapshot(game, tmp_path / "backups", "baseline")
    snap = tmp_path / "backups" / "baseline"
    assert meta["label"] == "baseline"
    assert set(meta["files"][0]) == {"path", "sha256", "size"}
    for rel in SNAPSHOT_FILES:
        copy = snap / "files" / rel
        assert copy.is_file()
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == hashlib.sha256(
            (game / rel).read_bytes()
        ).hexdigest()
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["game_root"] == str(game.resolve())
    assert len(meta["files"]) == len(SNAPSHOT_FILES)
    assert meta["missing"] == []


def test_restore_round_trips(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    snapshot(game, tmp_path / "backups", "baseline")
    (game / SNAPSHOT_FILES[0]).write_text("changed\n", encoding="utf-8")
    result = restore(tmp_path / "backups" / "baseline", force=True)
    assert result["restored"] == len(SNAPSHOT_FILES)
    assert (game / SNAPSHOT_FILES[0]).read_text(encoding="utf-8") == (
        f"content:{SNAPSHOT_FILES[0]}\n"
    )


def test_restore_refuses_conflict_without_force(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    snapshot(game, tmp_path / "backups", "baseline")
    (game / SNAPSHOT_FILES[0]).write_text("changed\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        restore(tmp_path / "backups" / "baseline")
    assert (game / SNAPSHOT_FILES[0]).read_text(encoding="utf-8") == "changed\n"
    restore(tmp_path / "backups" / "baseline", force=True)
    assert (game / SNAPSHOT_FILES[0]).read_text(encoding="utf-8") == (
        f"content:{SNAPSHOT_FILES[0]}\n"
    )


def test_restore_rejects_bad_snapshot(tmp_path):
    snap = tmp_path / "snaps" / "empty"
    snap.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        restore(snap)


def test_snapshot_records_missing_source_files(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    removed = SNAPSHOT_FILES[0]
    (game / removed).unlink()
    meta = snapshot(game, tmp_path / "backups", "partial")
    assert meta["missing"] == [removed]
    assert [item["path"] for item in meta["files"]] == list(SNAPSHOT_FILES[1:])
    manifest = json.loads(
        (tmp_path / "backups" / "partial" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["missing"] == [removed]


def test_cli_snapshot_warns_and_returns_one_when_missing(tmp_path, capsys):
    game = tmp_path / "game"
    _seed(game)
    removed = SNAPSHOT_FILES[2]
    (game / removed).unlink()
    rc = main([
        "snapshot",
        "--game-root", str(game),
        "--dest", str(tmp_path / "backups"),
        "--label", "partial",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert f"WARNING: missing {removed}" in captured.err
    assert (tmp_path / "backups" / "partial" / "manifest.json").is_file()


def test_restore_rejects_corrupt_payload_without_writing(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    snapshot(game, tmp_path / "backups", "baseline")
    snap = tmp_path / "backups" / "baseline"
    (snap / "files" / SNAPSHOT_FILES[0]).write_text(
        "CORRUPTED-PAYLOAD\n", encoding="utf-8"
    )
    original = (game / SNAPSHOT_FILES[0]).read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        restore(snap, force=True)
    assert (game / SNAPSHOT_FILES[0]).read_text(encoding="utf-8") == original
    assert original == f"content:{SNAPSHOT_FILES[0]}\n"


def test_snapshot_rejects_unsafe_label(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    for label in ("", ".", "..", "../escape", "a/b", "a\\b", "C:escape"):
        with pytest.raises(ValueError):
            snapshot(game, tmp_path / "backups", label)


def test_snapshot_rejects_absolute_label(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    with pytest.raises(ValueError):
        snapshot(game, tmp_path / "backups", str(tmp_path / "escape"))
    assert not (tmp_path / "escape").exists()


def test_restore_rejects_manifest_path_escape(tmp_path):
    game = tmp_path / "game"
    _seed(game)
    snapshot(game, tmp_path / "backups", "baseline")
    snap = tmp_path / "backups" / "baseline"
    manifest_path = snap / "manifest.json"
    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta["files"][0]["path"] = "../../escaped.txt"
    manifest_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError):
        restore(snap, force=True)
    assert not (tmp_path.parent / "escaped.txt").exists()
