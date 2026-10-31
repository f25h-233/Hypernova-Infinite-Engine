#!/usr/bin/env python3
"""Hypernova 冒烟自动化：启动 -> 检测主菜单 -> 记录耗时 -> 干净退出 -> 汇总。

## 全自动（2026-10-30 实测跑通，11.1s 到主菜单，零人工）

不用点启动器。`StarfarerLauncher` 的构造函数里有一条直接启动分支：

    if (System.getProperty("launchDirect") != null) {     // StarfarerSettings.ØÕ0000()
        if (ooOO.getInstance().<canStart>()) {
            String[] wh = System.getProperty("startRes").split("x");
            boolean fs    = Boolean.parseBoolean(System.getProperty("startFS"));
            boolean sound = Boolean.parseBoolean(System.getProperty("startSound"));
            o00000(fs, sound, wh[0], wh[1]);   // 直接进游戏，不建 UI
            return;
        }
    }

而且这条路径走的是 `new StarfarerLauncher(true)` 的**完整初始化**
（ModManager / StarfarerSettings 都就绪），所以没有 DirectLaunch 那种
"settings 未初始化 → StringIndexOutOfBoundsException" 的问题。

本脚本在启动时注入这四个 -D 属性，因此**无需任何人工交互**。

（顺带记录：本会话跑在非活动桌面上，SetForegroundWindow 恒为 0、
SendInput/PostMessage 进不了游戏，所以「模拟点击」这条路在本机不可行。）

本脚本负责：
  * 注入 launchDirect/startRes/startFS/startSound 并启动进程
  * 轮询 starsector.log 直到出现主菜单锚点，记录**精确耗时**
  * 进主菜单后再停留 N 秒（给 CacheWriter 稳定窗口）
  * 干净退出（先 taskkill 不带 /F，让 shutdown hook 落盘；超时才 /F）
  * 多轮重复 + 汇总（冷热对比全自动）

## 用法

    # 单轮
    python tools/smoke_run.py --profile miko-simple

    # 冷热对比 3 轮（第 1 轮前清缓存）
    python tools/smoke_run.py --profile miko-simple --rounds 3 --clear-cache-first

    # 只测热跑
    python tools/smoke_run.py --profile base --rounds 2

## 主菜单锚点

`Playing music with id [miscallenous_main_menu.ogg]` —— 游戏真的进入主菜单时才写。
比 sleep 固定秒数可靠：慢机器不会误判，快机器不会白等。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROFILES = {
    # vmparams 一律**相对 cwd** 写（cwd 都是 starsector-core）：
    #   base        -> fr.vmparams
    #   miko-*      -> ../Miko_*.txt（在游戏根目录）
    "base": {
        "game": "Starsector-098-Base",
        "java": "jre/bin/java.exe",
        "vmparams": "fr.vmparams",
        "cwd": "starsector-core",
    },
    # Miko 的 vmparams 在**游戏根目录**，cwd 是 starsector-core，
    # 所以必须写 ../Miko_Simple.txt（照抄 LaunchMiko.ps1 的参数）。
    "miko-simple": {
        "game": "Starsector-098-260mods",
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": "../Miko_Simple.txt",
        "cwd": "starsector-core",
    },
    "miko-lite": {
        "game": "Starsector-098-260mods",
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": "../Miko_Lite.txt",
        "cwd": "starsector-core",
    },
    "miko-lite-phase": {
        "game": "Starsector-098-260mods",
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": "../Miko_Lite_phase.txt",
        "cwd": "starsector-core",
    },
    "miko-lite-nofr": {
        "game": "Starsector-098-260mods",
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": "../Miko_Lite_nofr.txt",
        "cwd": "starsector-core",
    },
}

MENU_ANCHOR = b"Playing music with id [miscallenous_main_menu.ogg]"
# Prefix match: FR 0.9.5 logs "v0.9.5", FR 0.9.7rc2 logs "v0.9.7rc2".
# A version-pinned anchor silently stops finding sessions after an FR upgrade.
SESSION_ANCHOR = b"Fast Rendering: v0.9."


# ---------------------------------------------------------------- log helpers

def log_path_for(game: Path) -> Path:
    return game / "starsector-core" / "starsector.log"


def session_offset(log_path: Path) -> int:
    """当前日志里最后一次会话起始的字节偏移。"""
    if not log_path.is_file():
        return 0
    data = log_path.read_bytes()
    idx = data.rfind(SESSION_ANCHOR)
    return 0 if idx < 0 else idx


def read_tail(log_path: Path, offset: int) -> bytes:
    try:
        with log_path.open("rb") as f:
            f.seek(offset)
            return f.read()
    except OSError:
        return b""


def wait_for_menu(log_path: Path, offset: int, timeout_s: float,
                  proc: subprocess.Popen) -> float | None:
    """增量读日志等主菜单。

    260mods 的日志能到 40 MB+；每轮把 offset 之后的内容整个重读会越来越慢
    （实测 0.5s 轮询下，后期每次读取数十 MB）。这里维护一个游标，只读新增部分，
    并用 overlap 处理锚点跨两次读取边界的情况。
    """
    t0 = time.time()
    cursor = offset
    overlap = b""
    while time.time() - t0 < timeout_s:
        if proc.poll() is not None:
            return None
        try:
            size = log_path.stat().st_size
            # 日志被重写（新一轮启动/轮转）时 size 会小于 cursor。
            # 不重置 cursor 的话 seek 到 EOF 之后永远读不到东西——实测踩到，
            # 表现为"游戏明明到了主菜单但脚本一直等到超时"。
            if size < cursor:
                print(f"[smoke] log rotated (size {size} < cursor {cursor}); rescan from 0",
                      flush=True)
                cursor = 0
                overlap = b""
            with log_path.open("rb") as f:
                f.seek(cursor)
                chunk = f.read()
            if chunk:
                cursor += len(chunk)
                # 拼上一轮末尾，避免锚点被切在两块之间
                if MENU_ANCHOR in overlap + chunk:
                    return time.time() - t0
                overlap = chunk[-len(MENU_ANCHOR):]
        except OSError:
            pass
        time.sleep(0.5)
    return None


def agent_log_for(game: Path) -> Path:
    return game / "saves" / "hypernova" / "scripts-agent.log"


def agent_results(game: Path, since_bytes: int) -> dict:
    """从 agent 日志里抓最近一轮的关键行。"""
    p = agent_log_for(game)
    out: dict = {}
    if not p.is_file():
        return out
    try:
        with p.open("rb") as f:
            f.seek(since_bytes)
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return out
    for line in text.splitlines():
        if "scripts cache preloaded:" in line:
            out["preload_hit"] = line
        elif "scripts cache cold:" in line:
            out["preload_cold"] = line
        elif "script phase ended:" in line:
            out["phase_end"] = line
        elif "miss breakdown:" in line:
            out["breakdown"] = line
        elif "scripts cache written:" in line:
            out.setdefault("writes", []).append(line)
        elif "FR missing; scripts cache disabled" in line:
            out["fr_missing"] = line
        elif "textures: patched" in line:
            out["textures_patched"] = line
        elif "textures: TextureData sha mismatch" in line:
            out["textures_mismatch"] = line
        elif "cache key ready (background):" in line:
            out["key_ready"] = line
        elif "cache key breakdown:" in line:
            out["key_breakdown"] = line
        elif "file index:" in line:
            out.setdefault("file_index", []).append(line)
    return out


# ---------------------------------------------------------------- process ops

def kill_pid(pid: int, force: bool) -> None:
    # 注意：Git Bash 会把 /PID 当路径转换，必须走 subprocess 的 argv 形式（不经过 shell）。
    # 参数顺序必须是 taskkill /F /PID <pid>；旧写法把 /F 插在 /PID 之后，
    # 成了 "taskkill /PID /F <pid>"，taskkill 静默失败（已实测踩到）。
    args = ["taskkill", "/F", "/PID", str(pid)] if force else ["taskkill", "/PID", str(pid)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            print(f"[smoke] taskkill pid={pid} force={force} rc={r.returncode}: "
                  f"{(r.stdout or r.stderr).strip()[:120]}", flush=True)
    except Exception as e:
        print(f"[smoke] taskkill pid={pid} exception: {e}", flush=True)


def pid_alive(pid: int) -> bool:
    """用 tasklist 判断存活，不依赖 Popen.wait（CREATE_NEW_PROCESS_GROUP 下不可靠）。"""
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True, timeout=10)
        return str(pid) in r.stdout
    except Exception:
        return False


def wait_dead(pid: int, timeout_s: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if not pid_alive(pid):
            return True
        time.sleep(0.5)
    return False


def graceful_stop(proc: subprocess.Popen, wait_s: float = 40.0) -> str:
    """先请求关闭（让 shutdown hook 落盘），再兜底强杀。

    实测：Windows 上对 `java.exe` 用 taskkill 不带 /F 基本无效（游戏没有
    窗口消息循环可响应 CTRL_CLOSE），所以 15 秒后直接升级 /F。
    shutdown hook 在强杀时**不会**执行——这意味着缓存落盘只能靠
    CacheWriter 的稳定窗口，不能依赖退出时 flush。这一点已记入验收口径。
    """
    pid = proc.pid
    if not pid_alive(pid):
        return "already-exited"
    kill_pid(pid, force=False)
    if wait_dead(pid, 15):
        return "graceful"
    kill_pid(pid, force=True)
    if wait_dead(pid, 20):
        return "forced"
    return "still-running"


# ---------------------------------------------------------------- one round

def build_command(java: str, vmparams_arg: str, direct: list[str],
                  jvm_args: list[str]) -> list[str]:
    """JVM props and the argfile are all JVM args; -D must come before @file."""
    return [java, *direct, *jvm_args, f"@{vmparams_arg}"]


if sys.platform == "win32":
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IoCounters)]
    _k32.GetProcessIoCounters.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL

    def io_read_bytes(pid: int) -> int | None:
        # PROCESS_QUERY_LIMITED_INFORMATION works for same-user processes.
        handle = _k32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            counters = _IoCounters()
            if not _k32.GetProcessIoCounters(handle, ctypes.byref(counters)):
                return None
            return int(counters.ReadTransferCount)
        finally:
            _k32.CloseHandle(handle)
else:
    def io_read_bytes(pid: int) -> int | None:
        return None


def one_round(cfg: dict, game: Path, args) -> dict:
    java = game / cfg["java"]
    cwd = game / cfg["cwd"]
    # vmparams 可能是相对 cwd 的 ../ 路径；存在性检查要按 cwd 解析。
    vmparams_arg = cfg["vmparams"]
    vmparams = (cwd / vmparams_arg).resolve()
    logp = log_path_for(game)
    agentp = agent_log_for(game)

    # 记录的是"本次启动前日志的末尾"。启动后只从这之后找锚点，
    # 绝不能用 rfind(SESSION_ANCHOR)——那会落在上一次会话里，导致 0 秒误判（已实测踩到）。
    offset = logp.stat().st_size if logp.is_file() else 0
    agent_off = agentp.stat().st_size if agentp.is_file() else 0

    # 直接启动：不经启动器 UI。argfile 与命令行 -D 可共存。
    direct = [
        "-DlaunchDirect=true",
        f"-DstartRes={args.start_res}",
        f"-DstartFS={'true' if args.fullscreen else 'false'}",
        "-DstartSound=true",
    ]
    cmd = build_command(str(java), vmparams_arg, direct, args.jvm_arg)
    t0 = time.time()
    # 不要用 CREATE_NEW_PROCESS_GROUP：实测它会让 Popen.pid 与实际 java 进程
    # 不一致（Popen 拿到的是中间进程），导致 kill 打空、游戏残留（已实测踩到）。
    proc = subprocess.Popen(cmd, cwd=str(cwd),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"\n{'='*60}")
    print(f">>> 直接启动（launchDirect），自动等待主菜单……")
    print(f"{'='*60}", flush=True)

    menu_s = wait_for_menu(logp, offset, args.wait_menu, proc)
    if menu_s is None:
        kill_pid(proc.pid, True)
        return {"ok": False, "reason": "menu-timeout", "elapsed": time.time() - t0}

    print(f">>> 主菜单到达：{menu_s:.1f}s（从进程启动算）")

    read_menu = io_read_bytes(proc.pid)

    if args.linger > 0:
        print(f">>> 停留 {args.linger:.0f}s（给 CacheWriter 稳定窗口）")
        time.sleep(args.linger)

    read_exit = io_read_bytes(proc.pid)
    how = graceful_stop(proc)
    wall = time.time() - t0
    print(f">>> 退出方式：{how}；总墙钟 {wall:.1f}s")

    time.sleep(1.0)   # 让 shutdown hook 写完
    return {
        "ok": True,
        "menu_s": round(menu_s, 1),
        "wall_s": round(wall, 1),
        "stop": how,
        "read_bytes_menu": read_menu,
        "read_bytes_exit": read_exit,
        "agent": agent_results(game, agent_off),
    }


# ---------------------------------------------------------------- reporting

def summarize(rows: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    for i, r in enumerate(rows, 1):
        if not r.get("ok"):
            print(f"#{i}: FAILED ({r.get('reason')})")
            continue
        a = r.get("agent", {})
        pre = "cold" if "preload_cold" in a else ("hit" if "preload_hit" in a else "?")
        pre_ms = "?"
        if pre == "hit":
            m = re.search(r"entries=(\d+), bytes=\d+, in (\d+) ms", a["preload_hit"])
            if m:
                pre_ms = f"{m.group(2)}ms/{m.group(1)}条"
        elif pre == "cold":
            m = re.search(r"in (\d+) ms", a["preload_cold"])
            if m:
                pre_ms = f"{m.group(1)}ms"
        # menu_s 是唯一可信的端到端指标：日志里 Playing music 锚点，
        # 不会像"缓存停止增长"那样在加载中途的停顿处误判。
        flags = []
        if "fr_missing" in a:
            flags.append("no-FR")
        if "textures_patched" in a:
            flags.append("textures:patched")
        if "textures_mismatch" in a:
            flags.append("textures:MISMATCH")
        print(f"#{i}: menu={r['menu_s']}s wall={r['wall_s']}s preload={pre}({pre_ms}) "
              f"stop={r['stop']} {' '.join(flags)}")
        if a.get("file_index"):
            print(f"     {a['file_index'][-1].split('INFO ')[-1]}")
        if "breakdown" in a:
            print(f"     {a['breakdown'].split('INFO ')[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=sorted(PROFILES), required=True)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--wait-menu", type=float, default=300.0)
    ap.add_argument("--click-wait", type=float, default=60.0,
                    help="提示你在启动器里点击的等待提示时长（仅用于打印）")
    ap.add_argument("--linger", type=float, default=8.0)
    ap.add_argument("--clear-cache-first", action="store_true",
                    help="第 1 轮前删除 scripts-cache（测冷跑）")
    ap.add_argument("--start-res", default="1707x1067",
                    help="直接启动时传给游戏的 startRes")
    ap.add_argument("--fullscreen", action="store_true", help="直接启动时全屏")
    ap.add_argument("--jvm-arg", action="append", default=[],
                    help="extra JVM argument, e.g. -Dhypernova.textures=false")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    cfg = PROFILES[args.profile]
    game = ROOT / cfg["game"]
    cwd = game / cfg["cwd"]
    for key, p in (("game", game), ("java", game / cfg["java"]),
                   ("cwd", cwd), ("vmparams", (cwd / cfg["vmparams"]).resolve())):
        if not p.exists():
            print(f"FATAL: {key} not found: {p}", file=sys.stderr)
            return 2

    cache = game / "saves" / "hypernova" / "scripts-cache"
    if args.clear_cache_first and cache.exists():
        shutil.rmtree(cache)
        print(f"[smoke] cleared {cache}")

    rows = []
    for i in range(1, args.rounds + 1):
        print(f"\n########## 第 {i}/{args.rounds} 轮 ##########")
        rows.append(one_round(cfg, game, args))
        if i < args.rounds:
            time.sleep(3)

    summarize(rows)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[smoke] json -> {args.json_out}")
    return 0 if all(r.get("ok") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
