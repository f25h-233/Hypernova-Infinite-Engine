import hashlib
import json
from pathlib import Path

import pytest

from m6_env_snapshot import SNAPSHOT_FILES, restore, snapshot


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
