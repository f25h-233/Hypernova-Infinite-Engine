#!/usr/bin/env python3
"""把 starsector.log 的首屏 PNG 加载行采成 demand.jsonl。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

BANNER = "正在运行 Starsector"
IMG_RE = re.compile(r"Loading image \[([^\]]*)\]")
THREAD_RE = re.compile(r"^\d+\s+\[([^\]]+)\]")
MS_RE = re.compile(r"^(\d+)\s")
ANCHOR_CLASS = "CodexTextEntryLoader"
ANCHOR_TEXT = "Parsing entry"


def read_sessions(path: Path) -> list[tuple[int, int]]:
    starts = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            total = lineno
            if BANNER in line:
                starts.append(lineno)
    if not starts:
        return []
    out = []
    for i, start in enumerate(starts):
        end = starts[i + 1] - 1 if i + 1 < len(starts) else total
        out.append((start, end))
    return out


def collect_session(
    path: Path, start: int, end: int, until_anchor: bool = True
) -> tuple[list[dict], dict]:
    records: list[dict] = []
    threads: Counter[str] = Counter()
    anchor_ms = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if lineno < start:
                continue
            if lineno > end:
                break
            ms = None
            m = MS_RE.match(line)
            if m:
                ms = int(m.group(1))
            if until_anchor and ANCHOR_CLASS in line and ANCHOR_TEXT in line:
                anchor_ms = ms
                break
            m = IMG_RE.search(line)
            if not m:
                continue
            thread = ""
            tm = THREAD_RE.match(line)
            if tm:
                thread = tm.group(1)
            threads[thread] += 1
            records.append(
                {
                    "session": 0,
                    "line": lineno,
                    "ms": ms,
                    "thread": thread,
                    "path": m.group(1).replace("\\", "/"),
                }
            )
    summary = {
        "anchor_ms": anchor_ms,
        "records": len(records),
        "unique_paths": len({r["path"] for r in records}),
        "threads": dict(threads),
    }
    return records, summary


def collect(
    path: Path, session: int | None = None, until_anchor: bool = True
) -> tuple[list[dict], dict]:
    sessions = read_sessions(path)
    if not sessions:
        return [], {"sessions": 0, "records": 0, "unique_paths": 0, "anchor_ms": None}
    selected = (
        [(session, sessions[session - 1])]
        if session is not None
        else list(enumerate(sessions, 1))
    )
    all_records: list[dict] = []
    anchors = {}
    total_threads: Counter[str] = Counter()
    for number, (start, end) in selected:
        records, summary = collect_session(path, start, end, until_anchor)
        for record in records:
            record["session"] = number
        all_records.extend(records)
        total_threads.update(summary["threads"])
        if summary["anchor_ms"] is not None:
            anchors[number] = summary["anchor_ms"]
    return all_records, {
        "sessions": len(selected),
        "records": len(all_records),
        "unique_paths": len({r["path"] for r in all_records}),
        "anchor_ms": anchors if session is None else anchors.get(session),
        "threads": dict(total_threads),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--session", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    records, summary = collect(args.log, args.session)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
