#!/usr/bin/env bash
# 编译游戏面向的代理子类（LazyProxyObject extends com.fs.graphics.Object）。
# 单独源根/src/agent/proxy 的原因：主 agent 源码在没有游戏 jar 时也要能编译，
# 而子类必须引用游戏类。产物进 build/agent/proxy，由 build-agent.sh 打进 jar。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/agent"
if [ ! -d "$OUT/classes" ]; then
  echo "FATAL: agent classes missing; run build-agent.sh first" >&2
  exit 1
fi
rm -rf "$OUT/proxy"
mkdir -p "$OUT/proxy"
find "$ROOT_W/src/agent/proxy/java" -name '*.java' > "$OUT/proxy-sources.txt"
javac --release 17 -encoding UTF-8 \
  -cp "$GAME/fs.common_obf.jar;$GAME/starfarer_obf.jar;$OUT/classes" \
  -d "$OUT/proxy" @"$OUT/proxy-sources.txt"
if [ ! -f "$OUT/proxy/hypernova/agent/textures/LazyProxyObject.class" ]; then
  echo "FATAL: LazyProxyObject.class not produced" >&2
  exit 1
fi
echo "OK: $OUT/proxy"
