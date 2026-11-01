#!/usr/bin/env python3
"""Interleaved control/treatment menu A/B for M2.6 DDS lazy textures.

Control: -Dhypernova.textures.lazy=false
Treatment: -Dhypernova.textures.lazy=true -Dhypernova.textures.lazy.dds=true
Optional: --eviction / --selftest add the corresponding -D flags.

Every round runs through tools/smoke_run.py (launchDirect -> menu anchor ->
linger -> forced exit) and archives that session's log slice. Lazy counters
come from the last "lazy probe: summary" line of the last agent session.
Battle/save/manual visual are explicitly out of scope for this tool.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from smoke_run import PROFILES, free_physical_mb  # noqa: E402

SESSION_ANCHOR = b"Fast Rendering: v0.9."
SUMMARY = "lazy probe: summary "
PAIR_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")
SMOKE_TIMEOUT_S = 900
MIN_FREE_MB = 12 * 1024


def stats_from_text(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    out = {}
    for line in lines[start:]:
        pos = line.find(SUMMARY)
        if pos < 0:
            continue
        out = {}
        for key, value in PAIR_RE.findall(line[pos + len(SUMMARY):]):
            try:
                out[key] = int(value)
            except ValueError:
                out[key] = value
    return out


def _flags(lazy: bool, dds: bool, eviction: bool, selftest: bool) -> list[str]:
    args = ["-Dhypernova.textures.lazy=" + ("true" if lazy else "false")]
    if lazy:
        args.append("-Dhypernova.textures.lazy.dds=" + ("true" if dds else "false"))
        if eviction:
            args.append("-Dhypernova.textures.lazy.eviction=true")
        if selftest:
            args.append("-Dhypernova.textures.lazy.selftest=true")
    return args


def run_round(profile: str, lazy: bool, dds: bool, eviction: bool,
              selftest: bool, out: Path, wait: float, linger: float) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", str(TOOLS / "smoke_run.py"),
           "--profile", profile, "--rounds", "1", "--wait-menu", str(wait),
           "--linger", str(linger), "--json-out", str(out.resolve())]
    for arg in _flags(lazy, dds, eviction, selftest):
        cmd.append("--jvm-arg=" + arg)
    proc = subprocess.run(cmd, check=False, cwd=str(ROOT), timeout=SMOKE_TIMEOUT_S)
    try:
        row = json.loads(out.read_text(encoding="utf-8"))[0]
    except Exception as exc:
        row = {"ok": False, "reason": f"json: {exc}"}
    row["returncode"] = proc.returncode
    if proc.returncode != 0:
        row["ok"] = False
    return row


def archive_round(profile: str, tag: str, index: int, out_dir: Path) -> dict:
    result = {"log": None, "failed": 0, "verify": 0, "class_errors": 0,
              "async_errors": 0, "corrupted": 0}
    game = ROOT / PROFILES[profile]["game"]
    log = game / "starsector-core" / "starsector.log"
    if not log.is_file():
        return result
    data = log.read_bytes()
    idx = data.rfind(SESSION_ANCHOR)
    session = data[idx:] if idx >= 0 else data
    dst = out_dir / f"ab-{tag}{index}.log"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(session)
    result["log"] = str(dst)
    result["failed"] = session.count(b"Failed to load texture")
    result["verify"] = session.count(b"VerifyError")
    result["class_errors"] = session.count(b"ClassFormatError")
    result["async_errors"] = session.count(b"AsyncException")
    result["corrupted"] = session.count(b"isStateCorrupted")
    return result


def median(values):
    values = sorted(v for v in values if v is not None)
    n = len(values)
    if not n:
        return None
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="miko-lite")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--wait-menu", type=float, default=300)
    ap.add_argument("--linger", type=float, default=8)
    ap.add_argument("--agent-log", default="")
    ap.add_argument("--log-dir", default="build/m26/logs")
    ap.add_argument("--eviction", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dds", action="store_true", default=True)
    ap.add_argument("--no-dds", dest="dds", action="store_false")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    free_start = free_physical_mb()
    print(f"[ab] free physical before A/B: {free_start} MB")
    if free_start is not None and free_start < MIN_FREE_MB:
        print(f"[ab] WARNING: free physical memory < {MIN_FREE_MB} MB; A/B may be noisy",
              flush=True)

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
        c = run_round(args.profile, False, False, False, False,
                      Path(f"build/m26/ab-c{i}.json"), args.wait_menu, args.linger)
        c.update(archive_round(args.profile, "c", i, log_dir))
        print(f"[ab] {label} treatment", flush=True)
        t = run_round(args.profile, True, args.dds, args.eviction, args.selftest,
                      Path(f"build/m26/ab-t{i}.json"), args.wait_menu, args.linger)
        t.update(archive_round(args.profile, "t", i, log_dir))
        stats = stats_from_text(agent.read_text(encoding="utf-8", errors="replace")) \
            if agent.is_file() else {}
        rows.append({"control": c, "treatment": t, "lazy": stats})
        print(f"[ab] {label}: control={c.get('menu_s')}s treatment={t.get('menu_s')}s "
              f"err={c['failed']}/{c['verify']}/{c['class_errors']}|"
              f"{t['failed']}/{t['verify']}/{t['class_errors']} lazy={stats}", flush=True)

    c_med = median([r["control"].get("menu_s") for r in rows])
    t_med = median([r["treatment"].get("menu_s") for r in rows])
    lazy_median = {}
    if rows and all(r["lazy"] for r in rows):
        keys = set().union(*(r["lazy"].keys() for r in rows))
        for key in sorted(keys):
            values = [r["lazy"].get(key) for r in rows
                      if isinstance(r["lazy"].get(key), int)]
            lazy_median[key] = median(values)
    pairs = [round(r["treatment"]["menu_s"] - r["control"]["menu_s"], 1)
             for r in rows
             if r["control"].get("menu_s") is not None
             and r["treatment"].get("menu_s") is not None]
    gates = {
        "all_rounds_ok": all(r["control"].get("ok") and r["treatment"].get("ok")
                             for r in rows),
        "no_texture_errors": all(
            (r[side]["failed"] == 0 and r[side]["verify"] == 0
             and r[side]["class_errors"] == 0 and r[side]["async_errors"] == 0
             and r[side]["corrupted"] == 0)
            for r in rows for side in ("control", "treatment")),
        "treatment_failed_zero": all(r["lazy"].get("failed", 0) == 0 for r in rows),
        "treatment_disabled_zero": all(r["lazy"].get("disabled", 0) == 0 for r in rows),
        "treatment_dim_mismatch_zero": all(
            r["lazy"].get("dimMismatch", 0) == 0 for r in rows),
        "treatment_dds_disabled_zero": all(
            r["lazy"].get("ddsDisabled", 0) == 0 for r in rows),
        "treatment_dds_hit_positive": (lazy_median.get("ddsHit") or 0) > 0,
        "selftest_ok": (not args.selftest) or all(
            r["lazy"].get("selftest") == 1 for r in rows),
    }
    result = {
        "profile": args.profile,
        "rounds": args.rounds,
        "flags": {"dds": args.dds, "eviction": args.eviction, "selftest": args.selftest},
        "free_mb_start": None if free_start is None else round(free_start, 1),
        "rows": rows,
        "control_median": c_med,
        "treatment_median": t_med,
        "delta_s": None if c_med is None or t_med is None else round(t_med - c_med, 2),
        "paired_deltas_s": pairs,
        "paired_median_s": median(pairs),
        "lazy_median": lazy_median or None,
        "gates": gates,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"},
                     ensure_ascii=False, indent=2))
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
