#!/usr/bin/env python3
"""Interleaved control/treatment A/B for M2.5 lazy textures (same boot, warm).

Every round runs control (lazy=false) then treatment (lazy=true) through
tools/smoke_run.py, archives that round's starsector.log, and aggregates the
median menu time, working set, GPU memory and free physical memory. Lazy
counters are parsed from the last agent-log session (after the last premain).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from smoke_run import PROFILES, free_physical_mb  # noqa: E402

# Task 2's fail-open fix added pending/drained between deferred and failed;
# the brief's regex assumed they were adjacent, so tolerate extra fields.
LAZY_RE = re.compile(
    r"lazy probe: summary .*?skipped=(\d+) proxies=(\d+) materialized=(\d+) "
    r"deferred=(\d+).*?failed=(\d+) disabled=(\d+)")
LAZY_KEYS = ("skipped", "proxies", "materialized", "deferred", "failed", "disabled")
SESSION_ANCHOR = b"Fast Rendering: v0.9."
SMOKE_TIMEOUT_S = 600
MIN_FREE_MB = 12 * 1024


def lazy_stats_from_text(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    out = {}
    for line in lines[start:]:
        m = LAZY_RE.search(line)
        if m:
            out = {key: int(m.group(i + 1)) for i, key in enumerate(LAZY_KEYS)}
    return out


def run_round(profile: str, lazy: bool, out: str, wait: float) -> dict:
    arg = "-Dhypernova.textures.lazy=" + ("true" if lazy else "false")
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", str(TOOLS / "smoke_run.py"),
           "--profile", profile, "--rounds", "1", "--wait-menu", str(wait),
           "--jvm-arg=" + arg, "--json-out", str(out_path.resolve())]
    subprocess.run(cmd, check=True, cwd=str(ROOT), timeout=SMOKE_TIMEOUT_S)
    return json.loads(out_path.read_text(encoding="utf-8"))[0]


def archive_round(profile: str, tag: str, index: int, out_dir: Path) -> dict:
    """Copy this round's starsector.log and count errors in the last session.

    The log is cumulative across launches, so slicing at the last FR session
    anchor is what makes the counts belong to this round.
    """
    result = {"log": None, "failed": 0, "verify": 0, "class_errors": 0}
    game = ROOT / PROFILES[profile]["game"]
    log = game / "starsector-core" / "starsector.log"
    if not log.is_file():
        return result
    dst = Path(out_dir) / f"ab-{tag}{index}.log"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(log, dst)
    result["log"] = str(dst)
    data = dst.read_bytes()
    idx = data.rfind(SESSION_ANCHOR)
    session = data[idx:] if idx >= 0 else data
    result["failed"] = session.count(b"Failed to load texture")
    result["verify"] = session.count(b"VerifyError")
    result["class_errors"] = session.count(b"ClassFormatError")
    return result


def median(values):
    values = sorted(values)
    n = len(values)
    if not n:
        return None
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def _median_field(rows: list[dict], side: str, key: str):
    values = [r[side].get(key) for r in rows if r[side].get(key) is not None]
    value = median(values)
    return None if value is None else round(value, 1)


def _format_mb(value) -> str:
    return "?" if value is None else f"{value:.0f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="miko-lite")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--wait-menu", type=float, default=300)
    ap.add_argument("--agent-log", default="")
    ap.add_argument("--log-dir", default="build/m25/logs")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    free_start = free_physical_mb()
    print(f"[ab] free physical before A/B: {_format_mb(free_start)} MB")
    if free_start is not None and free_start < MIN_FREE_MB:
        print(f"[ab] WARNING: free physical memory < {MIN_FREE_MB} MB; "
              f"A/B may be noisy", flush=True)

    agent = Path(args.agent_log) if args.agent_log else (
        ROOT / "Starsector-098-260mods/saves/hypernova/scripts-agent.log")
    if not agent.is_absolute():
        agent = ROOT / agent
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir

    rows = []
    for i in range(1, args.rounds + 1):
        label = f"#{i}/{args.rounds}"
        print(f"\n[ab] {label} control", flush=True)
        c = run_round(args.profile, False, f"build/m25/ab-c{i}.json", args.wait_menu)
        c.update(archive_round(args.profile, "c", i, log_dir))
        print(f"[ab] {label} treatment", flush=True)
        t = run_round(args.profile, True, f"build/m25/ab-t{i}.json", args.wait_menu)
        t.update(archive_round(args.profile, "t", i, log_dir))
        stats = lazy_stats_from_text(agent.read_text(encoding="utf-8", errors="replace")) \
            if agent.is_file() else {}
        rows.append({"control": c, "treatment": t, "lazy": stats})
        print(f"[ab] {label}: control={c['menu_s']}s treatment={t['menu_s']}s "
              f"ws={c.get('ws_menu_mb')}/{t.get('ws_menu_mb')} "
              f"gpu={c.get('gpu_menu_mb')}/{t.get('gpu_menu_mb')} "
              f"free={c.get('free_mb_menu')}/{t.get('free_mb_menu')} "
              f"err={c['failed']}/{c['verify']}/{c['class_errors']}|"
              f"{t['failed']}/{t['verify']}/{t['class_errors']} lazy={stats}",
              flush=True)

    c_med = median([r["control"]["menu_s"] for r in rows])
    t_med = median([r["treatment"]["menu_s"] for r in rows])
    lazy_median = {}
    if rows and all(r["lazy"] for r in rows):
        lazy_median = {key: median([r["lazy"][key] for r in rows]) for key in LAZY_KEYS}
    result = {
        "profile": args.profile,
        "rounds": args.rounds,
        "free_mb_start": None if free_start is None else round(free_start, 1),
        "rows": rows,
        "control_median": c_med,
        "treatment_median": t_med,
        "delta_s": None if c_med is None or t_med is None
        else round(t_med - c_med, 2),
        "ws_control_median": _median_field(rows, "control", "ws_menu_mb"),
        "ws_treatment_median": _median_field(rows, "treatment", "ws_menu_mb"),
        "gpu_control_median": _median_field(rows, "control", "gpu_menu_mb"),
        "gpu_treatment_median": _median_field(rows, "treatment", "gpu_menu_mb"),
        "free_control_median": _median_field(rows, "control", "free_mb_menu"),
        "free_treatment_median": _median_field(rows, "treatment", "free_mb_menu"),
        "lazy_median": lazy_median or None,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"},
                     ensure_ascii=False, indent=2))
    ok = all(r["control"].get("ok") and r["treatment"].get("ok") for r in rows)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
