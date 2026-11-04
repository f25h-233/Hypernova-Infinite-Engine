#!/usr/bin/env python3
"""M7 isolation run: one serialized Starsector launch with cache/lock protocol.

Groups:
  c1 = FR 0.9.5 + Hypernova + VOpt, Java 28 (jdk-28+13)
  c2 = FR 0.9.5 + Hypernova + VOpt, JRE 17 (bundled)

Phases:
  cold  = clear GraphicsLib/shaderLib normal caches + Hypernova script cache
  warm1 = no cache clearing
  warm2 = no cache clearing

Records menu anchor, Loading rule / Compiling script / Loading image counts,
Hypernova find span, JavaSourceIClassLoader/Janino lines, Fatal/OOM.
Only the launched PID is killed.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\github\Hypernova-Infinite-Engine")
CASE = REPO / "SS098_Hypernova_Compat_AuditTest"
ROOT = CASE / "install" / "optimized-2026.10.15"
CORE = ROOT / "starsector-core"
EVID = CASE / "evidence" / "isolation"
LOCK = CASE / "evidence" / ".game-lock"

JAVA = {
    "c1": REPO / "Starsector-098-260mods" / "jdk-28+13" / "bin" / "java.exe",
    "c2": ROOT / "jre" / "bin" / "java.exe",
}
ARGFILE = {
    "c1": CORE / "m7-isolation-c1.vmparams",
    "c2": CORE / "m7-isolation-c2.vmparams",
}

ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"
LOG_NAMES = ["starsector.log.1", "starsector.log"]
GC_NAMES = ["gc-miko.log", "gc-miko.log.0", "gc-miko.log.1", "gc-miko.log.2"]
AGENT_LOG = ROOT / "saves" / "hypernova" / "scripts-agent.log"
AGENT_TELEMETRY = ROOT / "saves" / "hypernova" / "scripts-telemetry.jsonl"

FATAL_RE = re.compile(
    r"(?i)(java\.lang\.OutOfMemoryError|OutOfMemoryError|"
    r"# A fatal error has been detected|FATAL:|There was a problem|"
    r"Uncaught exception|Caused by: java\.lang\.OutOfMemoryError)"
)

_PROC: subprocess.Popen | None = None


def _emergency_cleanup() -> None:
    global _PROC
    if _PROC is not None and _PROC.poll() is None:
        try:
            kill_pid(_PROC.pid, _PROC)
        except Exception:  # noqa: BLE001
            pass
    release_lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


def acquire_lock(run_id: str) -> None:
    waited = 0
    while LOCK.exists():
        if waited % 30 == 0:
            log(f"lock exists, waiting: {LOCK}")
        time.sleep(5)
        waited += 5
        if waited > 3600:
            raise SystemExit("lock wait exceeded 1h")


def write_lock(run_id: str, pid: int | None) -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(
        json.dumps({"run": run_id, "pid": pid, "created": now_iso()}, ensure_ascii=False),
        encoding="utf-8",
    )


def release_lock() -> None:
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass


BASELINE_GLIB = EVID / "cache-baseline" / "GraphicsLib"


def clear_caches() -> dict:
    """Revised cold procedure: keep/restore a normal-cache baseline, clear
    only the core texture cache (preserve startup-optimization) and the
    Hypernova script cache.  Never leave the normal-cache directories absent.
    """
    info = {}
    for rel in ["mods/GraphicsLib/cache", "mods/shaderLib/cache"]:
        d = ROOT / rel
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write-probe"
        try:
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            info[rel] = "present_writable"
        except OSError as e:  # noqa: BLE001
            info[rel] = f"NOT_WRITABLE: {e}"
    if BASELINE_GLIB.is_dir():
        target = ROOT / "mods/GraphicsLib/cache"
        shutil.rmtree(target)
        shutil.copytree(BASELINE_GLIB, target)
        info["restored_baseline"] = str(BASELINE_GLIB)
    else:
        info["restored_baseline"] = "absent (kept current cache)"

    m = CORE / "cache" / "mixinfr"
    if m.exists():
        shutil.rmtree(m)
        info["starsector-core/cache/mixinfr"] = "removed"
    else:
        info["starsector-core/cache/mixinfr"] = "absent"
    sc = ROOT / "saves" / "hypernova" / "scripts-cache"
    if sc.exists():
        n = sum(1 for _ in sc.rglob("*"))
        shutil.rmtree(sc)
        info["saves/hypernova/scripts-cache"] = {"files_removed": n}
    else:
        info["saves/hypernova/scripts-cache"] = "absent"
    for keep in ["starsector-core/cache/startup-optimization", "mods/DDSCache"]:
        info["preserved_" + keep] = (ROOT / keep).exists()
    return info


def rotate_previous_logs(run_dir: Path) -> None:
    for name in LOG_NAMES + GC_NAMES:
        p = CORE / name
        if p.exists():
            shutil.move(str(p), str(run_dir / ("prev-" + name)))
    for p in [AGENT_LOG, AGENT_TELEMETRY]:
        if p.exists():
            shutil.move(str(p), str(run_dir / ("prev-" + p.name)))


def collect_new_logs(run_dir: Path) -> None:
    pending = [(CORE / name, run_dir / name) for name in LOG_NAMES + GC_NAMES]
    pending += [(AGENT_LOG, run_dir / "scripts-agent.log"),
                (AGENT_TELEMETRY, run_dir / "scripts-telemetry.jsonl")]
    for _ in range(30):
        moving = [(s, d) for s, d in pending if s.exists()]
        if not moving:
            return
        for src, dst in moving:
            try:
                shutil.move(str(src), str(dst))
            except OSError as e:
                log(f"move retry {src.name}: {e}")
        if not any(s.exists() for s, _ in pending):
            return
        time.sleep(1)


class TailState:
    def __init__(self) -> None:
        self.offset = 0
        self.buf = ""

    def poll(self) -> str:
        p = CORE / "starsector.log"
        try:
            size = p.stat().st_size
        except FileNotFoundError:
            return self.buf[-300000:]
        if size < self.offset:
            self.offset = 0
        try:
            with open(p, "rb") as f:
                f.seek(self.offset)
                chunk = f.read(4 * 1024 * 1024)
                self.offset = f.tell()
        except OSError:
            return self.buf[-300000:]
        self.buf += chunk.decode("utf-8", errors="replace")
        if len(self.buf) > 2_000_000:
            self.buf = self.buf[-1_500_000:]
        return self.buf


def current_stage(tail: str) -> str:
    stages = []
    for m in re.finditer(
        r"Loading rule \[|Compiling script \[|Loading image \[|Loading JSON from \[",
        tail,
    ):
        t = m.group(0)
        if t.startswith("Loading rule"):
            stages.append("rules")
        elif t.startswith("Compiling script"):
            stages.append("scripts")
        elif t.startswith("Loading image"):
            stages.append("textures")
        else:
            stages.append("json")
    return stages[-1] if stages else "unknown"


def kill_pid(pid: int, proc: subprocess.Popen | None) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        log(f"taskkill failed: {e}")
    if proc is not None:
        try:
            proc.wait(timeout=60)
        except Exception:  # noqa: BLE001
            pass


def leading_ms(line: str) -> int | None:
    m = re.match(r"^(\d+)\s+\[", line)
    return int(m.group(1)) if m else None


def parse_starsector(log_paths: list[Path]) -> dict:
    out = {
        "rule_lines": 0,
        "compiling_lines": 0,
        "image_lines": 0,
        "json_lines": 0,
        "rule_first_ms": None,
        "rule_last_ms": None,
        "image_first_ms": None,
        "image_last_ms": None,
        "javasource_lines": 0,
        "janino_lines": 0,
        "fatal_lines": [],
        "java_version": None,
        "anchor_line": None,
        "anchor_ms": None,
        "last_line_ms": None,
        "stage_at_end": "unknown",
    }
    max_stage_ms = -1
    for p in log_paths:
        if not p.exists():
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                ms = leading_ms(line)
                if ms is not None:
                    out["last_line_ms"] = ms
                if "Java version:" in line:
                    out["java_version"] = line.strip()
                if "Loading rule [" in line:
                    out["rule_lines"] += 1
                    if ms is not None:
                        if out["rule_first_ms"] is None:
                            out["rule_first_ms"] = ms
                        out["rule_last_ms"] = ms
                        if ms > max_stage_ms:
                            max_stage_ms = ms
                            out["stage_at_end"] = "rules"
                if "Compiling script [" in line:
                    out["compiling_lines"] += 1
                    if ms is not None and ms > max_stage_ms:
                        max_stage_ms = ms
                        out["stage_at_end"] = "scripts"
                if "Loading image [" in line:
                    out["image_lines"] += 1
                    if ms is not None:
                        if out["image_first_ms"] is None:
                            out["image_first_ms"] = ms
                        out["image_last_ms"] = ms
                        if ms > max_stage_ms:
                            max_stage_ms = ms
                            out["stage_at_end"] = "textures"
                if "Loading JSON" in line:
                    out["json_lines"] += 1
                    if ms is not None and ms > max_stage_ms:
                        max_stage_ms = ms
                        out["stage_at_end"] = "json"
                low = line.lower()
                if "javasourceiclassloader" in low:
                    out["javasource_lines"] += 1
                if "janino" in low:
                    out["janino_lines"] += 1
                if ANCHOR in line:
                    out["anchor_line"] = line.strip()[:400]
                    out["anchor_ms"] = ms
                if FATAL_RE.search(line) and len(out["fatal_lines"]) < 20:
                    out["fatal_lines"].append(line.strip()[:400])
    return out


def parse_agent(log_path: Path) -> dict:
    out = {
        "find_span": None,
        "miss_breakdown": None,
        "cache_written": None,
        "preload": None,
        "unsupported_fr": 0,
        "lazy_disabled": 0,
        "errors": 0,
        "first_ts": None,
        "last_ts": None,
    }
    if not log_path.exists():
        return out
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            ts_m = re.match(r"^(\S+Z) ", line)
            if ts_m:
                if out["first_ts"] is None:
                    out["first_ts"] = ts_m.group(1)
                out["last_ts"] = ts_m.group(1)
            if "find span:" in line:
                out["find_span"] = line.strip()[:500]
            elif "miss breakdown:" in line:
                out["miss_breakdown"] = line.strip()[:500]
            elif "scripts cache written:" in line:
                out["cache_written"] = line.strip()[:500]
            elif "scripts cache preloaded:" in line:
                out["preload"] = line.strip()[:500]
            if "unsupported FR version" in line:
                out["unsupported_fr"] += 1
            if "lazy textures disabled" in line or "lazy: FR missing" in line:
                out["lazy_disabled"] += 1
            if " ERROR " in line:
                out["errors"] += 1
    return out


def parse_find(line: str | None) -> dict:
    if not line:
        return {}
    nums = dict(re.findall(r"(finds|hits|misses|span_ms|first_epoch_ms|last_epoch_ms)=(\d+)", line))
    return {k: int(v) for k, v in nums.items()}


def main() -> int:
    global _PROC
    ap = argparse.ArgumentParser()
    ap.add_argument("group", choices=["c1", "c2"])
    ap.add_argument("phase", choices=["cold", "warm1", "warm2"])
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--extend", type=int, default=900)
    args = ap.parse_args()

    run_id = f"{args.group}-{args.phase}"
    run_dir = EVID / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "result.json"

    acquire_lock(run_id)
    atexit.register(_emergency_cleanup)
    cache_info = clear_caches() if args.phase == "cold" else {"cleared": False}
    rotate_previous_logs(run_dir)
    write_lock(run_id, None)

    java = JAVA[args.group]
    arg = ARGFILE[args.group]
    if not java.is_file():
        release_lock()
        raise SystemExit(f"missing java: {java}")
    if not arg.is_file():
        release_lock()
        raise SystemExit(f"missing argfile: {arg}")

    env = os.environ.copy()
    for k in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"):
        env.pop(k, None)

    stdio_path = run_dir / "stdio.log"
    log(f"START {run_id}: {java} @{arg}")
    start_wall = time.time()
    start_mono = time.monotonic()
    with open(stdio_path, "wb") as stdio:
        proc = subprocess.Popen(
            [str(java), "@" + str(arg)],
            cwd=str(CORE),
            stdout=stdio,
            stderr=subprocess.STDOUT,
            env=env,
        )
        _PROC = proc
        write_lock(run_id, proc.pid)
        log(f"pid={proc.pid}")

        tail = TailState()
        timeout = args.timeout
        extended = False
        menu_elapsed = None
        timed_out = False
        exited_early = False
        kill_reason = None

        while True:
            elapsed = time.monotonic() - start_mono
            text = tail.poll()
            if ANCHOR in text:
                menu_elapsed = elapsed
                kill_reason = "menu"
                time.sleep(2)
                kill_pid(proc.pid, proc)
                break
            rc = proc.poll()
            if rc is not None:
                exited_early = menu_elapsed is None
                kill_reason = f"exit:{rc}"
                log(f"process exited rc={rc} elapsed={elapsed:.1f}s")
                break
            if elapsed >= timeout:
                stage = current_stage(text)
                if timeout == args.timeout and not extended and stage in ("rules", "scripts"):
                    timeout = args.extend
                    extended = True
                    log(f"at {elapsed:.1f}s stage={stage}; extending to {timeout}s")
                else:
                    timed_out = True
                    kill_reason = f"timeout:{stage}"
                    log(f"timeout at {elapsed:.1f}s stage={stage}; killing pid={proc.pid}")
                    kill_pid(proc.pid, proc)
                    break
            time.sleep(3)

        elapsed = time.monotonic() - start_mono
        # ensure process gone
        if proc.poll() is None:
            kill_pid(proc.pid, proc)
        try:
            proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            pass

    collect_new_logs(run_dir)
    release_lock()

    log_paths = [run_dir / n for n in LOG_NAMES]
    starsector = parse_starsector(log_paths)
    agent = parse_agent(run_dir / "scripts-agent.log")
    find = parse_find(agent["find_span"])

    result = {
        "run_id": run_id,
        "group": args.group,
        "phase": args.phase,
        "started_utc": datetime.fromtimestamp(start_wall, timezone.utc).isoformat(),
        "cache_clear": cache_info,
        "java": str(java),
        "argfile": str(arg),
        "pid": proc.pid,
        "kill_reason": kill_reason,
        "menu_reached": menu_elapsed is not None,
        "menu_elapsed_s": round(menu_elapsed, 3) if menu_elapsed is not None else None,
        "wall_elapsed_s": round(elapsed, 3),
        "timeout_s_effective": timeout,
        "extended": extended,
        "timed_out": timed_out,
        "exited_early": exited_early,
        "stage_at_end": starsector["stage_at_end"],
        "starsector": starsector,
        "agent": agent,
        "find": find,
        "stdio_bytes": stdio_path.stat().st_size if stdio_path.exists() else 0,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"RESULT {run_id}: menu={result['menu_elapsed_s']} stage={result['stage_at_end']} "
        f"rule={starsector['rule_lines']} compiling={starsector['compiling_lines']} "
        f"image={starsector['image_lines']} find={find} reason={kill_reason}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
