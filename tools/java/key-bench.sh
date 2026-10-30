#!/usr/bin/env bash
# 用法: bash tools/java/key-bench.sh [游戏根目录]
# 在真实安装的文件树上跑 key 分项基准；manifest 用临时副本，不写真实缓存。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$(winpath "${1:-$ROOT/Starsector-098-260mods}")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
JAVA="$ROOT_W/Starsector-098-Base/jre/bin/java.exe"
test -x "$JAVA" || { echo "FATAL: Base JRE not found: $JAVA" >&2; exit 1; }

bash "$ROOT_W/tools/java/build-agent.sh" >/dev/null
OUT="$ROOT_W/build/keybench"
rm -rf "$OUT/classes"
mkdir -p "$OUT/classes"
javac --release 17 -encoding UTF-8 \
  -cp "$ROOT_W/build/agent/classes;$CORE/json.jar" \
  -d "$OUT/classes" "$ROOT_W/tools/java/keybench/KeyBench.java"

TMP="$(winpath "$(mktemp -d)")"
cp "$GAME/saves/hypernova/scripts-cache/key-manifest.json" "$TMP/" 2>/dev/null || true
CP="$ROOT_W/build/agent/classes;$CORE/json.jar;$OUT/classes"

echo "== threads=4 (auto) =="
"$JAVA" -Dhypernova.keyThreads=4 -cp "$CP" hypernova.agent.KeyBench "$GAME" "$GAME/mods" "$TMP" 5
echo "== threads=1 =="
"$JAVA" -Dhypernova.keyThreads=1 -cp "$CP" hypernova.agent.KeyBench "$GAME" "$GAME/mods" "$TMP" 5
rm -rf "$TMP"
