#!/usr/bin/env bash
# 用法: bash tools/java/build-mod.sh
# 打包成品 mod（含运行时 manifest 与 lazy-skip-v1.txt）。发行包固定使用
# Starsector-098-Base 的 M2 manifest；manifest/skip 缺失时**拒绝产出 zip**：
# 缺 manifest 的包解压后 ManifestLoader.load() 返回 null，整组件静默禁用（C1）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Git Bash/MSYS 下 javac/jar/javap 是原生 Windows 程序，不认 /d/... 路径，统一转成 D:/...
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
# 任意失败（含参数校验、agent 构建/新鲜度失败与显式 exit 1）都清掉 zip，
# 避免发布路径上残留上一次成功构建的包；INT/TERM 转成非零退出以触发清理。
OUT="$ROOT_W/build/java"
VERSION="$(python -I - "$ROOT_W/mod_info.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8"))["version"]
if isinstance(v, dict):
    print(f"{v['major']}.{v['minor']}.{v['patch']}")
else:
    print(v)
PY
)"
ZIP="$OUT/hypernova-$VERSION.zip"
cleanup_failed_zip() {
  status=$?
  if [ "$status" -ne 0 ]; then
    rm -f "$ZIP"
  fi
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup_failed_zip EXIT
rm -f "$ZIP"
# 发行包固定使用 Base manifest；旧的 --env 参数已失去意义，显式拒绝以免误以为能打 260mods 包。
if [ "$#" -gt 0 ]; then
  echo "FATAL: build-mod.sh 不再接受参数（发行包固定使用 Starsector-098-Base 的 M2 manifest）" >&2
  exit 1
fi
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
CP="$GAME/starfarer.api.jar;$GAME/json.jar;$GAME/lwjgl.jar;$GAME/log4j-1.2.9.jar"
rm -rf "$OUT/classes" "$OUT/hypernova.jar"
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
# 发行包根目录只放一层 <mod 文件夹>/。玩家把 zip 解压到 mods/ 之后得到的直接就是
# mods/hypernova_infinite_engine/。以前的包把 mod_info.json、data/、jars/ 摊在 zip
# 根目录：用"解压到当前文件夹"会把这些东西散进 mods/ 根，游戏扫不到（它只认
# mods/<文件夹>/mod_info.json），还会污染别的 mod 的目录。
MODNAME="hypernova_infinite_engine"
PKG="$OUT/pkg"
MODDIR="$PKG/$MODNAME"
rm -rf "$PKG"; mkdir -p "$MODDIR/jars" "$MODDIR/data/config/hypernova"
cp "$OUT/hypernova.jar" "$MODDIR/jars/hypernova.jar"
cp "$ROOT_W/mod_info.json" "$MODDIR/mod_info.json"
# M2.7 W6：agent jar 已在上方强制构建，无条件打包；README 说明目标机安装步骤（W5）。
cp "$AGENT_JAR" "$MODDIR/jars/hypernova.agent.jar"
cp "$ROOT_W/tools/java/README-install.txt" "$MODDIR/README-install.txt"
# 面向玩家的 manifest 生成工具。发行包里的 manifest 只能覆盖 Base 纹理集，
# 装了其它 mod 的玩家必须就地重新生成，否则主 mod 的预取对目标用户基本无效。
DIST_TOOLS="$MODDIR/hypernova-tools"
mkdir -p "$DIST_TOOLS"
for f in install_manifest.py manifest_builder.py gen_lazy_skip.py trim_manifest.py \
         validate_manifest.py image_probe.py l1_core.py mod_index.py sprite_closure.py \
         hn_json.py; do
  if [ ! -s "$ROOT_W/tools/$f" ]; then
    echo "FATAL: tools/$f 缺失或为空，manifest 生成工具不全" >&2
    exit 1
  fi
  cp "$ROOT_W/tools/$f" "$DIST_TOOLS/$f"
done
# 三支 .bat 保持纯 ASCII（中文文案在 run_*.py 里）：cmd.exe 逐字节解析批处理，
# UTF-8 中文在非 65001 代码页下会被撕成命令。这里只统一成 CRLF，对已是 CRLF 的
# checkout 幂等。
for bat in generate-manifest.bat install-agent.bat rollback-agent.bat; do
  sed -e 's/\r$//' -e 's/$/\r/' "$ROOT_W/tools/player-tools/$bat" > "$DIST_TOOLS/$bat"
done
cp "$ROOT_W/tools/player-tools/generate-manifest.sh" "$DIST_TOOLS/generate-manifest.sh"
cp "$ROOT_W/tools/player-tools/manage_agent.py" "$DIST_TOOLS/manage_agent.py"
cp "$ROOT_W/tools/player-tools/run_manifest.py" "$DIST_TOOLS/run_manifest.py"
cp "$ROOT_W/tools/player-tools/run_agent.py" "$DIST_TOOLS/run_agent.py"
cp "$ROOT_W/tools/player-tools/README-tools.txt" "$DIST_TOOLS/README-tools.txt"
# 玩家机器不一定有 Python。内置 python.org 官方 embeddable 运行时（压缩后约 11MB），
# 双击批处理零安装即可运行。版本与 SHA256 固定在 tools/player-tools/fetch_python_embed.py。
python -I "$ROOT_W/tools/player-tools/fetch_python_embed.py" >/dev/null
PY_RUNTIME="$ROOT/.cache/python-embed/runtime"
if [ ! -f "$PY_RUNTIME/python.exe" ]; then
  echo "FATAL: embeddable Python 运行时缺失（$PY_RUNTIME）" >&2
  exit 1
fi
mkdir -p "$DIST_TOOLS/python"
cp -r "$PY_RUNTIME/." "$DIST_TOOLS/python/"
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
# 用 Python 的 zipfile 打包而不是 `jar --create`：jar 会往根目录塞 META-INF/，
# 而且没法保证根目录只有 mod 文件夹这一层。
rm -f "$OUT/hypernova-$VERSION.zip"
python -I - "$MODDIR" "$OUT/hypernova-$VERSION.zip" <<'PY'
import os, sys, zipfile
from pathlib import Path

moddir = Path(sys.argv[1]).resolve()
zip_path = Path(sys.argv[2])
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(moddir):
        dirs.sort()
        rel_root = Path(root).relative_to(moddir.parent)
        if not files:
            zf.writestr(str(rel_root).replace(os.sep, "/") + "/", "")
        for name in sorted(files):
            src = Path(root) / name
            arc = str(rel_root / name).replace(os.sep, "/")
            zf.write(src, arc)
print(f"OK: zip {zip_path.name} ({zip_path.stat().st_size} bytes)")
PY
# 发行包结构门禁：根目录只能有 <mod 文件夹>/，且关键文件一个都不能少。
python -I - "$OUT/hypernova-$VERSION.zip" "$MODNAME" <<'PY'
import sys, zipfile

zip_path, mod = sys.argv[1], sys.argv[2]
names = set(zipfile.ZipFile(zip_path).namelist())
need = [
    "mod_info.json",
    "README-install.txt",
    "data/config/hypernova/manifest-v1.json",
    "data/config/hypernova/lazy-skip-v1.txt",
    "graphics/hypernova/blank.png",
    "jars/hypernova.jar",
    "jars/hypernova.agent.jar",
    "hypernova-tools/generate-manifest.bat",
    "hypernova-tools/generate-manifest.sh",
    "hypernova-tools/install-agent.bat",
    "hypernova-tools/rollback-agent.bat",
    "hypernova-tools/manage_agent.py",
    "hypernova-tools/run_manifest.py",
    "hypernova-tools/run_agent.py",
    "hypernova-tools/install_manifest.py",
    "hypernova-tools/python/python.exe",
]
bad = [f"{mod}/{n}" for n in need if f"{mod}/{n}" not in names]
roots = {n.split("/")[0] for n in names}
if roots != {mod}:
    bad.append(f"zip 根目录应当只有 {mod}/，实际是 {sorted(roots)[:5]}")
if bad:
    print("FATAL: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)
print(f"OK: zip 根目录 = {mod}/")
PY
# M2.7 W5/W6：发行包门禁（README/manifest/skip generation/宿主 v2 路径/agent 一致性/新鲜度）。
python -I "$ROOT_W/tools/release_check.py" --zip "$OUT/hypernova-$VERSION.zip" \
  --agent-jar "$AGENT_JAR" --main-jar "$OUT/hypernova.jar" \
  --sources "$ROOT_W/src/agent/java"
echo "OK: $MANIFEST_DIST (dist artifact, not tracked)"
echo "OK: $ROOT/build/java/pkg/$MODNAME"
echo "OK: $ROOT/build/java/hypernova-$VERSION.zip"
