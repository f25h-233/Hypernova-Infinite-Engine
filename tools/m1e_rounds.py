#!/usr/bin/env python3
"""Run M-1e startup rounds and summarize the OS-cache state.

Each round delegates to tools/smoke_run.py so the launch path, menu anchor and
process shutdown stay in one place. This orchestrator adds:

  * an optional standby-list purge (tools/clear_standby.ps1) before a round;
  * a JSON summary with median/min/max for menu time, process read bytes and
    the agent's cache-key time.

`ReadTransferCount` is the objective cache-state evidence: a warm OS cache
means the game reads far less from disk than a cold one. When the standby
purge cannot run (no elevation), `cache_control` stays "none" and the results
must be reported as an observation, not as a controlled cold/warm comparison.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tools" / "smoke_run.py"
PURGE = ROOT / "tools" / "clear_standby.ps1"
KEY_MS = re.compile(r"took (\d+) ms")


def build_smoke_command(profile: str, json_out: Path, jvm_args: list[str],
                        rounds: int = 1) -> list[str]:
    cmd = [sys.executable, "-I", str(SMOKE), "--profile", profile,
           "--rounds", str(rounds), "--json-out", str(json_out)]
    for arg in jvm_args:
        # argparse would treat "-D..." as an option after a bare "--jvm-arg";
        # the --opt=value form passes option-like values through unchanged.
        cmd.append(f"--jvm-arg={arg}")
    return cmd


def purge_standby() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(PURGE)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
    except Exception as e:  # noqa: BLE001 - reported, never fatal
        return False, f"error: {e}"
    out = (r.stdout or r.stderr or "").strip()
    return (r.returncode == 0 and "PURGED" in out), out


def parse_key_ms(line: str) -> int | None:
    m = KEY_MS.search(line or "")
    return int(m.group(1)) if m else None


def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "n": len(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    menus = [r["menu_s"] for r in ok if r.get("menu_s") is not None]
    reads = [r["read_bytes_menu"] for r in ok
             if r.get("read_bytes_menu") is not None]
    keys = []
    for r in ok:
        key = parse_key_ms(r.get("agent", {}).get("key_ready", ""))
        if key is not None:
            keys.append(key)
    return {
        "rounds": len(rows),
        "ok_rounds": len(ok),
        "menu_s": _stats(menus),
        "read_bytes_menu": _stats(reads),
        "key_ms": _stats(keys),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="miko-lite")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--purge", choices=["never", "once", "each"], default="never")
    ap.add_argument("--jvm-arg", action="append", default=[])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    out = (Path(args.json_out) if args.json_out
           else ROOT / "build" / f"m1e-rounds-{args.tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    purge_log: list[str] = []
    cache_control = "none"
    purge_mode = args.purge

    for i in range(1, args.rounds + 1):
        if purge_mode == "each" or (purge_mode == "once" and i == 1):
            ok, msg = purge_standby()
            purge_log.append(f"round {i}: {msg}")
            print(f"[m1e] standby purge: {msg}", flush=True)
            if ok:
                cache_control = "standby-purged"
            else:
                cache_control = "none"
                purge_mode = "never"
        round_json = out.with_name(f"{out.stem}-r{i}.json")
        cmd = build_smoke_command(args.profile, round_json, args.jvm_arg)
        print(f"[m1e] round {i}/{args.rounds}: {' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode != 0:
            print(f"[m1e] smoke exited {r.returncode}", file=sys.stderr)
        if round_json.is_file():
            rows.extend(json.loads(round_json.read_text(encoding="utf-8")))
            round_json.unlink()

    summary = summarize(rows)
    payload = {
        "profile": args.profile,
        "tag": args.tag,
        "cache_control": cache_control,
        "purge_log": purge_log,
        "jvm_args": args.jvm_arg,
        "summary": summary,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cache_control": cache_control, "summary": summary},
                     ensure_ascii=False, indent=2))
    print(f"[m1e] json -> {out}")
    return 0 if summary["ok_rounds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
