#!/usr/bin/env bash
# 用法: bash tools/java/build-mod.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Git Bash/MSYS 下 javac/jar/javap 是原生 Windows 程序，不认 /d/... 路径，统一转成 D:/...
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/java"
CP="$GAME/starfarer.api.jar;$GAME/json.jar;$GAME/lwjgl.jar;$GAME/log4j-1.2.9.jar"
rm -rf "$OUT/classes" "$OUT/hypernova.jar"
mkdir -p "$OUT/classes"
find "$ROOT_W/src/main/java" -name '*.java' > "$OUT/sources.txt"
javac --release 17 -encoding UTF-8 -cp "$CP" -d "$OUT/classes" @"$OUT/sources.txt"
# 校验主版本 61
bad=$(javap -verbose -cp "$OUT/classes" hypernova.HypernovaPlugin 2>/dev/null | grep -c "major version: 61" || true)
if [ "$bad" -ne 1 ]; then echo "FATAL: class file major version != 61" >&2; exit 1; fi
jar --create --file "$OUT/hypernova.jar" -C "$OUT/classes" .
echo "OK: $OUT/hypernova.jar"
