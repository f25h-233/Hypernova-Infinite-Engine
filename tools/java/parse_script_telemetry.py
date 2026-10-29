#!/usr/bin/env python3
"""Summarize Hypernova scripts-cache JSONL telemetry."""
import json
import sys
from pathlib import Path


def summaries(path: Path) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("kind") == "summary":
                out.append(event)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: parse-script-telemetry.py <jsonl>", file=sys.stderr)
        return 2
    found = summaries(Path(sys.argv[1]))
    if not found:
        print("no summary event", file=sys.stderr)
        return 1
    print(json.dumps(found[-1], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
