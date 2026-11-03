"""M6：实机会话开始/结束。开始前轮转日志，结束后合并证据。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from m4_session_report import build_report  # noqa: E402
from m6_log_audit import scan_logs  # noqa: E402

LOG_RELS = {
    "starsector": "starsector-core/starsector.log",
    "scripts-agent": "saves/hypernova/scripts-agent.log",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def start(game_root: str | Path, evidence_root: str | Path, label: str) -> dict:
    root = Path(game_root).resolve()
    session_dir = Path(evidence_root).resolve() / label
    logs_dir = session_dir / "logs"
    if logs_dir.exists():
        raise FileExistsError(f"session already started: {logs_dir}")
    logs_dir.mkdir(parents=True)
    moved = []
    for name, rel in LOG_RELS.items():
        src = root / rel
        if not src.is_file():
            continue
        dst = logs_dir / f"pre-{name}.log"
        shutil.copy2(src, dst)
        os.replace(src, logs_dir / f"rotated-{name}.log")
        moved.append({"name": name, "path": str(dst)})
    meta = {
        "label": label,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "game_root": str(root),
        "logs": moved,
    }
    (session_dir / "session-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return meta


def end(game_root: str | Path, evidence_root: str | Path, label: str) -> dict:
    root = Path(game_root).resolve()
    session_dir = Path(evidence_root).resolve() / label
    starsector = root / LOG_RELS["starsector"]
    agent = root / LOG_RELS["scripts-agent"]
    report = build_report(_read(agent), _read(starsector))
    audit = scan_logs(starsector, agent)
    merged = {
        "label": label,
        **report,
        "log_audit": audit,
        "ok": bool(
            report["starsector_session"]["anchor_found"]
            and report["frame_probe"]["present"]
            and report["lazy"]["present"]
            and report["texture_errors_total"] == 0
            and audit["complete"]
            and audit["total"] == 0
        ),
    }
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "end"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--game-root", required=True, type=Path)
        cmd.add_argument("--evidence-root", required=True, type=Path)
        cmd.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    try:
        result = (start if args.command == "start" else end)(
            args.game_root, args.evidence_root, args.label
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
