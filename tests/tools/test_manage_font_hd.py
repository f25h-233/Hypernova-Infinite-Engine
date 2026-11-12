import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "player-tools"))
import manage_font_hd as mf


def _fake_game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    (game / "starsector-core" / "graphics" / "fonts").mkdir(parents=True)
    return game


def test_restore_copies_backup_and_deletes_it(tmp_path):
    game = _fake_game(tmp_path)
    fonts = game / "starsector-core" / "graphics" / "fonts"
    target = fonts / "fontA.fnt"
    target.write_text("hd-font")
    backup = fonts / "fontA.fnt.bak-hypernova-hd"
    backup.write_text("original-font")

    restored, failed = mf.restore(game, dry_run=False)

    assert (restored, failed) == (1, 0)
    assert target.read_text() == "original-font"
    assert not backup.exists()


def test_dry_run_keeps_target_and_backup(tmp_path):
    game = _fake_game(tmp_path)
    fonts = game / "starsector-core" / "graphics" / "fonts"
    target = fonts / "fontA_0.png"
    target.write_text("hd-page")
    backup = fonts / "fontA_0.png.bak-hypernova-hd"
    backup.write_text("original-page")

    restored, failed = mf.restore(game, dry_run=True)

    assert (restored, failed) == (1, 0)
    assert target.read_text() == "hd-page"
    assert backup.read_text() == "original-page"


def test_no_backups_is_a_noop(tmp_path):
    game = _fake_game(tmp_path)
    assert mf.backups(game) == []
    assert mf.restore(game, dry_run=False) == (0, 0)


def test_backups_finds_nested_font_directories(tmp_path):
    game = _fake_game(tmp_path)
    fonts = game / "starsector-core" / "graphics" / "fonts"
    nested = fonts / "nested"
    nested.mkdir()
    backup = nested / "fontB.fnt.bak-hypernova-hd"
    backup.write_text("original")
    (nested / "fontB.fnt").write_text("hd")

    assert mf.backups(game) == [backup]
    restored, failed = mf.restore(game, dry_run=False)
    assert (restored, failed) == (1, 0)
    assert (nested / "fontB.fnt").read_text() == "original"
    assert not backup.exists()
