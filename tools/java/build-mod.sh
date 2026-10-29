#!/usr/bin/env bash
# 用法: bash tools/java/build-mod.sh [--env base|260mods]
# 打包成品 mod（含运行时 manifest）。manifest 源缺失时**拒绝产出 zip**：
# 缺 manifest 的包解压后 ManifestLoader.load() 返回 null，整组件静默禁用（C1）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Git Bash/MSYS 下 javac/jar/javap 是原生 Windows 程序，不认 /d/... 路径，统一转成 D:/...
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
ENV="base"
if [ "${1:-}" = "--env" ]; then ENV="${2:?--env needs a value}"; fi
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/java"
CP="$GAME/starfarer.api.jar;$GAME/json.jar;$GAME/lwjgl.jar;$GAME/log4j-1.2.9.jar"
rm -rf "$OUT/classes" "$OUT/hypernova.jar"
# 先删旧 zip：任何一步失败都不留下上一次的成品（否则失败路径仍然「有包可发」）。
rm -f "$OUT/hypernova-0.1.0.zip"
mkdir -p "$OUT/classes"
find "$ROOT_W/src/main/java" -name '*.java' > "$OUT/sources.txt"
javac --release 17 -encoding UTF-8 -cp "$CP" -d "$OUT/classes" @"$OUT/sources.txt"
# 校验主版本 61
bad=$(javap -verbose -cp "$OUT/classes" hypernova.HypernovaPlugin 2>/dev/null | grep -c "major version: 61" || true)
if [ "$bad" -ne 1 ]; then echo "FATAL: class file major version != 61" >&2; exit 1; fi
jar --create --file "$OUT/hypernova.jar" -C "$OUT/classes" .
echo "OK: $OUT/hypernova.jar"

# ---- 运行时 manifest：裁自 M0 产物，库存到 dist/ 以便分发路径可复现 ----
MANIFEST_SRC="$ROOT_W/build/m0/$ENV/manifest-v1.json"
MANIFEST_DIST="$ROOT/dist/manifest-v1.json"
if [ ! -f "$MANIFEST_SRC" ]; then
  echo "FATAL: 运行时 manifest 源不存在: $MANIFEST_SRC" >&2
  echo "       先跑 tools/gen_manifest.py（见 docs/m1/），再重跑本脚本；" >&2
  echo "       缺 manifest 的发布包会让整个组件在用户机上静默禁用。" >&2
  exit 1
fi
python -I "$ROOT_W/tools/trim_manifest.py" --src "$MANIFEST_SRC" --out "$(winpath "$MANIFEST_DIST")"
cp "$MANIFEST_DIST" "$OUT/hypernova-manifest-v1.json"

# ---- 打包成品 mod 目录与 zip ----
MODDIR="$OUT/hypernova-mod"
rm -rf "$MODDIR"; mkdir -p "$MODDIR/jars" "$MODDIR/data/config/hypernova"
cp "$OUT/hypernova.jar" "$MODDIR/jars/hypernova.jar"
cp "$ROOT_W/mod_info.json" "$MODDIR/mod_info.json"
# 可选 agent：构建过就放进 mod 包；是否启用由 install_agent.py 决定。
if [ -f "$ROOT_W/build/agent/hypernova.agent.jar" ]; then
  cp "$ROOT_W/build/agent/hypernova.agent.jar" "$MODDIR/jars/hypernova.agent.jar"
fi
# 注意 `cp -r data/. <dst>` 而不是 `cp -r data <dst>`：后者在 dst 存在时会嵌套成 data/data/。
mkdir -p "$MODDIR/data"
cp -r "$ROOT_W/data/." "$MODDIR/data/"
cp "$OUT/hypernova-manifest-v1.json" "$MODDIR/data/config/hypernova/manifest-v1.json"
# zip 内容断言：manifest 必须在且非空，否则宁可不产出 zip。
if [ ! -s "$MODDIR/data/config/hypernova/manifest-v1.json" ]; then
  echo "FATAL: 打包目录缺少 data/config/hypernova/manifest-v1.json" >&2
  exit 1
fi
rm -f "$OUT/hypernova-0.1.0.zip"
(cd "$OUT" && jar --create --file hypernova-0.1.0.zip -C hypernova-mod .)
if ! (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'data/config/hypernova/manifest-v1.json'; then
  echo "FATAL: hypernova-0.1.0.zip 内缺少 data/config/hypernova/manifest-v1.json" >&2
  exit 1
fi
if [ -f "$MODDIR/jars/hypernova.agent.jar" ]; then
  (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'jars/hypernova.agent.jar' \
    || { echo "FATAL: zip 缺少 jars/hypernova.agent.jar" >&2; exit 1; }
fi
echo "OK: $MANIFEST_DIST (dist artifact, not tracked)"
echo "OK: $ROOT/build/java/hypernova-mod"
echo "OK: $ROOT/build/java/hypernova-0.1.0.zip"
