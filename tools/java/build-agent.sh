#!/usr/bin/env bash
# 用法: bash tools/java/build-agent.sh
# 产出 build/agent/hypernova.agent.jar（含 ASM 9.1）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/agent"
mkdir -p "$OUT/lib" "$OUT/classes" "$OUT/asm"
if [ ! -f "$OUT/lib/asm-9.1.jar" ]; then
  unzip -p "$GAME/fr.agent.jar" asm-9.1.jar > "$OUT/lib/asm-9.1.jar"
fi
# 注意：UnZip 6.00 的 `unzip 'org/*'` 会静默匹配 0 个条目（不报错），
# 必须用 -x 排除法从根展开全部条目，否则 agent jar 里的 ASM 是空的。
if [ ! -f "$OUT/asm/org/objectweb/asm/ClassReader.class" ]; then
  rm -rf "$OUT/asm"
  mkdir -p "$OUT/asm"
  (cd "$OUT/asm" && unzip -oq "$OUT/lib/asm-9.1.jar" -x 'META-INF/*' 'module-info.class')
fi
rm -rf "$OUT/classes"
mkdir -p "$OUT/classes"
find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*' > "$OUT/sources.txt"
javac --release 17 -encoding UTF-8 \
  -cp "$GAME/json.jar;$OUT/lib/asm-9.1.jar" \
  -d "$OUT/classes" @"$OUT/sources.txt"
bad=$(javap -verbose -cp "$OUT/classes" hypernova.agent.HypernovaAgent 2>/dev/null \
  | grep -c "major version: 61" || true)
if [ "$bad" -ne 1 ]; then echo "FATAL: agent class major version != 61" >&2; exit 1; fi
printf '%s\n' \
  'Manifest-Version: 1.0' \
  'Premain-Class: hypernova.agent.HypernovaAgent' \
  'Can-Retransform-Classes: false' > "$OUT/MANIFEST.MF"
jar --create --file "$OUT/hypernova.agent.jar" --manifest "$OUT/MANIFEST.MF" \
  -C "$OUT/classes" . -C "$OUT/asm" .
echo "OK: $OUT/hypernova.agent.jar"
