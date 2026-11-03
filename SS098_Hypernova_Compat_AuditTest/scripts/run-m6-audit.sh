#!/usr/bin/env bash
# M6 兼容性审计：自动化侧一键复跑。
#
# 只覆盖 M6 的自动化证据（构建/测试/矩阵/manifest/日志 + 菜单 smoke）。
# 菜单 smoke **不是** 战役/战斗/读档/分辨率/中文输入验收；用户实机 gate
# 见 docs/m6-manual-acceptance.md，结果见 docs/m6-results.md §4。
#
# 运行前提：
#   - 从仓库根目录运行（Git Bash）；
#   - 已安装 Starsector-098-260mods，且其中已装好 Hypernova agent；
#   - 运行前游戏完全退出（m6_session start 需要移走日志文件）。
#
# 本脚本不修改 enabled_mods.json / hypernova.json / Miko_Lite.txt /
# settings.json，也不启用 ChineseInputFix；lazy/probe 只通过 -D 临时开启。

set -euo pipefail

GAME_ROOT="Starsector-098-260mods"
AUDIT_ROOT="SS098_Hypernova_Compat_AuditTest"
EVIDENCE="$AUDIT_ROOT/evidence"
LABEL="menu-smoke"

if [ ! -d "$GAME_ROOT" ]; then
  echo "FATAL: game root not found: $GAME_ROOT" >&2
  exit 1
fi
mkdir -p "$EVIDENCE"

echo "== Step 1.1: Java main tests"
bash tools/java/run-tests.sh

echo "== Step 1.2: Java agent tests"
bash tools/java/run-agent-tests.sh

echo "== Step 1.3: Python tools tests"
python -I -m pytest tests/tools -q

echo "== Step 1.4: Build mod"
bash tools/java/build-mod.sh

echo "== Step 1.5: Regenerate manifest/skip for $GAME_ROOT"
bash tools/java/install-manifest.sh "$GAME_ROOT"

echo "== Step 1.6: Environment matrix"
python -I tools/m6_audit_matrix.py \
  --game-root "$GAME_ROOT" \
  --out "$EVIDENCE/matrix.json"

echo "== Step 1.7: Manifest/skip generation + host pollution + fail-open"
# fail-open workdir 必须在仓库与游戏根之外，且每次唯一；旧的
# evidence/fail-open 会被工具拒绝。
FAIL_OPEN_DIR="$(mktemp -d)"
trap 'rm -rf "$FAIL_OPEN_DIR"' EXIT
python -I tools/m6_manifest_audit.py \
  --game-root "$GAME_ROOT" \
  --out "$EVIDENCE/manifest-audit.json" \
  --fail-open-dir "$FAIL_OPEN_DIR" \
  --fail-open-out "$EVIDENCE/fail-open.json"

echo "== Step 1.8: Log audit"
python -I tools/m6_log_audit.py \
  --game-root "$GAME_ROOT" \
  --out "$EVIDENCE/log-audit-current.json"

echo "== Step 2: Menu smoke (probe + lazy, real process)"
# 注意：session 产物按 m6_session 实现落在 <evidence-root>/<label>，
# 即 $AUDIT_ROOT/$LABEL/（不是 $EVIDENCE/$LABEL/）。
if [ -e "$AUDIT_ROOT/$LABEL" ]; then
  echo "FATAL: $AUDIT_ROOT/$LABEL already exists; move it aside for a fresh slice." >&2
  exit 1
fi
python -I tools/m6_session.py start \
  --game-root "$GAME_ROOT" \
  --evidence-root "$AUDIT_ROOT" \
  --label "$LABEL"

python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 20 \
  --jvm-arg=-Dhypernova.frameProbe=true \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --json-out "$EVIDENCE/menu-smoke.json"

python -I tools/m6_session.py end \
  --game-root "$GAME_ROOT" \
  --evidence-root "$AUDIT_ROOT" \
  --label "$LABEL"

echo "== Done. Check $AUDIT_ROOT/$LABEL/session.json (ok=true) and $EVIDENCE/*.json"
echo "== User gates (campaign/combat/load/resolution/IME/visual) remain pending."
