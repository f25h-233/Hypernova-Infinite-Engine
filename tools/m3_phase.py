#!/usr/bin/env python3
"""Parse a Starsector session into 0-50 s phase timings.

Never assumes the M-1c (FR 0.9.5) table. Inputs may be rotated logs; the
parser takes the LAST Fast Rendering session and the LAST agent premain
session. Output is JSON so docs and the ledger can cite exact numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SESSION_RE = __import__("re").compile(
    r"^\s*(\d+)\s+\[[^\]]+\]\s+INFO\s+com\.genir\.renderer\.agent\.Agent\s+"
    r"-\s+Fast Rendering: v0\.9\.")
MENU_RE = __import__("re").compile(
    r"^\s*(\d+)\s+\[[^\]]+\]\s+INFO\s+sound\.H\s+"
    r"-\s+Playing music with id \[miscallenous_main_menu\.ogg\]")
CRAWL_RE = __import__("re").compile(r"Cached (\d+) files in (\d+)ms")
TIMELINE_RE = __import__("re").compile(
    r"timeline:\s*(\S+)\s+rel_ms=(\d+)\s+epoch_ms=(\d+)")
PRELOAD_RE = __import__("re").compile(
    r"scripts cache preloaded:.*entries=(\d+).*in (\d+) ms")


def _read(paths: list[str]) -> str:
    """Concatenate files oldest->newest so the LAST session is the newest run."""
    try:
        ordered = sorted(paths, key=lambda p: Path(p).stat().st_mtime)
    except OSError:
        ordered = list(paths)
    return b"".join(Path(p).read_bytes() for p in ordered).decode("utf-8", "replace")


def parse_session(text: str):
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if SESSION_RE.match(line)]
    if not starts:
        raise SystemExit("no Fast Rendering session anchor in log")
    session = lines[starts[-1]:]
    start_ms = int(SESSION_RE.match(session[0]).group(1))
    menu_ms = None
    for line in session:
        m = MENU_RE.match(line)
        if m:
            menu_ms = int(m.group(1)) - start_ms
    crawl = None
    for line in session:
        m = CRAWL_RE.search(line)
        if m:
            crawl = {"files": int(m.group(1)), "ms": int(m.group(2))}
    return session, start_ms, menu_ms, crawl


def parse_agent(text: str):
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if "hypernova agent premain" in line]
    session = lines[starts[-1]:] if starts else lines
    marks: dict[str, dict[str, int]] = {}
    for line in session:
        m = TIMELINE_RE.search(line)
        if m:
            marks[m.group(1)] = {"rel_ms": int(m.group(2)), "epoch_ms": int(m.group(3))}
    preload = None
    for line in session:
        m = PRELOAD_RE.search(line)
        if m:
            preload = {"entries": int(m.group(1)), "ms": int(m.group(2))}
    return marks, preload


def phases(marks: dict[str, dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in ("initFileLoaders", "initSpecStore", "initMods"):
        start = marks.get(name + ".start")
        end = marks.get(name + ".end")
        if start and end:
            out[name] = end["rel_ms"] - start["rel_ms"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="append", required=True,
                    help="session log(s); rotated files are read oldest->newest by mtime")
    ap.add_argument("--agent-log", action="append", default=[])
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    _, start_ms, menu_ms, crawl = parse_session(_read(args.log))
    marks, preload = ({}, None)
    if args.agent_log:
        marks, preload = parse_agent(_read(args.agent_log))
    result = {
        "session_start_ms": start_ms,
        "menu_ms": menu_ms,
        "crawl": crawl,
        "timeline": marks,
        "phases_ms": phases(marks),
        "preload": preload,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
    return 0 if menu_ms is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
