"""M6：备份/恢复影响兼容性判定的 4 个环境文件（只复制，不修改源）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SNAPSHOT_FILES = (
    "mods/enabled_mods.json",
    "mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json",
    "Miko_Lite.txt",
    "starsector-core/data/config/settings.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(game_root: str | Path, dest: str | Path, label: str) -> dict:
    root = Path(game_root).resolve()
    snap = Path(dest).resolve() / label
    if snap.exists():
        raise FileExistsError(f"snapshot already exists: {snap}")
    files = []
    for rel in SNAPSHOT_FILES:
        src = root / rel
        if not src.is_file():
            continue
        copy = snap / "files" / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, copy)
        files.append({
            "path": rel,
            "sha256": sha256_file(src),
            "size": src.stat().st_size,
        })
    meta = {
        "label": label,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "game_root": str(root),
        "files": files,
    }
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return meta


def restore(snapshot_dir: str | Path, *, force: bool = False) -> dict:
    snap = Path(snapshot_dir).resolve()
    manifest_path = snap / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(meta["game_root"])
    conflicts = []
    for item in meta["files"]:
        target = root / item["path"]
        source = snap / "files" / item["path"]
        if not source.is_file():
            raise FileNotFoundError(f"missing snapshot file: {source}")
        if target.is_file() and sha256_file(target) != item["sha256"]:
            conflicts.append(item["path"])
    if conflicts and not force:
        raise FileExistsError(
            "current files differ from snapshot; use --force to overwrite: "
            + ", ".join(conflicts)
        )
    restored = 0
    for item in meta["files"]:
        target = root / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snap / "files" / item["path"], target)
        restored += 1
    return {"restored": restored, "game_root": str(root), "label": meta["label"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--game-root", required=True, type=Path)
    snap.add_argument("--dest", required=True, type=Path)
    snap.add_argument("--label", required=True)
    rest = sub.add_parser("restore")
    rest.add_argument("--snapshot", required=True, type=Path)
    rest.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = snapshot(args.game_root, args.dest, args.label)
        else:
            result = restore(args.snapshot, force=args.force)
    except Exception as exc:  # noqa: BLE001 - fail-closed
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
