#!/usr/bin/env bash
# 最终冒烟准备：用 HEAD 产物构建并安装，临时开启自检，清掉上一轮日志。
# 用法: bash tools/java/smoke-prepare.sh [game-root]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_ROOT="${1:-$ROOT/Starsector-098-Base}"
CFG="$ROOT/data/config/hypernova/hypernova.json"
INSTALLED_CFG="$GAME_ROOT/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json"

echo "== 1. 构建（含 manifest 打包） =="
bash "$ROOT/tools/java/build-mod.sh" | tail -2

echo "== 2. 临时开启自检（验证 REQ-R1-01 用，跑完由 smoke-restore.sh 还原） =="
python -I - "$CFG" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["startup_probe_paths"] = 8
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("startup_probe_paths = 8")
PY

echo "== 3. 安装到游戏目录 =="
bash "$ROOT/tools/java/install-manifest.sh" "$GAME_ROOT" --env base | tail -3

echo "== 4. 清上一轮证据 =="
mv "$GAME_ROOT/starsector-core/starsector.log" \
   "$GAME_ROOT/starsector-core/starsector.log.prev-$(date +%s)" 2>/dev/null || true
rm -f "$GAME_ROOT/saves/common/hypernova/telemetry.jsonl.data"
echo "old log rotated, telemetry cleared"

echo "== 5. 前置断言 =="
python -I - "$GAME_ROOT" <<'PY'
import json, sys
from pathlib import Path
g = Path(sys.argv[1])
en = json.loads((g / "mods/enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
assert "hypernova_infinite_engine" in en, "hypernova not enabled"
mod = g / "mods/hypernova_infinite_engine"
for rel in ("data/config/hypernova/manifest-v1.json", "jars/hypernova.jar",
            "data/config/hypernova/hypernova.json"):
    assert (mod / rel).is_file(), f"missing {rel}"
cfg = json.loads((mod / "data/config/hypernova/hypernova.json").read_text(encoding="utf-8"))
assert cfg["startup_probe_paths"] == 8, f"probe not set: {cfg}"
print(f"ok: enabled={len(en)} mods, manifest+jar+config present, probe={cfg['startup_probe_paths']}")
PY

echo
echo "准备完成。启动游戏后进生涯模式到星系，然后跑:"
echo "  python -I tools/java/smoke-check.py --game $GAME_ROOT"
