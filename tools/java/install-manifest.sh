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
# 先在仓库内产出裁剪版中间产物，再复制到游戏目录（中间产物在 build/ 下，已被 gitignore）
BUILD_OUT="$ROOT/build/java/hypernova-manifest-v1.json"
DST="$GAME_ROOT/mods/hypernova_infinite_engine/data/config/hypernova"
mkdir -p "$ROOT/build/java" "$DST"
python -I - "$SRC" "$BUILD_OUT" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
out = {"schema": "hypernova-runtime-1", "layers": {}}
for layer in ("L1", "L2", "L3"):
    out["layers"][layer] = [
        {"path": e["path"], "modId": e["modId"], "w": e.get("w", 0),
         "h": e.get("h", 0), "baked": e.get("baked", False)}
        for e in data.get("layers", {}).get(layer, [])
        if e.get("path")
    ]
with open(dst, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
print(f"wrote {dst}: " + ", ".join(f"{k}={len(v)}" for k, v in out["layers"].items()))
PY
cp "$BUILD_OUT" "$DST/manifest-v1.json"
echo "installed: $DST/manifest-v1.json"

# 若已跑过 build-mod.sh，一并把 jar 与 mod_info.json 装进同一 mod 目录
MODDIR="$GAME_ROOT/mods/hypernova_infinite_engine"
if [ -f "$ROOT/build/java/hypernova.jar" ]; then
  mkdir -p "$MODDIR/jars"
  cp "$ROOT/build/java/hypernova.jar" "$MODDIR/jars/hypernova.jar"
  cp "$ROOT/mod_info.json" "$MODDIR/mod_info.json"
  # data/ 下的其余运行时配置（hypernova.json / settings.json 等）也同步过去
  if [ -d "$ROOT/data" ]; then mkdir -p "$MODDIR/data"; cp -r "$ROOT/data/." "$MODDIR/data/"; fi
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
