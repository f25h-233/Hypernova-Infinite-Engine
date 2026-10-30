#!/usr/bin/env bash
# 用法: bash tools/java/build-texture-patch.sh [game-dir]
# 产出: build/agent/textures/hypernova/agent/textures/{TextureData.class.bin,patch.properties}
#       build/agent/texture-original.class (测试用，不打包)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="${1:-$ROOT_W/Starsector-098-260mods}"
GLIB="$GAME/mods/GraphicsLib/jars/Graphics.jar"
CORE="$GAME/starsector-core"
OUT="$ROOT_W/build/agent/textures"
WORK="$ROOT_W/build/texture-patch"
RES="$OUT/hypernova/agent/textures"
EXPECTED_CLASS="$(tr -d '[:space:]' < "$ROOT_W/tools/java/texture-patch/expected-sha256.txt")"

if [ ! -f "$GLIB" ]; then echo "FATAL: missing $GLIB" >&2; exit 2; fi
if [ ! -f "$CORE/starfarer.api.jar" ]; then echo "FATAL: missing game jars under $CORE" >&2; exit 2; fi

rm -rf "$WORK" "$RES"
mkdir -p "$WORK/orig" "$WORK/src/org/dark/shaders/util" \
  "$WORK/src/hypernova/agent/textures" "$WORK/classes" "$RES"

unzip -p "$GLIB" org/dark/shaders/util/TextureData.java  > "$WORK/orig/TextureData.java"
unzip -p "$GLIB" org/dark/shaders/util/TextureData.class > "$WORK/orig/TextureData.class"
actual_class="$(sha256sum "$WORK/orig/TextureData.class" | cut -d' ' -f1)"
if [ "$actual_class" != "$EXPECTED_CLASS" ]; then
  echo "FATAL: TextureData.class sha256 mismatch: $actual_class != $EXPECTED_CLASS" >&2
  exit 2
fi

python "$ROOT_W/tools/java/texture_patch.py" \
  --source "$WORK/orig/TextureData.java" \
  --out    "$WORK/src/org/dark/shaders/util/TextureData.java"

# 仅供 javac 的编译期 stub：补丁类引用 agent 域的真 CacheProbe，但此时 agent
# 尚未编译。stub 只进 $WORK/classes，不复制进 $RES；运行期由 agent jar 提供真类。
cat > "$WORK/src/hypernova/agent/textures/CacheProbe.java" <<'JAVA'
package hypernova.agent.textures;

/** 编译期 stub；运行期由 agent jar 提供真类。 */
public final class CacheProbe {
    private CacheProbe() {
    }

    public static boolean has(String cachePath) {
        return false;
    }
}
JAVA

CP="$CORE/starfarer_obf.jar;$CORE/starfarer.api.jar;$CORE/lwjgl.jar;$CORE/lwjgl_util.jar;$CORE/json.jar;$CORE/log4j-1.2.9.jar;$GLIB"
javac --release 17 -encoding UTF-8 -nowarn -cp "$CP" \
  -d "$WORK/classes" \
  "$WORK/src/org/dark/shaders/util/TextureData.java" \
  "$WORK/src/hypernova/agent/textures/CacheProbe.java"

javap -verbose -cp "$WORK/classes" org.dark.shaders.util.TextureData 2>/dev/null \
  | grep -q "major version: 61" || { echo "FATAL: patched class major != 61" >&2; exit 2; }

cp "$WORK/classes/org/dark/shaders/util/TextureData.class" "$RES/TextureData.class.bin"
cp "$WORK/orig/TextureData.class" "$ROOT_W/build/agent/texture-original.class"
patched_sha="$(sha256sum "$RES/TextureData.class.bin" | cut -d' ' -f1)"
printf '%s\n' \
  'target=org/dark/shaders/util/TextureData' \
  "sourceSha256=$actual_class" \
  "patchedSha256=$patched_sha" \
  'graphicsLibVersion=1.12.1' > "$RES/patch.properties"

echo "OK: $RES/TextureData.class.bin (patched=$patched_sha)"
