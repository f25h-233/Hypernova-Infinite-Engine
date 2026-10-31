#!/usr/bin/env bash
# 冒烟后还原：把自检开关关掉并重装，使发布态配置回到默认（startup_probe_paths = 0）。
# 用法: bash tools/java/smoke-restore.sh [game-root]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_ROOT="${1:-$ROOT/Starsector-098-Base}"
CFG="$ROOT/data/config/hypernova/hypernova.json"

python -I - "$CFG" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["startup_probe_paths"] = 0
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("startup_probe_paths = 0")
PY

bash "$ROOT/tools/java/build-mod.sh" | tail -1
bash "$ROOT/tools/java/install-manifest.sh" "$GAME_ROOT" --env base | tail -2
# install-manifest.sh 装的是 M0 manifest；立即重跑 M2 安装器把运行时 manifest 写回。
python -I "$ROOT/tools/install_manifest.py" --game-root "$GAME_ROOT" | tail -3
echo "restored: released config has startup_probe_paths=0; M2 runtime manifest reinstalled"
