#!/usr/bin/env python3
"""Summarize one M2.5 probe session from the agent log + smoke JSON."""
import argparse
import json
import re
import sys
from pathlib import Path

INDEX_RE = re.compile(
    r"lazy probe: index loaded paths=(\d+) invalid=(\d+) in (\d+) ms")
SUMMARY_RE = re.compile(
    r"lazy probe: summary queue=(\d+) wouldSkip=(\d+) lookups=(\d+) demand=(\d+) index=(\S+)")
OPERATIONAL_RE = re.compile(
    r"queuedSkip=(\d+) demandQueued=(\d+) hits=(\d+) misses=(\d+) degraded=(\d+)")


def _timestamp(line: str) -> str:
    return line.split(" ", 1)[0]


def parse_agent_log(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    session = lines[start:]
    out = {
        "session_lines": len(session),
        "premain_ts": _timestamp(session[0]) if session else None,
        "agent_errors": 0,
        "index_paths": 0,
        "index_invalid": 0,
        "index_ms": 0,
        "queue_hook": False,
        "lookup_hook": False,
        "wired": False,
        "summary": None,
        "summary_series": [],
        "operational": {
            "queued_skip": None,
            "demand_queued": None,
            "hits": None,
            "misses": None,
            "degraded": None,
        },
        "would_skip_samples": 0,
        "demand_samples": 0,
    }
    for line in session:
        if " ERROR " in line:
            out["agent_errors"] += 1
        m = INDEX_RE.search(line)
        if m:
            out["index_paths"] = int(m.group(1))
            out["index_invalid"] = int(m.group(2))
            out["index_ms"] = int(m.group(3))
        if "queue lambda hook added" in line:
            out["queue_hook"] = True
        if "repository lookup hook added" in line:
            out["lookup_hook"] = True
        if "lambda wired" in line:
            out["wired"] = True
        if "lazy probe: would-skip " in line:
            out["would_skip_samples"] += 1
        if "lazy probe: demand " in line:
            out["demand_samples"] += 1
        m = SUMMARY_RE.search(line)
        if m:
            raw = {
                "queue": int(m.group(1)),
                "would_skip": int(m.group(2)),
                "lookups": int(m.group(3)),
                "demand": int(m.group(4)),
                "index": m.group(5),
            }
            out["summary"] = raw
            record = {"ts": _timestamp(line)}
            record.update(raw)
            op = OPERATIONAL_RE.search(line)
            if op:
                record.update({
                    "queued_skip": int(op.group(1)),
                    "demand_queued": int(op.group(2)),
                    "hits": int(op.group(3)),
                    "misses": int(op.group(4)),
                    "degraded": int(op.group(5)),
                })
            out["summary_series"].append(record)
    s = out["summary"]
    out["skip_fraction"] = (s["would_skip"] / s["queue"]) if s and s["queue"] else 0.0
    last = out["summary_series"][-1] if out["summary_series"] else {}
    out["operational"] = {
        "queued_skip": last.get("queued_skip"),
        "demand_queued": last.get("demand_queued"),
        "hits": last.get("hits"),
        "misses": last.get("misses"),
        "degraded": last.get("degraded"),
    }
    demand_queued = out["operational"]["demand_queued"]
    out["operational_fraction"] = (
        demand_queued / s["would_skip"]
        if demand_queued is not None and s and s["would_skip"] else 0.0)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-log", required=True)
    ap.add_argument("--smoke-json", default="")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    text = Path(args.agent_log).read_text(encoding="utf-8", errors="replace")
    result = parse_agent_log(text)
    if args.smoke_json:
        try:
            rows = json.loads(Path(args.smoke_json).read_text(encoding="utf-8"))
            result["menu_s"] = rows[0].get("menu_s") if rows else None
        except Exception as exc:
            result["smoke_error"] = str(exc)
    result["ok"] = bool(
        result["queue_hook"] and result["lookup_hook"] and result["wired"]
        and result["summary"] and result["summary"]["queue"] > 0
        and result["index_paths"] > 0
        and result["agent_errors"] == 0
        and result["operational"]["degraded"] == 0
        and result.get("menu_s") is not None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
