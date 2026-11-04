#!/usr/bin/env python3
"""One serialized B-debug launch: lock -> smoke_run.one_round -> stage log -> unlock.

Does not modify tools/.  Uses tools/smoke_run.py as a library.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(r"D:/github/Hypernova-Infinite-Engine")
sys.path.insert(0, str(REPO / "tools"))
import smoke_run  # noqa: E402

LOCK = REPO / "SS098_Hypernova_Compat_AuditTest/evidence/.game-lock"
ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"


def acquire_lock(label: str, timeout_s: float = 1800.0) -> None:
    t0 = time.time()
    while LOCK.exists():
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"game-lock still present after {timeout_s}s")
        print(f"[lock] waiting: {LOCK}", flush=True)
        time.sleep(2.0)
    LOCK.write_text(
        f"b-debug label={label} pid={os.getpid()} at={time.time():.0f}\n",
        encoding="utf-8")
    print(f"[lock] acquired: {label}", flush=True)


def release_lock() -> None:
    try:
        LOCK.unlink()
        print("[lock] released", flush=True)
    except FileNotFoundError:
        pass


def stage_report(game: Path) -> dict:
    """Parse the new starsector.log for stage timestamps and key lines."""
    logp = game / "starsector-core" / "starsector.log"
    out: dict = {"log": str(logp)}
    if not logp.is_file():
        return out
    text = logp.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out["log_bytes"] = logp.stat().st_size
    out["log_lines"] = len(lines)

    def find(needle: str, last: bool = False) -> list[str]:
        hit = [ln for ln in lines if needle in ln]
        return hit[-1:] if last and hit else hit

    def ts(line: str | None) -> int | None:
        if not line:
            return None
        head = line.lstrip().split(" ", 1)[0]
        try:
            return int(head)
        except ValueError:
            return None

    anchor = None
    for ln in lines:
        if ANCHOR in ln:
            anchor = ln
    out["menu_anchor"] = anchor
    out["menu_log_ms"] = ts(anchor)
    first = find("Fast Rendering:")
    out["fr_banner"] = first[0] if first else None
    jv = find("Java version:")
    out["java_version"] = jv[0] if jv else None
    cached = find("Cached ", last=True)
    out["file_cache"] = cached[0] if cached else None
    vopt = find("VOpt Loaded")
    out["vopt"] = vopt[0] if vopt else None
    cif = find("[CIF] 中文输入修复")
    out["cif"] = cif[0] if cif else None
    prep = find("StarsectorPrepatcher 0.18.4")
    out["prepatcher"] = prep[0] if prep else None
    prep_sk = [ln for ln in lines if "skippedPatchesSoFar" in ln]
    out["prepatcher_patches"] = prep_sk[-1] if prep_sk else None
    normals = [ln for ln in lines if "Auto-generated normal map" in ln]
    out["normal_map_count"] = len(normals)
    out["normal_map_first"] = normals[0] if normals else None
    out["normal_map_last"] = normals[-1] if normals else None
    csv = [ln for ln in lines if "Loading CSV data" in ln]
    out["csv_last"] = csv[-1] if csv else None
    errs = []
    for pat in ("OutOfMemoryError", "FATAL", "ERROR lazy: materialize failed",
                "Could not make current context", "NoClassDefFoundError",
                "Exception in thread"):
        hits = [ln for ln in lines if pat in ln]
        if hits:
            errs.append({"pattern": pat, "count": len(hits),
                         "first": hits[0][:400], "last": hits[-1][:400]})
    out["errors"] = errs
    return out


def agent_report(game: Path) -> dict:
    p = game / "saves" / "hypernova" / "scripts-agent.log"
    out: dict = {"log": str(p)}
    if not p.is_file():
        return out
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    probes = [ln for ln in lines if "lazy probe" in ln]
    out["lazy_probe_last"] = probes[-1] if probes else None
    for key, needle in (
            ("premain", "hypernova agent premain"),
            ("file_index", "file index transformer registered"),
            ("lazy", "lazy: transformers registered"),
            ("scripts_cache", "scripts cache transformer registered"),
            ("preload_hit", "scripts cache preloaded:"),
            ("preload_cold", "scripts cache cold:"),
    ):
        hit = [ln for ln in lines if needle in ln]
        out[key] = hit[-1] if hit else None
    return out


class Args:
    wait_menu = 540.0
    linger = 5.0
    start_res = "1707x1067"
    fullscreen = False
    jvm_arg: list[str] = []
    pid_file = ""


def clean_logs(game: Path) -> None:
    core = game / "starsector-core"
    for name in ("starsector.log", "starsector.log.1"):
        try:
            (core / name).unlink()
        except FileNotFoundError:
            pass
    for p in core.glob("gc-miko.log*"):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    for p in (game / "saves/hypernova").glob("scripts-agent.log*"):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--argfile", default="../route-b.vmparams")
    ap.add_argument("--wait-menu", type=float, default=540.0)
    ap.add_argument("--linger", type=float, default=5.0)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--jvm-arg", action="append", default=[])
    ns = ap.parse_args()

    game = Path(ns.root).resolve()
    cfg = {
        "game": str(game),
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": ns.argfile,
        "cwd": "starsector-core",
    }
    args = Args()
    args.wait_menu = ns.wait_menu
    args.linger = ns.linger
    args.jvm_arg = ns.jvm_arg
    args.pid_file = str(Path(ns.json_out).with_suffix(".pid"))

    acquire_lock(ns.label)
    try:
        payloads = []
        for index in range(ns.rounds):
            clean_logs(game)
            label = ns.label if ns.rounds == 1 else f"{ns.label}-{index + 1}"
            print(f"\n########## {label} ({index + 1}/{ns.rounds}) ##########",
                  flush=True)
            row = smoke_run.one_round(cfg, game, args)
            payloads.append({
                "label": label,
                "root": str(game),
                "argfile": ns.argfile,
                "smoke": row,
                "stage": stage_report(game),
                "agent": agent_report(game),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            })
            if index + 1 < ns.rounds:
                time.sleep(3)
        payload = payloads[0] if ns.rounds == 1 else payloads
        Path(ns.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if ns.rounds == 1:
            print(json.dumps({k: payload[k] for k in ("label", "smoke")},
                             ensure_ascii=False, indent=2), flush=True)
        else:
            print(json.dumps([
                {"label": p["label"], "menu_s": p["smoke"].get("menu_s"),
                 "ok": p["smoke"].get("ok")} for p in payloads],
                ensure_ascii=False, indent=2), flush=True)
        return 0 if all(p["smoke"].get("ok") for p in payloads) else 1
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
