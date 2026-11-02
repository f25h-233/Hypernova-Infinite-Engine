#!/usr/bin/env python3
"""M2.8 scene-eviction gate evidence parser.

Reads the last valid `lazy probe: summary` line from the current agent
session, the last Starsector session slice, and an optional GPU sample CSV.
Emits JSON so the control/treatment runs are compared from files, not manual
transcription.

A summary only counts when it appears after the last
`hypernova agent premain` anchor and contains every key in
REQUIRED_SUMMARY_KEYS. Stale/old-format summaries are rejected instead of
being reported as zeros.

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
import math
import re
import sys
from pathlib import Path

SUMMARY_MARKER = "lazy probe: summary"
AGENT_SESSION_ANCHOR = "hypernova agent premain"
SESSION_ANCHOR = "Fast Rendering: v0.9."
TEXTURE_ERRORS = (
    "Failed to load texture",
    "VerifyError",
    "ClassFormatError",
    "AsyncException",
    "isStateCorrupted",
)
REQUIRED_SUMMARY_KEYS = (
    "queue",
    "failedParked",
    "sceneUnload",
    "scenePasses",
    "sceneEvictions",
    "sceneEvictMsTotal",
    "sceneEvictMsMax",
    "scenePending",
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


def agent_session(text: str) -> tuple[str, int | None, int]:
    """Return the text after the last agent premain anchor, its 1-based
    line number, and the total anchor count."""
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines)
               if AGENT_SESSION_ANCHOR in line]
    if not anchors:
        return text, None, 0
    index = anchors[-1]
    return "".join(lines[index + 1:]), index + 1, len(anchors)


def find_summary(
        text: str) -> tuple[dict[str, int | str], int, int, int]:
    """Return (summary, summary_line, anchor_line, anchor_count).

    Only the last valid summary after the last agent-session anchor counts.
    Old-format lines (missing scene keys), truncated lines, and
    `lazy probe: summary failed` errors are skipped.
    """
    session, anchor_line, anchor_count = agent_session(text)
    if anchor_line is None:
        raise ValueError(
            "no agent session anchor 'hypernova agent premain' in agent log")

    missing_keys = list(REQUIRED_SUMMARY_KEYS)
    found: tuple[dict[str, int | str], int] | None = None
    for offset, line in enumerate(session.splitlines()):
        if SUMMARY_MARKER not in line:
            continue
        if "summary failed" in line:
            continue
        parsed = parse_summary_line(line)
        missing = [key for key in REQUIRED_SUMMARY_KEYS
                   if key not in parsed]
        if missing:
            missing_keys = missing
            continue
        found = (parsed, anchor_line + offset + 1)

    if found is not None:
        summary, summary_line = found
        return summary, summary_line, anchor_line, anchor_count

    raise ValueError(
        "no valid lazy probe summary after agent session anchor line "
        f"{anchor_line}; missing keys: {', '.join(missing_keys)}")


def last_summary(text: str) -> dict[str, int | str]:
    return find_summary(text)[0]


def last_session(
        text: str, anchor: str = SESSION_ANCHOR,
) -> tuple[str, bool, int | None, int]:
    """Return (slice, anchor_found, anchor_line, anchor_count).

    The slice starts at the last anchor line. When the anchor is absent the
    whole text is returned with anchor_found=False so strict mode can fail.
    """
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines) if anchor in line]
    if not anchors:
        return text, False, None, 0
    index = anchors[-1]
    return "".join(lines[index:]), True, index + 1, len(anchors)


def require_int(summary: dict[str, int | str], key: str) -> int:
    if key not in summary:
        raise ValueError(f"summary missing required key: {key}")
    value = summary[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"summary key {key} must be an integer, got {value!r}")
    return value


def count_texture_errors(text: str) -> dict[str, int]:
    return {name: text.count(name) for name in TEXTURE_ERRORS}


def summarize_gpu(
        rows: list[tuple[float, float | None, float | None]]) -> dict:
    dedicated = [r[1] for r in rows if r[1] is not None and math.isfinite(r[1])]
    shared = [r[2] for r in rows if r[2] is not None and math.isfinite(r[2])]

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
        path: Path,
) -> tuple[list[tuple[float, float | None, float | None]], int]:
    """Read GPU samples; return (rows, bad_rows).

    BOM and whitespace around headers are tolerated. A non-numeric/non-finite
    timestamp skips the row and counts as bad. A non-empty invalid memory
    value becomes None and counts as bad; an empty value is simply None.
    """
    rows: list[tuple[float, float | None, float | None]] = []
    bad_rows = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is not None:
            reader.fieldnames = [
                name.strip() if isinstance(name, str) else name
                for name in reader.fieldnames]
        for row in reader:
            raw_ts = row.get("timestamp")
            try:
                ts = float((raw_ts or "").strip())
            except (TypeError, ValueError):
                bad_rows += 1
                continue
            if not math.isfinite(ts):
                bad_rows += 1
                continue

            def number(name: str) -> float | None:
                nonlocal bad_rows
                raw = row.get(name)
                if raw is None or not raw.strip():
                    return None
                try:
                    value = float(raw.strip())
                except (TypeError, ValueError):
                    bad_rows += 1
                    return None
                if not math.isfinite(value):
                    bad_rows += 1
                    return None
                return value

            rows.append((ts, number("dedicated_mb"), number("shared_mb")))
    return rows, bad_rows


def build_report(
        agent_text: str,
        starsector_text: str,
        gpu_rows: list[tuple[float, float | None, float | None]] | None = None,
) -> dict:
    summary, summary_line, anchor_line, anchor_count = find_summary(agent_text)
    session, anchor_found, session_anchor_line, session_count = last_session(
        starsector_text)
    errors = count_texture_errors(session)
    report = {
        "summary": summary,
        "texture_errors": errors,
        "texture_errors_total": sum(errors.values()),
        "scene_unload": require_int(summary, "sceneUnload"),
        "scene_passes": require_int(summary, "scenePasses"),
        "scene_evictions": require_int(summary, "sceneEvictions"),
        "scene_evict_ms_total": require_int(summary, "sceneEvictMsTotal"),
        "scene_evict_ms_max": require_int(summary, "sceneEvictMsMax"),
        "scene_pending": require_int(summary, "scenePending"),
        "failed_parked": require_int(summary, "failedParked"),
        "summary_line": summary_line,
        "agent_session_anchor_line": anchor_line,
        "agent_session_count": anchor_count,
        "session_anchor_found": anchor_found,
        "session_anchor_line": session_anchor_line,
        "session_count": session_count,
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
    parser.add_argument(
        "--require-scene", action="store_true",
        help="fail unless sceneEvictions > 0; implies --strict")
    parser.add_argument(
        "--strict", action="store_true",
        help="fail on texture errors, failedParked, or missing session anchor")
    args = parser.parse_args(argv)
    strict = args.strict or args.require_scene

    try:
        agent_text = args.agent_log.read_text(
            encoding="utf-8", errors="replace")
        starsector_text = args.starsector_log.read_text(
            encoding="utf-8", errors="replace")
        gpu_rows = None
        gpu_bad_rows = 0
        if args.gpu_csv is not None:
            gpu_rows, gpu_bad_rows = read_gpu_csv(args.gpu_csv)
            if not gpu_rows:
                print("m28_scene_gate: no valid GPU samples in "
                      f"{args.gpu_csv} (bad_rows={gpu_bad_rows})",
                      file=sys.stderr)
                return 2
        report = build_report(agent_text, starsector_text, gpu_rows)
        if gpu_bad_rows > 0:
            report["gpu_bad_rows"] = gpu_bad_rows
        text = json.dumps(
            report, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError) as exc:
        print(f"m28_scene_gate: {exc}", file=sys.stderr)
        return 1

    print(text)
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"m28_scene_gate: {exc}", file=sys.stderr)
            return 1

    if strict:
        if not report["session_anchor_found"]:
            print("m28_scene_gate: no Fast Rendering session anchor",
                  file=sys.stderr)
            return 1
        if report["texture_errors_total"] > 0:
            print("m28_scene_gate: texture errors="
                  f"{report['texture_errors_total']}", file=sys.stderr)
            return 1
        if report["failed_parked"] > 0:
            print(f"m28_scene_gate: failedParked={report['failed_parked']}",
                  file=sys.stderr)
            return 1
        if args.require_scene and report["scene_evictions"] <= 0:
            print("m28_scene_gate: require-scene but sceneEvictions=0",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
