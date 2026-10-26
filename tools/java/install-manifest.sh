#!/usr/bin/env bash
# 用法: bash tools/java/install-manifest.sh <game-root> [--env base|260mods]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_ROOT="${1:?usage: install-manifest.sh <game-root> [--env base|260mods]}"
ENV="base"
if [ "${2:-}" = "--env" ]; then ENV="${3:?--env needs a value}"; fi
SRC="$ROOT/build/m0/$ENV/manifest-v1.json"
if [ ! -f "$SRC" ]; then
  echo "manifest not found: $SRC (先跑 tools/gen_manifest.py)" >&2
  exit 1
fi
# 先在仓库内产出裁剪版中间产物，再复制到游戏目录（中间产物在 build/ 下，已被 gitignore）。
# 裁剪逻辑放在 tools/trim_manifest.py，与 build-mod.sh 打包共用同一份实现。
BUILD_OUT="$ROOT/build/java/hypernova-manifest-v1.json"
DST="$GAME_ROOT/mods/hypernova_infinite_engine/data/config/hypernova"
mkdir -p "$ROOT/build/java" "$DST"
python -I "$ROOT/tools/trim_manifest.py" --src "$SRC" --out "$BUILD_OUT"
cp "$BUILD_OUT" "$DST/manifest-v1.json"
echo "installed: $DST/manifest-v1.json"

# 若已跑过 build-mod.sh，一并把 jar 与 mod_info.json 装进同一 mod 目录
MODDIR="$GAME_ROOT/mods/hypernova_infinite_engine"
if [ -f "$ROOT/build/java/hypernova.jar" ]; then
  mkdir -p "$MODDIR/jars"
  cp "$ROOT/build/java/hypernova.jar" "$MODDIR/jars/hypernova.jar"
  cp "$ROOT/mod_info.json" "$MODDIR/mod_info.json"
  # data/ 下的其余运行时配置（hypernova.json / settings.json 等）也同步过去。
  # 注意：cp -r 可能把刚装好的 manifest 覆盖回旧版本，故紧随其后重新落一次（见下）。
  if [ -d "$ROOT/data" ]; then mkdir -p "$MODDIR/data"; cp -r "$ROOT/data/." "$MODDIR/data/"; fi
  # data/ 同步之后再落一次 manifest，保证它是本次裁剪产物（幂等）。
  cp "$BUILD_OUT" "$DST/manifest-v1.json"
  echo "installed: $MODDIR/jars/hypernova.jar, mod_info.json, data/"
else
  echo "ERROR: $ROOT/build/java/hypernova.jar not found; 先跑 tools/java/build-mod.sh" >&2
  exit 1
fi

# 安装后校验：确保装进去的 jar 与刚构建的一致（曾经因为没重装，
# 测试 mod 反射调用到旧 class 而抛 NoSuchMethodError）。
if [ -f "$MODDIR/jars/hypernova.jar" ] && [ -f "$ROOT/build/java/hypernova.jar" ]; then
  if ! cmp -s "$MODDIR/jars/hypernova.jar" "$ROOT/build/java/hypernova.jar"; then
    echo "ERROR: installed jar differs from build/java/hypernova.jar" >&2
    exit 1
  fi
  echo "verified: installed jar matches build output"
fi
