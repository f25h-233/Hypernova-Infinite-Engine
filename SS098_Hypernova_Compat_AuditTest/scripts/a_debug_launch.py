#!/usr/bin/env python3
"""Serialized launch helper for Route A debugging.

- Respects evidence/.game-lock (creates it for the duration of the launch).
- Starts the launcher JVM by PID, discovers the MixinLib game-JVM PID from
  mixinlib.log, waits for the main-menu anchor, then kills only those PIDs.
- Never uses `taskkill /IM java.exe`.
- Archives the relevant logs into the evidence directory.

This helper is intentionally outside tools/ and tests/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MENU_ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"
GAME_PID_RE = re.compile(r"Handoff - game JVM started pid=(\d+)")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def pid_alive(pid: int) -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
        )
        return str(pid) in (r.stdout or "")
    except Exception:
        return False


def kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=20)
    except Exception:
        pass


def read_tail(path: Path, limit: int = 40) -> list[str]:
    try:
        size = path.stat().st_size
        start = max(0, size - 4 * 1024 * 1024)
        with path.open("rb") as f:
            f.seek(start)
            text = f.read().decode("utf-8", errors="replace")
        lines = text.splitlines()
        return [ln[:400] for ln in lines[-limit:]]
    except Exception:
        return []


def tail_text(path: Path, max_bytes: int = 4 * 1024 * 1024) -> str:
    try:
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        with path.open("rb") as f:
            f.seek(start)
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def count_occurrences(path: Path, needle: str) -> int | None:
    try:
        return path.read_bytes().count(needle.encode("utf-8"))
    except Exception:
        return None


def hypernova_metrics(path: Path) -> dict[str, object]:
    text = tail_text(path, 4 * 1024 * 1024)
    out: dict[str, object] = {}

    def last_int(pattern: str, group: int = 1) -> int | None:
        hits = re.findall(pattern, text)
        return int(hits[-1]) if hits else None

    out["finds"] = last_int(r"find span:.*?finds=(\d+), hits=\d+, misses=\d+")
    out["hits"] = last_int(r"find span:.*?finds=\d+, hits=(\d+), misses=\d+")
    out["misses"] = last_int(r"find span:.*?finds=\d+, hits=\d+, misses=(\d+)")
    out["breakdown_total"] = last_int(
        r"miss breakdown: total=(\d+), sourceless=\d+, sourced=\d+")
    out["breakdown_sourceless"] = last_int(
        r"miss breakdown: total=\d+, sourceless=(\d+), sourced=\d+")
    out["breakdown_sourced"] = last_int(
        r"miss breakdown: total=\d+, sourceless=\d+, sourced=(\d+)")
    out["cache_preloaded"] = last_int(
        r"scripts cache (?:preloaded|cold):.*?entries=(\d+)")
    out["cache_cold_preloaded"] = last_int(
        r"scripts cache cold:.*?preloaded=(\d+)")
    out["cache_written_entries"] = last_int(
        r"scripts cache written:.*?entries=(\d+)")
    out["map_size"] = last_int(r"shutdown: map\.size=(\d+)")
    keys = re.findall(r"cache key ready \(background\): ([0-9a-f]+)", text)
    out["cache_key"] = keys[-1] if keys else None
    return out


def snapshot(root: Path, core: Path, started: float, menu: bool) -> dict[str, object]:
    log = core / "starsector.log"
    snap: dict[str, object] = {
        "t_s": round(time.time() - started, 1),
        "stage": last_stage(core),
        "menu": menu,
        "log_bytes": log.stat().st_size if log.is_file() else 0,
        "compiling_lines": count_occurrences(log, "Compiling script"),
        "rules": count_occurrences(log, "Loading rule:"),
        "json_loads": count_occurrences(log, "Loading JSON"),
        "images": count_occurrences(log, "Loading image"),
        "hypernova": hypernova_metrics(root / "saves" / "hypernova" / "scripts-agent.log"),
    }
    tail = read_tail(log, 1)
    snap["last_log"] = tail[-1] if tail else None
    return snap


def archive(root: Path, evidence: Path, label: str) -> list[str]:
    out = evidence / label
    out.mkdir(parents=True, exist_ok=True)
    core = root / "starsector-core"
    saves = root / "saves"
    candidates = [
        core / "starsector.log",
        core / "starsector.log.1",
        core / "mixinlib.log",
        core / "mixinlib-game-stdio.log",
        core / "mixinlib-launcher-stdio.log",
        core / "mixinfr-frweave.log",
        core / "mixinfr-ime-fix.log",
        core / "mixinfr-fonthd.log",
        core / "adebug-agent.log",
        saves / "hypernova" / "scripts-agent.log",
        saves / "hypernova" / "telemetry.jsonl",
    ]
    copied: list[str] = []
    for src in candidates:
        if not src.is_file():
            continue
        dst = out / src.name
        try:
            shutil.copy2(src, dst)
            copied.append(str(dst))
        except Exception:
            pass
    return copied


def wait_for_lock(lock: Path, max_wait_s: float) -> None:
    deadline = time.time() + max_wait_s
    while lock.exists():
        if time.time() > deadline:
            raise TimeoutError(f"game lock still held after {max_wait_s}s: {lock}")
        print(f"[a-debug] waiting for lock: {lock}", flush=True)
        time.sleep(5)


def acquire_lock(lock: Path) -> int:
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, f"pid={os.getpid()} at={now_iso()}\n".encode())
    return fd


def release_lock(fd: int, lock: Path) -> None:
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        lock.unlink()
    except Exception:
        pass


def last_stage(core: Path) -> str:
    tail = read_tail(core / "starsector.log", 12)
    for line in reversed(tail):
        if "Loading rule:" in line:
            return "rules"
        if "Compiling script" in line:
            return "scripts"
        if "Loading image" in line:
            return "textures"
        if "Playing music with id" in line:
            return "menu"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--vmparams", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--evidence", required=True, type=Path)
    ap.add_argument("--lock", required=True, type=Path)
    ap.add_argument("--start-res", default="1707x1067")
    ap.add_argument("--jcmd", type=Path, default=None,
                    help="optional jcmd.exe for a thread dump at menu")
    ap.add_argument("--poll-interval", type=float, default=100.0,
                    help="seconds between timeline snapshots")
    ap.add_argument("--timeline-out", type=Path, default=None,
                    help="JSONL timeline path (one snapshot per poll interval)")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    root = args.root.resolve()
    core = root / "starsector-core"
    java = root / "jre" / "bin" / "java.exe"
    if not java.is_file():
        print(f"missing java: {java}", file=sys.stderr)
        return 2
    if not args.vmparams.is_file():
        print(f"missing vmparams: {args.vmparams}", file=sys.stderr)
        return 2

    args.evidence.mkdir(parents=True, exist_ok=True)
    wait_for_lock(args.lock, max_wait_s=1800)
    fd = acquire_lock(args.lock)
    started = time.time()
    proc = None
    game_pid = 0
    result: dict[str, object] = {
        "label": args.label,
        "root": str(root),
        "vmparams": str(args.vmparams),
        "started_at": now_iso(),
        "timeout_s": args.timeout,
        "menu": False,
        "seconds_to_menu": None,
        "exit_early": False,
        "stage_at_end": None,
        "fatal": False,
        "oom": False,
        "game_pid": None,
        "launcher_pid": None,
        "error": None,
    }
    try:
        # Keep a copy of the previous starsector.log so the new run's anchor
        # cannot be satisfied by an old line.
        old_log = core / "starsector.log"
        if old_log.is_file():
            backup = core / f"starsector.log.pre-{args.label}"
            try:
                os.replace(old_log, backup)
            except Exception:
                pass
        for stale in (core / "mixinlib.log",):
            try:
                if stale.is_file():
                    os.replace(stale, core / f"{stale.name}.pre-{args.label}")
            except Exception:
                pass

        cmd = [
            str(java),
            "-DlaunchDirect=true",
            f"-DstartRes={args.start_res}",
            "-DstartFS=false",
            "-DstartSound=true",
            f"@{args.vmparams}",
        ]
        stdout_path = args.evidence / f"{args.label}.stdio.log"
        stdout_f = stdout_path.open("wb")
        env = os.environ.copy()
        proc = subprocess.Popen(cmd, cwd=str(core), stdout=stdout_f,
                                stderr=subprocess.STDOUT, env=env)
        result["launcher_pid"] = proc.pid
        print(f"[a-debug] launched launcher pid={proc.pid} label={args.label}", flush=True)

        deadline = started + args.timeout
        timeline_f = None
        if args.timeline_out is not None:
            args.timeline_out.parent.mkdir(parents=True, exist_ok=True)
            timeline_f = args.timeline_out.open("a", encoding="utf-8")
            result["timeline"] = str(args.timeline_out)
        next_poll = started
        anchor_seen_at = None
        while time.time() < deadline:
            time.sleep(2.0)
            now = time.time()
            if timeline_f is not None and now >= next_poll:
                snap = snapshot(root, core, started, False)
                timeline_f.write(json.dumps(snap, ensure_ascii=False) + "\n")
                timeline_f.flush()
                hn = snap.get("hypernova") or {}
                print(
                    f"[a-debug] t={snap['t_s']}s stage={snap['stage']} "
                    f"compiling={snap['compiling_lines']} rules={snap['rules']} "
                    f"json={snap['json_loads']} "
                    f"hn_finds={hn.get('finds')} hn_misses={hn.get('misses')} "
                    f"hn_sourced={hn.get('breakdown_sourced')}", flush=True)
                next_poll = now + args.poll_interval
            # Discover the MixinLib game JVM pid.
            if not game_pid:
                try:
                    text = (core / "mixinlib.log").read_text(
                        encoding="utf-8", errors="replace")
                    m = GAME_PID_RE.search(text)
                    if m:
                        game_pid = int(m.group(1))
                        result["game_pid"] = game_pid
                        print(f"[a-debug] game pid={game_pid}", flush=True)
                except Exception:
                    pass
            log_path = core / "starsector.log"
            text = tail_text(log_path)
            if MENU_ANCHOR in text:
                anchor_seen_at = time.time()
                if timeline_f is not None:
                    snap = snapshot(root, core, started, True)
                    timeline_f.write(json.dumps(snap, ensure_ascii=False) + "\n")
                    timeline_f.flush()
                break
            # Early exit: neither launcher nor game alive.
            launcher_alive = proc.poll() is None
            game_alive = pid_alive(game_pid) if game_pid else False
            if not launcher_alive and not game_alive:
                result["exit_early"] = True
                if timeline_f is not None:
                    snap = snapshot(root, core, started, False)
                    timeline_f.write(json.dumps(snap, ensure_ascii=False) + "\n")
                    timeline_f.flush()
                break

        if timeline_f is not None:
            if anchor_seen_at is None and not result.get("exit_early"):
                snap = snapshot(root, core, started, False)
                timeline_f.write(json.dumps(snap, ensure_ascii=False) + "\n")
                timeline_f.flush()
            timeline_f.close()

        if anchor_seen_at is not None:
            result["menu"] = True
            result["seconds_to_menu"] = round(anchor_seen_at - started, 1)
            print(f"[a-debug] MENU in {result['seconds_to_menu']}s", flush=True)
            time.sleep(3)
            if args.jcmd is not None and game_pid and args.jcmd.is_file():
                try:
                    dump = subprocess.run(
                        [str(args.jcmd), str(game_pid), "Thread.print"],
                        capture_output=True, text=True, timeout=60)
                    out = args.evidence / f"{args.label}.threads.txt"
                    out.write_text(dump.stdout + "\n---STDERR---\n" + dump.stderr,
                                   encoding="utf-8", errors="replace")
                    result["thread_dump"] = str(out)
                    print(f"[a-debug] thread dump -> {out}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    result["thread_dump_error"] = f"{type(exc).__name__}: {exc}"
        else:
            result["stage_at_end"] = last_stage(core)
            print(f"[a-debug] timeout/exit at stage={result['stage_at_end']}",
                  flush=True)

        # Classify fatal/OOM from the fresh log.
        try:
            text = (core / "starsector.log").read_text(
                encoding="utf-8", errors="replace")
            result["fatal"] = ("Fatal" in text or "FATAL" in text)
            result["oom"] = ("OutOfMemoryError" in text
                             or "Direct buffer memory" in text)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[a-debug] error: {result['error']}", file=sys.stderr, flush=True)
    finally:
        # Kill the game JVM first, then the launcher JVM, strictly by PID.
        if game_pid:
            kill_pid(game_pid)
        if proc is not None and pid_alive(proc.pid):
            kill_pid(proc.pid)
        time.sleep(1)
        release_lock(fd, args.lock)
        result["finished_at"] = now_iso()
        result["elapsed_s"] = round(time.time() - started, 1)
        result["log_tail"] = read_tail(core / "starsector.log", 20)
        result["copied"] = archive(root, args.evidence, args.label)
        if args.json_out is not None:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
