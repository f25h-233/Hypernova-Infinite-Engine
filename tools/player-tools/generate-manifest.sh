#!/usr/bin/env bash
# Hypernova 无限引擎 —— 按当前游戏目录重新生成 manifest / lazy-skip。
# 用法（mods/<ModFolder>/hypernova-tools/ 下）: bash generate-manifest.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODDIR="$(cd "$HERE/.." && pwd)"

# 向上找带 starsector-core 的祖先：不假定固定层数，多套一层文件夹也能认出来。
GAME=""
PROBE="$MODDIR"
for _ in 1 2 3 4 5; do
  PROBE="$(cd "$PROBE/.." && pwd)"
  if [ -d "$PROBE/starsector-core" ]; then GAME="$PROBE"; break; fi
done

if [ -z "$GAME" ] || [ ! -f "$MODDIR/mod_info.json" ]; then
  echo "[错误] 没找到游戏目录：从 $MODDIR 往上没有哪一层下面有 starsector-core。" >&2
  echo "       请把整个 mod 文件夹放在 游戏目录/mods/ 下面再运行。" >&2
  exit 1
fi
if [ "$(basename "$(dirname "$MODDIR")")" != "mods" ]; then
  echo "[注意] 这个 mod 文件夹不在 mods 正下方：$MODDIR" >&2
  echo "       如果它套在另一层文件夹里，把 hypernova_infinite_engine 挪到 mods/ 下面，游戏才扫得到。" >&2
fi

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)' >/dev/null 2>&1; then
      PY="$c"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "[错误] 没找到 Python 3.8 或更新版本。装好后重跑。" >&2
  exit 1
fi

echo "游戏目录: $GAME"
echo "模组目录: $MODDIR"
echo "正在扫描 mods 目录……"
"$PY" -I "$HERE/install_manifest.py" \
  --game-root "$GAME" \
  --out "$MODDIR/data/config/hypernova/manifest-v1.json"

if [ -f "$MODDIR/graphics/hypernova/blank.png" ]; then
  mkdir -p "$GAME/starsector-core/graphics/hypernova"
  cp -f "$MODDIR/graphics/hypernova/blank.png" \
        "$GAME/starsector-core/graphics/hypernova/blank.png"
fi

echo "完成。manifest 和 lazy-skip 已写入 $MODDIR/data/config/hypernova/"
