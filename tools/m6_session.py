"""M6：实机会话开始/结束。开始前轮转日志，结束后合并证据。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
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

# 只清理/覆盖本工具自己命名的半成品，不碰用户或其它进程放进 logs/ 的文件。
KNOWN_ARTIFACTS = frozenset(
    f"{prefix}{name}.log"
    for name in LOG_RELS
    for prefix in ("pre-", "rotated-")
)

# 文件系统 mtime 精度/时钟取整可能让“刚写的日志”比 started_at 早一点点。
FRESH_TOLERANCE_SECONDS = 2.0


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _validate_label(label: str) -> str:
    """label 只能是 evidence_root 下的单段目录名，不能逃逸或跨盘。"""
    if not isinstance(label, str):
        raise ValueError("invalid label: must be a string")
    if not label or label in {".", ".."}:
        raise ValueError(f"invalid label: {label!r}")
    if label != label.strip():
        raise ValueError(f"invalid label (leading/trailing whitespace): {label!r}")
    if any(ch in label for ch in ("/", "\\", ":", "\x00")):
        raise ValueError(
            f"invalid label (path separator or reserved char): {label!r}"
        )
    if any(ord(ch) < 32 for ch in label):
        raise ValueError(f"invalid label (control character): {label!r}")
    if Path(label).is_absolute() or Path(label).name != label:
        raise ValueError(f"invalid label (must be a single path segment): {label!r}")
    return label


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _rmdir_quietly(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def start(game_root: str | Path, evidence_root: str | Path, label: str) -> dict:
    label = _validate_label(label)
    root = Path(game_root).resolve()
    session_dir = Path(evidence_root).resolve() / label
    logs_dir = session_dir / "logs"
    meta_path = session_dir / "session-meta.json"
    if meta_path.is_file():
        raise FileExistsError(f"session already started: {logs_dir}")
    if logs_dir.exists():
        if not logs_dir.is_dir():
            raise FileExistsError(f"session log path is not a directory: {logs_dir}")
        names = {path.name for path in logs_dir.iterdir()}
        unknown = sorted(names - KNOWN_ARTIFACTS)
        if unknown:
            raise FileExistsError(
                "session log dir has unexpected files (refusing to delete): "
                + ", ".join(unknown)
            )
        # 上次 start 失败留下的已知半成品：只清理这些，允许安全重试。
        for name in names:
            _unlink_quietly(logs_dir / name)
    else:
        logs_dir.mkdir(parents=True)

    started_epoch = time.time()
    created_pre: list[Path] = []
    moved: list[tuple[Path, Path]] = []
    entries: list[dict] = []
    try:
        # 先把所有日志完整复制到 evidence，再移动原文件；
        # 任一步失败都不会丢掉原日志或本次复制出的副本。
        pending: list[tuple[str, Path, Path]] = []
        for name, rel in LOG_RELS.items():
            src = root / rel
            if not src.is_file():
                continue
            pre = logs_dir / f"pre-{name}.log"
            shutil.copy2(src, pre)
            created_pre.append(pre)
            pending.append((name, src, pre))
        for name, src, pre in pending:
            rotated = logs_dir / f"rotated-{name}.log"
            shutil.move(str(src), str(rotated))
            moved.append((src, rotated))
            entries.append({
                "name": name,
                "path": str(pre),
                "rotated": str(rotated),
                "pre_size": pre.stat().st_size,
                "pre_mtime": pre.stat().st_mtime,
            })
        meta = {
            "label": label,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "started_at_epoch": started_epoch,
            "game_root": str(root),
            "logs": entries,
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except BaseException as exc:
        rollback_errors: list[str] = []
        for src, rotated in reversed(moved):
            if src.exists():
                rollback_errors.append(f"{src} reappeared; left {rotated}")
                continue
            try:
                shutil.move(str(rotated), str(src))
            except OSError as rollback_exc:
                rollback_errors.append(f"{rotated} -> {src}: {rollback_exc}")
        if not rollback_errors:
            # 写 meta 失败可能留下半截文件；删除后同一 label 才能安全重试。
            _unlink_quietly(meta_path)
            for pre in created_pre:
                _unlink_quietly(pre)
        _rmdir_quietly(logs_dir)
        _rmdir_quietly(session_dir)
        if rollback_errors:
            raise RuntimeError(
                f"start failed ({exc}); rollback incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    return meta


def _load_meta(session_dir: Path) -> dict:
    meta_path = session_dir / "session-meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"session not started (missing {meta_path}); run start first"
        )
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid session-meta.json: {meta_path}")
    return data


def _started_epoch(meta: dict) -> float | None:
    value = meta.get("started_at_epoch")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = meta.get("started_at")
    if isinstance(text, str):
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return None
    return None


def _log_growth(root: Path, started_epoch: float | None) -> dict:
    """检查当前日志是否在 start 之后新建/更新；旧日志不能当新会话证据。"""
    growth: dict[str, dict] = {}
    for name, rel in LOG_RELS.items():
        path = root / rel
        if not path.is_file():
            growth[name] = {"present": False, "fresh": False}
            continue
        stat = path.stat()
        fresh = (
            started_epoch is not None
            and stat.st_mtime >= started_epoch - FRESH_TOLERANCE_SECONDS
        )
        growth[name] = {
            "present": True,
            "fresh": bool(fresh),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }
    return growth


def end(game_root: str | Path, evidence_root: str | Path, label: str) -> dict:
    label = _validate_label(label)
    root = Path(game_root).resolve()
    session_dir = Path(evidence_root).resolve() / label
    meta = _load_meta(session_dir)
    started_epoch = _started_epoch(meta)
    starsector = root / LOG_RELS["starsector"]
    agent = root / LOG_RELS["scripts-agent"]
    report = build_report(_read(agent), _read(starsector))
    audit = scan_logs(starsector, agent)
    growth = _log_growth(root, started_epoch)
    new_logs_ok = all(growth[name]["fresh"] for name in LOG_RELS)
    health = report["health"]
    lazy_health = {
        "failed": health["lazy_failed_zero"],
        "disabled": health["lazy_disabled_zero"],
        "dimMismatch": health["lazy_dim_mismatch_zero"],
        "failedParked": health["lazy_failed_parked_zero"],
    }
    lazy_health_ok = all(value is True for value in lazy_health.values())

    problems: list[str] = []
    if not report["starsector_session"]["anchor_found"]:
        problems.append("no session anchor")
    if not report["frame_probe"]["present"]:
        problems.append("no frame probe")
    if not report["lazy"]["present"]:
        problems.append("no lazy summary")
    elif not lazy_health_ok:
        unhealthy = [name for name, value in lazy_health.items() if value is not True]
        problems.append("lazy health not zero: " + ", ".join(unhealthy))
    if report["texture_errors_total"] != 0:
        problems.append(f"texture errors: {report['texture_errors_total']}")
    if not audit["complete"]:
        problems.append("incomplete logs")
    if audit["total"] != 0:
        problems.append(f"log audit errors: {audit['total']}")
    if started_epoch is None:
        problems.append("session-meta missing started_at")
    if not new_logs_ok:
        problems.append("no new logs since start")

    merged = {
        "label": label,
        **report,
        "log_audit": audit,
        "new_logs": growth,
        "new_logs_ok": new_logs_ok,
        "problems": problems,
        "ok": not problems,
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
    if args.command == "start":
        if not result.get("logs"):
            print(f"WARNING: no logs found under {args.game_root}", file=sys.stderr)
        return 0
    if not result.get("ok", True):
        problems = result.get("problems") or ["see session.json for details"]
        print(
            f"m6_session: session not ok: label={args.label}: "
            + "; ".join(problems),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
