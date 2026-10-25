#!/usr/bin/env python3
"""M-1 日志测量器：按 session 统计首屏时间与纹理加载量。

用法:
    python -I tools/m1_measure.py <starsector.log> [--session N] [--json]

口径见规格附录 A：
  - session 以 "正在运行 Starsector" 为界（一个滚动日志里可能追加多次启动）
  - t_main_menu = 该 session 内首条 CodexTextEntryLoader "Parsing entry" 的毫秒戳
  - "Loading image [" 只统计 PNG 解码（DDS 命中在打日志前 return）
  - "Loading DDS texture a/b" 的最大 b = 本次排队 DDS 总数
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

BANNER = "正在运行 Starsector"
IMG_RE = re.compile(r"Loading image \[([^\]]*)\]")
THREAD_RE = re.compile(r"^\d+\s+\[([^\]]+)\]")
MS_RE = re.compile(r"^(\d+)\s")
DDS_RE = re.compile(r"Loading DDS texture (\d+)/(\d+)")
ANCHOR = "Parsing entry"


def read_sessions(path: Path) -> list[int]:
    starts: list[int] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if BANNER in line:
                starts.append(lineno)
    return starts


def measure(path: Path, start: int, end: int) -> dict:
    images = 0
    paths: set[str] = set()
    threads: Counter[str] = Counter()
    cache = 0
    normal = 0
    anchor_ms: int | None = None
    anchor_line: int | None = None
    dds_denoms: list[int] = []
    max_ms = 0
    snap: dict | None = None

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if lineno < start:
                continue
            if lineno >= end:
                break
            m = MS_RE.match(line)
            if m:
                ms = int(m.group(1))
                if ms > max_ms:
                    max_ms = ms
            if ANCHOR in line and "CodexTextEntryLoader" in line and anchor_ms is None:
                anchor_ms = int(MS_RE.match(line).group(1)) if MS_RE.match(line) else None
                anchor_line = lineno
                snap = {
                    "loading_image_lines": images,
                    "unique_paths": len(paths),
                    "cache_lines": cache,
                    "normal_lines": normal,
                    "threads": dict(threads),
                }
            if "Loading image [" in line:
                images += 1
                im = IMG_RE.search(line)
                if im:
                    p = im.group(1)
                    paths.add(p)
                    if p.startswith("cache/"):
                        cache += 1
                    if "_normal" in p:
                        normal += 1
                tm = THREAD_RE.match(line)
                if tm:
                    threads[tm.group(1)] += 1
            dm = DDS_RE.search(line)
            if dm:
                dds_denoms.append(int(dm.group(2)))

    return {
        "start_line": start,
        "end_line": end - 1,
        "max_ms": max_ms,
        "t_main_menu_ms": anchor_ms,
        "anchor_line": anchor_line,
        "loading_image_lines": images,
        "unique_paths": len(paths),
        "cache_lines": cache,
        "normal_lines": normal,
        "dds_queued_max": max(dds_denoms) if dds_denoms else None,
        "threads": dict(threads.most_common()),
        "at_menu": snap,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--session", type=int, default=0, help="1-based; 默认最后一个")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"log not found: {path}", file=sys.stderr)
        return 2
    starts = read_sessions(path)
    if not starts:
        print("no session banner found", file=sys.stderr)
        return 3

    idx = args.session or len(starts)
    if idx < 1 or idx > len(starts):
        print(f"session out of range 1..{len(starts)}", file=sys.stderr)
        return 4
    start = starts[idx - 1]
    end = starts[idx] if idx < len(starts) else path.stat().st_size + 1
    # end 是下一 session 的行号；文件末尾用一个大数
    if idx == len(starts):
        end = 1 << 60

    result = measure(path, start, end)
    result["session"] = idx
    result["sessions_total"] = len(starts)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"session {idx}/{len(starts)}  lines {result['start_line']}..{result['end_line']}")
        print(f"  t_main_menu      : {result['t_main_menu_ms']} ms (line {result['anchor_line']})")
        at = result["at_menu"] or {}
        print(f"  到主菜单         : images={at.get('loading_image_lines')} unique={at.get('unique_paths')} "
              f"cache={at.get('cache_lines')} normal={at.get('normal_lines')}")
        print(f"  整个 session     : images={result['loading_image_lines']} (unique {result['unique_paths']})")
        print(f"    cache/         : {result['cache_lines']}")
        print(f"    *_normal       : {result['normal_lines']}")
        print(f"  DDS queued max   : {result['dds_queued_max']}")
        print("  threads          : " + ", ".join(f"{k}={v}" for k, v in result["threads"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
