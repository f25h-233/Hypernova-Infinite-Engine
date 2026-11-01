#!/usr/bin/env python3
"""Generate the M2.5 lazy skip file from the runtime manifest.

Format: UTF-8, LF, one record per line: <path>\t<w>\t<h>.
Only L2/L3 paths are eligible. L1 always wins; entries without usable
dimensions and FR's blacklist paths are excluded. The file is written
atomically (sibling .tmp + os.replace).
"""
import argparse
import json
import os
import sys
from pathlib import Path

BLACKLIST_PREFIX = "graphics/ui/bottomright"


def build_skip(manifest: dict) -> tuple[list[tuple[str, int, int]], dict]:
    layers = manifest.get("layers") or {}
    if not isinstance(layers, dict):
        layers = {}
    l1 = {e.get("path") for e in layers.get("L1") or [] if isinstance(e, dict)}
    stats = {
        "l1": len(l1),
        "candidates": 0,
        "skip": 0,
        "excluded_l1": 0,
        "excluded_invalid": 0,
        "excluded_blacklist": 0,
        "excluded_duplicate": 0,
    }
    seen: set[str] = set()
    out: list[tuple[str, int, int]] = []
    for layer in ("L2", "L3"):
        for entry in layers.get(layer) or []:
            if not isinstance(entry, dict):
                continue
            stats["candidates"] += 1
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                stats["excluded_invalid"] += 1
                continue
            if path in l1:
                stats["excluded_l1"] += 1
                continue
            if path.startswith(BLACKLIST_PREFIX):
                stats["excluded_blacklist"] += 1
                continue
            w, h = entry.get("w"), entry.get("h")
            if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
                stats["excluded_invalid"] += 1
                continue
            if path in seen:
                stats["excluded_duplicate"] += 1
                continue
            seen.add(path)
            out.append((path, w, h))
    out.sort()
    stats["skip"] = len(out)
    return out, stats


def write_skip(path: Path, rows: list[tuple[str, int, int]],
               header: str | None = None) -> None:
    """Write an optional header line plus one ``<path>\\t<w>\\t<h>`` per row.

    No staging: the caller owns atomicity. Multi-file installs (manifest +
    skip) stage every file first and only then ``os.replace`` them, so this
    helper writes straight to the path it is given.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        if header is not None:
            f.write(header.rstrip("\n") + "\n")
        for p, w, h in rows:
            f.write(f"{p}\t{w}\t{h}\n")
        f.flush()
        os.fsync(f.fileno())


def write_atomic(path: Path, rows: list[tuple[str, int, int]],
                 header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    write_skip(tmp, rows, header)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--max-paths", type=int, default=200_000)
    args = ap.parse_args(argv)
    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 2
    rows, stats = build_skip(data)
    if len(rows) > args.max_paths:
        print(f"FATAL: skip set {len(rows)} > --max-paths {args.max_paths}", file=sys.stderr)
        return 2
    write_atomic(Path(args.out), rows)
    stats["out"] = str(args.out)
    stats["bytes"] = Path(args.out).stat().st_size
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"stats": stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
