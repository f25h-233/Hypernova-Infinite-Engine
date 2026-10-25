#!/usr/bin/env bash
# 用法: bash tools/java/run-tests.sh [TestClassFilter]
# Filter 是正则的**子串匹配**：传 TextureManifestTest 即可。
# 过滤器匹配 0 个测试视为失败（否则会出现「什么都没跑却 exit 0」的假绿）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Git Bash/MSYS 下 javac/java 是原生 Windows 程序，不认 /d/... 路径，统一转成 D:/...
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
LIB="$ROOT_W/lib"
OUT="$ROOT_W/build/java/test-classes"
if [ ! -f "$LIB/junit-platform-console-standalone.jar" ]; then
  echo "缺少 $LIB/junit-platform-console-standalone.jar（见 Task 1 Step 3 的下载说明）" >&2
  exit 2
fi
CP="$GAME/starfarer.api.jar;$GAME/json.jar;$GAME/lwjgl.jar;$GAME/log4j-1.2.9.jar;$LIB/junit-platform-console-standalone.jar"
rm -rf "$OUT"; mkdir -p "$OUT"
MAIN_OUT="$ROOT_W/build/java/classes"
rm -rf "$MAIN_OUT"; mkdir -p "$MAIN_OUT"
find "$ROOT_W/src/main/java" -name '*.java' > "$OUT/../main-sources.txt"
javac --release 17 -encoding UTF-8 -cp "$CP" -d "$MAIN_OUT" @"$OUT/../main-sources.txt"
find "$ROOT_W/tests/java" -name '*.java' > "$OUT/../test-sources.txt"
javac --release 17 -encoding UTF-8 -cp "$CP;$MAIN_OUT" -d "$OUT" @"$OUT/../test-sources.txt"
FILTER=".*"
if [ -n "${1:-}" ]; then FILTER=".*${1}.*"; fi
java -jar "$LIB/junit-platform-console-standalone.jar" \
  --class-path "$OUT;$MAIN_OUT;$GAME/starfarer.api.jar;$GAME/json.jar;$GAME/lwjgl.jar;$GAME/log4j-1.2.9.jar" \
  --scan-class-path "$OUT" \
  --include-classname="$FILTER" \
  --fail-if-no-tests
