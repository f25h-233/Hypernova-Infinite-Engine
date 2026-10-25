#!/usr/bin/env bash
# 用法: m1_watch.sh <pid> <log> [timeout_sec] [anchor_regex]
# 到主菜单（默认 CodexTextEntryLoader Parsing entry）后等 10s 再结束进程。
set -u
pid="$1"; log="$2"; timeout="${3:-2400}"; anchor="${4:-CodexTextEntryLoader.*Parsing entry}"
start=$(date +%s)
while kill -0 "$pid" 2>/dev/null; do
  if grep -aqE "$anchor" "$log" 2>/dev/null; then
    sleep 10
    powershell -NoProfile -Command "Stop-Process -Id $pid -Force" 2>/dev/null
    echo "ANCHOR_FOUND killed pid=$pid after $(( $(date +%s) - start ))s"
    exit 0
  fi
  now=$(date +%s)
  if (( now - start > timeout )); then
    powershell -NoProfile -Command "Stop-Process -Id $pid -Force" 2>/dev/null
    echo "TIMEOUT killed pid=$pid after ${timeout}s"
    exit 1
  fi
  sleep 10
done
echo "PROCESS_EXITED pid=$pid after $(( $(date +%s) - start ))s"
