#!/usr/bin/env bash
# 用法: bash tools/java/install-manifest.sh <game-root>
# 运行时 manifest 与 lazy-skip-v1.txt 由 M2 安装器根据该游戏安装就地生成。
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "FATAL: usage: install-manifest.sh <game-root>" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_ROOT="${1:?usage: install-manifest.sh <game-root>}"
MODDIR="$GAME_ROOT/mods/hypernova_infinite_engine"
DST="$MODDIR/data/config/hypernova"

if [ ! -f "$ROOT/build/java/hypernova.jar" ]; then
  echo "ERROR: $ROOT/build/java/hypernova.jar not found; 先跑 tools/java/build-mod.sh" >&2
  exit 1
fi

# 安装 jar 与静态 data/。data/ 拷贝可能带回旧 manifest/skip，因此安装器最后跑。
mkdir -p "$MODDIR/jars" "$DST"
cp "$ROOT/build/java/hypernova.jar" "$MODDIR/jars/hypernova.jar"
cp "$ROOT/mod_info.json" "$MODDIR/mod_info.json"
if [ -d "$ROOT/data" ]; then mkdir -p "$MODDIR/data"; cp -r "$ROOT/data/." "$MODDIR/data/"; fi
if [ -d "$ROOT/graphics" ]; then
  mkdir -p "$MODDIR/graphics"
  cp -r "$ROOT/graphics/." "$MODDIR/graphics/"
fi

python -I "$ROOT/tools/install_manifest.py" --game-root "$GAME_ROOT"
echo "installed: $GAME_ROOT/mods/hypernova_infinite_engine/data/config/hypernova/{manifest-v1.json,lazy-skip-v1.txt}"

# 安装后校验：确保装进去的 jar 与刚构建的一致（曾经因为没重装，
# 测试 mod 反射调用到旧 class 而抛 NoSuchMethodError）。
if [ -f "$MODDIR/jars/hypernova.jar" ] && [ -f "$ROOT/build/java/hypernova.jar" ]; then
  if ! cmp -s "$MODDIR/jars/hypernova.jar" "$ROOT/build/java/hypernova.jar"; then
    echo "ERROR: installed jar differs from build/java/hypernova.jar" >&2
    exit 1
  fi
  echo "verified: installed jar matches build output"
fi
