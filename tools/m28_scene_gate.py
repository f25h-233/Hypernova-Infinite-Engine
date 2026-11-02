#!/usr/bin/env python3
"""M2.8 scene-eviction gate evidence parser.

Reads the last `lazy probe: summary` line from the agent log, the last
Starsector session slice, and an optional GPU sample CSV. Emits JSON so the
control/treatment runs are compared from files, not manual transcription.

Usage:
    python tools/m28_scene_gate.py \
        --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
        --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
        --gpu-csv build/m28/gpu-treatment.csv \
        --require-scene --strict --out build/m28/treatment.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

SUMMARY_MARKER = "lazy probe: summary"
SESSION_ANCHOR = "Fast Rendering: v0.9."
TEXTURE_ERRORS = (
    "Failed to load texture",
    "VerifyError",
    "ClassFormatError",
    "AsyncException",
    "isStateCorrupted",
)
_KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")


def parse_summary_line(line: str) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for key, value in _KEY_VALUE.findall(line):
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = value
    return out


def last_summary(text: str) -> dict[str, int | str]:
    lines = [line for line in text.splitlines() if SUMMARY_MARKER in line]
    if not lines:
        raise ValueError("no lazy probe summary line in agent log")
    return parse_summary_line(lines[-1])


def last_session(text: str, anchor: str = SESSION_ANCHOR) -> str:
    idx = text.rfind(anchor)
    return text if idx < 0 else text[idx:]


def count_texture_errors(text: str) -> dict[str, int]:
    return {name: text.count(name) for name in TEXTURE_ERRORS}


def summarize_gpu(
        rows: list[tuple[float, float | None, float | None]]) -> dict:
    dedicated = [r[1] for r in rows if r[1] is not None]
    shared = [r[2] for r in rows if r[2] is not None]

    def stats(values: list[float]) -> dict | None:
        if not values:
            return None
        values = sorted(values)
        mid = len(values) // 2
        median = (values[mid] if len(values) % 2
                  else (values[mid - 1] + values[mid]) / 2)
        return {
            "min": round(values[0], 1),
            "median": round(median, 1),
            "max": round(values[-1], 1),
        }

    return {
        "samples": len(rows),
        "dedicated_mb": stats(dedicated),
        "shared_mb": stats(shared),
    }


def read_gpu_csv(
        path: Path) -> list[tuple[float, float | None, float | None]]:
    rows: list[tuple[float, float | None, float | None]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                ts = float(row.get("timestamp", ""))
            except (TypeError, ValueError):
                continue

            def number(name: str) -> float | None:
                raw = (row.get(name) or "").strip()
                return float(raw) if raw else None

            rows.append((ts, number("dedicated_mb"), number("shared_mb")))
    return rows


def build_report(
        agent_text: str,
        starsector_text: str,
        gpu_rows: list[tuple[float, float | None, float | None]] | None = None,
) -> dict:
    summary = last_summary(agent_text)
    errors = count_texture_errors(last_session(starsector_text))
    report = {
        "summary": summary,
        "texture_errors": errors,
        "texture_errors_total": sum(errors.values()),
        "scene_evictions": summary.get("sceneEvictions", 0),
        "scene_passes": summary.get("scenePasses", 0),
        "failed_parked": summary.get("failedParked", 0),
    }
    if gpu_rows is not None:
        report["gpu"] = summarize_gpu(gpu_rows)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-log", type=Path, required=True)
    parser.add_argument("--starsector-log", type=Path, required=True)
    parser.add_argument("--gpu-csv", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-scene", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    gpu_rows = read_gpu_csv(args.gpu_csv) if args.gpu_csv else None
    report = build_report(
        args.agent_log.read_text(encoding="utf-8", errors="replace"),
        args.starsector_log.read_text(encoding="utf-8", errors="replace"),
        gpu_rows,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.strict:
        if report["texture_errors_total"] > 0 or report["failed_parked"] > 0:
            return 1
        if args.require_scene and report["scene_evictions"] <= 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
