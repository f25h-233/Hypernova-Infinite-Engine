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
bash "$ROOT/tools/java/install-manifest.sh" "$GAME_ROOT" | tail -3
# 断言恢复后 manifest 与 skip 都在位（install-manifest.sh 已由 M2 安装器生成两者）。
python -I - "$GAME_ROOT" <<'PY'
import sys
from pathlib import Path
mod = Path(sys.argv[1]) / "mods/hypernova_infinite_engine/data/config/hypernova"
for name in ("manifest-v1.json", "lazy-skip-v1.txt"):
    assert (mod / name).is_file(), f"missing {name}"
print("ok: M2 runtime manifest + lazy-skip present")
PY
echo "restored: released config has startup_probe_paths=0; M2 runtime manifest+skip reinstalled"
