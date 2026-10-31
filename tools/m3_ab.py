#!/usr/bin/env python3
"""Compute medians and deltas from two smoke_run JSON files."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def load_menu_s(path: Path) -> list[float]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    values = [float(r["menu_s"]) for r in rows if r.get("ok")]
    if not values:
        raise SystemExit(f"no ok rounds in {path}")
    return values


def summarize(control: Path, treatment: Path) -> dict:
    c = load_menu_s(control)
    t = load_menu_s(treatment)
    cm = statistics.median(c)
    tm = statistics.median(t)
    return {
        "control_s": c,
        "treatment_s": t,
        "control_median_s": cm,
        "treatment_median_s": tm,
        "delta_s": round(cm - tm, 1),
        "delta_pct": round((cm - tm) / cm * 100, 2),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", required=True)
    ap.add_argument("--treatment", required=True)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    result = summarize(Path(args.control), Path(args.treatment))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
