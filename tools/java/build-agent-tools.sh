#!/usr/bin/env bash
# 用法: bash tools/java/build-agent-tools.sh
# 依赖 build-agent.sh 的 build/agent/classes，产出 build/agent/tools-classes。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/agent/tools-classes"
bash "$ROOT_W/tools/java/build-agent.sh"
rm -rf "$OUT"
mkdir -p "$OUT"
javac --release 17 -encoding UTF-8 \
  -cp "$ROOT_W/build/agent/classes;$CORE/json.jar;$CORE/janino.jar;$CORE/commons-compiler.jar;$CORE/commons-compiler-jdk.jar" \
  -d "$OUT" $(find "$ROOT_W/src/agent/java" -path '*tools*' -name '*.java')
echo "OK: $OUT"
