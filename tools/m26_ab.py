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
from smoke_run import PROFILES, free_physical_mb, kill_pid, wait_dead  # noqa: E402

SESSION_ANCHOR = b"Fast Rendering: v0.9."
SUMMARY = "lazy probe: summary "
REQUIRED_SUMMARY_KEYS = (
    "queue", "failed", "disabled", "dimMismatch", "main",
    "ddsHit", "ddsDisabled",
)
PAIR_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")
SMOKE_TIMEOUT_S = 900
MIN_FREE_MB = 12 * 1024


def read_since(path: Path, offset: int) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def stats_from_text(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    out = {}
    for line in lines[start:]:
        if "summary failed" in line:
            continue
        pos = line.find(SUMMARY)
        if pos < 0:
            continue
        parsed = {}
        for key, value in PAIR_RE.findall(line[pos + len(SUMMARY):]):
            try:
                parsed[key] = int(value)
            except ValueError:
                parsed[key] = value
        # 只有包含门禁所需键的完整 summary 才可覆盖上一条完整 summary；
        # 强杀留下的 torn 行不能把有效数据清空。
        if all(key in parsed for key in REQUIRED_SUMMARY_KEYS):
            out = parsed
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


def cleanup_timed_out_game(pid_file: Path) -> bool:
    """只杀 smoke_run 记录的这一个游戏 PID，避免残留进程污染下一轮。"""
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    kill_pid(pid, True)
    dead = wait_dead(pid, 20)
    if dead:
        try:
            pid_file.unlink()
        except OSError:
            pass
    return dead


def run_round(profile: str, lazy: bool, dds: bool, eviction: bool,
              selftest: bool, out: Path, wait: float, linger: float) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    pid_file = out.with_name(out.name + ".pid")
    cmd = [sys.executable, "-I", str(TOOLS / "smoke_run.py"),
           "--profile", profile, "--rounds", "1", "--wait-menu", str(wait),
           "--linger", str(linger), "--json-out", str(out.resolve()),
           "--pid-file", str(pid_file.resolve())]
    for arg in _flags(lazy, dds, eviction, selftest):
        cmd.append("--jvm-arg=" + arg)
    try:
        pid_file.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        proc = subprocess.run(cmd, check=False, cwd=str(ROOT), timeout=SMOKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "returncode": None,
                "game_cleanup": cleanup_timed_out_game(pid_file)}
    try:
        row = json.loads(out.read_text(encoding="utf-8"))[0]
    except Exception as exc:
        row = {"ok": False, "reason": f"json: {exc}"}
    row["returncode"] = proc.returncode
    if proc.returncode != 0 or not row.get("ok", False):
        row["ok"] = False
        row["game_cleanup"] = cleanup_timed_out_game(pid_file)
    return row


def archive_round(profile: str, tag: str, index: int, out_dir: Path) -> dict:
    result = {"log": None, "log_present": False, "failed": 0, "verify": 0,
              "class_errors": 0, "async_errors": 0, "corrupted": 0}
    game = ROOT / PROFILES[profile]["game"]
    log = game / "starsector-core" / "starsector.log"
    if not log.is_file():
        return result
    data = log.read_bytes()
    idx = data.rfind(SESSION_ANCHOR)
    if idx < 0:
        return result
    session = data[idx:]
    result["log_present"] = True
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
    ap.add_argument("--counterbalance", action="store_true")
    ap.add_argument("--dds", action="store_true", default=True)
    ap.add_argument("--no-dds", dest="dds", action="store_false")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.rounds < 1:
        ap.error("--rounds must be >= 1")

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
        order = [("control", False), ("treatment", True)]
        if args.counterbalance and i % 2 == 0:
            order.reverse()
        side_rows = {}
        treatment_lazy: dict = {}
        for side, treatment in order:
            label = f"#{i}/{args.rounds} {side}"
            print(f"\n[ab] {label}", flush=True)
            round_dir = Path(args.out).parent
            out_path = round_dir / (
                f"{Path(args.out).stem}-{'t' if treatment else 'c'}{i}.json")
            agent_offset = (agent.stat().st_size
                            if treatment and agent.is_file() else 0)
            row = run_round(args.profile, treatment,
                            args.dds if treatment else False,
                            args.eviction if treatment else False,
                            args.selftest if treatment else False,
                            out_path, args.wait_menu, args.linger)
            row.update(archive_round(args.profile,
                                     "t" if treatment else "c", i, log_dir))
            if treatment:
                treatment_lazy = stats_from_text(read_since(agent, agent_offset))
                row["lazy_captured"] = bool(treatment_lazy)
            side_rows[side] = row
            print(f"[ab] {label}: menu={row.get('menu_s')}s "
                  f"err={row['failed']}/{row['verify']}/{row['class_errors']}",
                  flush=True)
        c = side_rows["control"]
        t = side_rows["treatment"]
        rows.append({"control": c, "treatment": t, "lazy": treatment_lazy,
                     "order": [side for side, _ in order]})
        print(f"[ab] #{i}: control={c.get('menu_s')}s treatment={t.get('menu_s')}s "
              f"lazy={treatment_lazy}", flush=True)

    c_med = median([r["control"].get("menu_s") for r in rows])
    t_med = median([r["treatment"].get("menu_s") for r in rows])
    lazy_rows = [r["lazy"] for r in rows if r["lazy"]]
    lazy_median = {}
    if lazy_rows:
        keys = set().union(*(r.keys() for r in lazy_rows))
        for key in sorted(keys):
            values = [r.get(key) for r in lazy_rows
                      if isinstance(r.get(key), int)]
            lazy_median[key] = median(values)
    pairs = [round(r["treatment"]["menu_s"] - r["control"]["menu_s"], 1)
             for r in rows
             if r["control"].get("menu_s") is not None
             and r["treatment"].get("menu_s") is not None]
    gates = {
        "all_rounds_ok": all(r["control"].get("ok") and r["treatment"].get("ok")
                             for r in rows),
        "treatment_stats_present": bool(rows) and all(
            bool(r["lazy"]) for r in rows),
        "logs_present": all(
            r[side].get("log_present", False)
            for r in rows for side in ("control", "treatment")),
        "no_texture_errors": all(
            r[side].get("log_present", False)
            and r[side]["failed"] == 0 and r[side]["verify"] == 0
            and r[side]["class_errors"] == 0 and r[side]["async_errors"] == 0
            and r[side]["corrupted"] == 0
            for r in rows for side in ("control", "treatment")),
        "treatment_failed_zero": all(r["lazy"].get("failed", 0) == 0 for r in rows),
        "treatment_disabled_zero": all(r["lazy"].get("disabled", 0) == 0 for r in rows),
        "treatment_dim_mismatch_zero": all(
            r["lazy"].get("dimMismatch", 0) == 0 for r in rows),
        "treatment_dds_disabled_zero": all(
            r["lazy"].get("ddsDisabled", 0) == 0 for r in rows),
        "treatment_dds_hit_positive": (not args.dds)
            or (lazy_median.get("ddsHit") or 0) > 0,
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
        "lazy_rows": len(lazy_rows),
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
