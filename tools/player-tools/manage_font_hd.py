#!/usr/bin/env python3
"""还原 Hypernova 高清字体桥覆盖过的游戏字体文件。

Hypernova agent 在远星汉化优化测试版上会把
``starsector-core/graphics/fonts/`` 下的若干 ``*.fnt`` / ``*_0.png``
替换成优化版生成的高清图集，并把原文件备份为 ``*.bak-hypernova-hd``。
本脚本扫描这些备份并逐个还原；还原后删除备份。

用法：
    python -I manage_font_hd.py --action restore [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKUP_SUFFIX = ".bak-hypernova-hd"


def here() -> tuple[Path, Path | None]:
    """返回 (工具目录, 游戏目录)；游戏目录靠往上找带 starsector-core 的祖先。"""
    tool_dir = Path(__file__).resolve().parent
    mod_root = tool_dir.parent
    for cand in mod_root.parents:
        if (cand / "starsector-core").is_dir():
            return tool_dir, cand
    return tool_dir, None


def backups(game: Path) -> list[Path]:
    fonts = game / "starsector-core" / "graphics" / "fonts"
    if not fonts.is_dir():
        return []
    return sorted(fonts.rglob(f"*{BACKUP_SUFFIX}"))


def restore(game: Path, dry_run: bool = False) -> tuple[int, int]:
    """把每份备份还原到去掉后缀的目标；返回 (restored, failed)。"""
    restored = 0
    failed = 0
    for backup in backups(game):
        target = backup.with_name(backup.name[: -len(BACKUP_SUFFIX)])
        try:
            if dry_run:
                print(f"  would restore: {target.relative_to(game)}")
            else:
                print(f"  restore: {target.relative_to(game)}")
                shutil.copy2(backup, target)
                backup.unlink()
            restored += 1
        except OSError as exc:
            failed += 1
            print(f"  FAILED: {backup.name}: {exc}", file=sys.stderr)
    return restored, failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--action", choices=["restore"], default="restore")
    ap.add_argument("--game-root", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    _, game = here()
    if args.game_root is not None:
        game = args.game_root
    if game is None or not (game / "starsector-core").is_dir():
        print("[错误] 没找到游戏目录。")
        print("       请把整个 hypernova-tools 文件夹放在"
              " 游戏目录\\mods\\hypernova_infinite_engine\\ 下再运行，")
        print("       或用 --game-root 指定游戏根目录。")
        return 1

    found = backups(game)
    if not found:
        print("没有找到 .bak-hypernova-hd 备份，字体已经是原版状态。")
        return 0

    print(f"发现 {len(found)} 份字体备份，"
          f"{'只检查不写入' if args.dry_run else '开始还原'}：")
    restored, failed = restore(game, dry_run=args.dry_run)
    print()
    if args.dry_run:
        print(f"dry-run：{restored} 份可还原，{failed} 份失败。")
    else:
        print(f"完成：还原 {restored} 份，失败 {failed} 份。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
