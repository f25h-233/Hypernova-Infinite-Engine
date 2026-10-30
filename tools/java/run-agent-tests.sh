#!/usr/bin/env bash
# 用法: bash tools/java/run-agent-tests.sh [TestClassFilter]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
LIB="$ROOT_W/lib"
JAVA_RUNTIME="${JAVA_RUNTIME:-java}"
echo "runtime: $("$JAVA_RUNTIME" -version 2>&1 | head -n 1)"
bash "$ROOT_W/tools/java/build-agent.sh"
ASM="$ROOT_W/build/agent/lib/asm-9.1.jar"
OUT="$ROOT_W/build/agent/run-$$-$(date +%s%N)"
mkdir -p "$OUT/classes" "$OUT/tests"
if [ ! -f "$LIB/junit-platform-console-standalone.jar" ]; then
  echo "missing $LIB/junit-platform-console-standalone.jar" >&2
  exit 2
fi
javac --release 17 -encoding UTF-8 -cp "$GAME/json.jar;$ASM" \
  -d "$OUT/classes" $(find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*')
find "$ROOT_W/tests/agent/java" -name '*.java' > "$OUT/test-sources.txt"
if [ -d "$ROOT_W/tests/agent/fixtures" ]; then
  find "$ROOT_W/tests/agent/fixtures" -name '*.java' >> "$OUT/test-sources.txt"
fi
javac --release 17 -encoding UTF-8 \
  -cp "$GAME/json.jar;$ASM;$OUT/classes;$LIB/junit-platform-console-standalone.jar" \
  -d "$OUT/tests" @"$OUT/test-sources.txt"
FILTER=".*"
if [ -n "${1:-}" ]; then FILTER=".*${1}.*"; fi
"$JAVA_RUNTIME" -jar "$LIB/junit-platform-console-standalone.jar" \
  --class-path "$OUT/classes;$OUT/tests;$GAME/json.jar;$ASM" \
  --scan-class-path "$OUT/tests" \
  --include-classname="$FILTER" \
  --fail-if-no-tests
rm -rf "$OUT"
