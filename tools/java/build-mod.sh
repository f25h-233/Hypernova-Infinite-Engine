#!/usr/bin/env bash
# 用法: bash tools/java/build-mod.sh
# 打包成品 mod（含运行时 manifest 与 lazy-skip-v1.txt）。发行包固定使用
# Starsector-098-Base 的 M2 manifest；manifest/skip 缺失时**拒绝产出 zip**：
# 缺 manifest 的包解压后 ManifestLoader.load() 返回 null，整组件静默禁用（C1）。
set -euo pipefail
# 发行包固定使用 Base manifest；旧的 --env 参数已失去意义，显式拒绝以免误以为能打 260mods 包。
if [ "$#" -gt 0 ]; then
  echo "FATAL: build-mod.sh 不再接受参数（发行包固定使用 Starsector-098-Base 的 M2 manifest）" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Git Bash/MSYS 下 javac/jar/javap 是原生 Windows 程序，不认 /d/... 路径，统一转成 D:/...
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
# M2.7 W6：发行前强制重建 agent jar，避免把旧代理打进包里；随后校验新鲜度。
AGENT_JAR="$ROOT_W/build/agent/hypernova.agent.jar"
bash "$ROOT_W/tools/java/build-agent.sh" >/dev/null
if [ ! -s "$AGENT_JAR" ]; then
  echo "FATAL: agent jar missing after build-agent.sh" >&2
  exit 1
fi
if find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*' -newer "$AGENT_JAR" | grep -q .; then
  echo "FATAL: agent jar is older than agent sources (stale build)" >&2
  exit 1
fi
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

# ---- 运行时 manifest + lazy-skip：由 M2 安装器从 Base 安装生成 ----
# 发行包固定使用 Base 的 manifest；260mods 等测试安装由 install-manifest.sh
# 在目标游戏目录就地生成，不再从 build/m0 取预生成 manifest。
BASE_GAME="$ROOT_W/Starsector-098-Base"
python -I "$ROOT_W/tools/install_manifest.py" --game-root "$BASE_GAME" | tail -5
MANIFEST_INSTALLED="$BASE_GAME/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json"
SKIP_INSTALLED="$BASE_GAME/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt"
MANIFEST_DIST="$ROOT/dist/manifest-v1.json"
# dist/ 被 .gitignore 忽略，干净 checkout 下不存在；先建目录再复制。
mkdir -p "$ROOT/dist"
cp "$MANIFEST_INSTALLED" "$MANIFEST_DIST"
cp "$MANIFEST_INSTALLED" "$OUT/hypernova-manifest-v1.json"

# ---- 打包成品 mod 目录与 zip ----
MODDIR="$OUT/hypernova-mod"
rm -rf "$MODDIR"; mkdir -p "$MODDIR/jars" "$MODDIR/data/config/hypernova"
cp "$OUT/hypernova.jar" "$MODDIR/jars/hypernova.jar"
cp "$ROOT_W/mod_info.json" "$MODDIR/mod_info.json"
# M2.7 W6：agent jar 已在上方强制构建，无条件打包；README 说明目标机安装步骤（W5）。
cp "$AGENT_JAR" "$MODDIR/jars/hypernova.agent.jar"
cp "$ROOT_W/tools/java/README-install.txt" "$MODDIR/README-install.txt"
# 注意 `cp -r data/. <dst>` 而不是 `cp -r data <dst>`：后者在 dst 存在时会嵌套成 data/data/。
mkdir -p "$MODDIR/data"
cp -r "$ROOT_W/data/." "$MODDIR/data/"
mkdir -p "$MODDIR/graphics"
cp -r "$ROOT_W/graphics/." "$MODDIR/graphics/"
cp "$OUT/hypernova-manifest-v1.json" "$MODDIR/data/config/hypernova/manifest-v1.json"
cp "$SKIP_INSTALLED" "$MODDIR/data/config/hypernova/lazy-skip-v1.txt"
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
if ! (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'data/config/hypernova/lazy-skip-v1.txt'; then
  echo "FATAL: zip 缺少 data/config/hypernova/lazy-skip-v1.txt" >&2
  exit 1
fi
if ! (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'graphics/hypernova/blank.png'; then
  echo "FATAL: zip 缺少 graphics/hypernova/blank.png" >&2
  exit 1
fi
if [ -f "$MODDIR/jars/hypernova.agent.jar" ]; then
  (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'jars/hypernova.agent.jar' \
    || { echo "FATAL: zip 缺少 jars/hypernova.agent.jar" >&2; exit 1; }
fi
# M2.7 W5/W6：发行包门禁（README/manifest/skip generation/宿主 v2 路径/agent 一致性/新鲜度）。
python -I "$ROOT_W/tools/release_check.py" --zip "$OUT/hypernova-0.1.0.zip" \
  --agent-jar "$AGENT_JAR" --sources "$ROOT_W/src/agent/java"
echo "OK: $MANIFEST_DIST (dist artifact, not tracked)"
echo "OK: $ROOT/build/java/hypernova-mod"
echo "OK: $ROOT/build/java/hypernova-0.1.0.zip"
