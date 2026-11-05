#!/usr/bin/env bash
# 用法: bash tools/java/build-texture-patch.sh [--core <starsector-core>] [--variant <version>=<Graphics.jar>]...
# 产出: build/agent/textures/hypernova/agent/textures/{variants.properties,v/<sourceSha>.class.bin}
#       build/agent/texture-original-<sourceSha>.class (测试用，不打包)
#
# 每个受支持的 GraphicsLib 版本各产出一个预编译补丁类；运行时按加载到的
# TextureData.class 的 SHA-256 精确匹配。没有变体 = 失败，绝不生成半成品。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
JAVAC="${JAVAC:-javac}"

CORE=""
declare -a VARIANTS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --core) CORE="$2"; shift 2 ;;
    --variant) VARIANTS+=("$2"); shift 2 ;;
    *) echo "FATAL: unknown argument: $1" >&2; exit 2 ;;
  esac
done

CONF="$ROOT_W/tools/java/texture-patch/variants.conf"
if [ ${#VARIANTS[@]} -eq 0 ] && [ -f "$CONF" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    VARIANTS+=("$line")
  done < "$CONF"
fi
if [ ${#VARIANTS[@]} -eq 0 ]; then
  echo "FATAL: no variants (edit $CONF or pass --variant <version>=<jar>)" >&2
  exit 2
fi
if [ -z "$CORE" ]; then CORE="$ROOT_W/Starsector-098-Base/starsector-core"; fi
if [ ! -f "$CORE/starfarer.api.jar" ]; then echo "FATAL: missing game jars under $CORE" >&2; exit 2; fi

resolve() { case "$1" in /*|[A-Za-z]:*) printf '%s' "$1" ;; *) printf '%s/%s' "$ROOT_W" "$1" ;; esac; }

OUT="$ROOT_W/build/agent/textures"
RES="$OUT/hypernova/agent/textures"
VDIR="$RES/v"
WORK="$ROOT_W/build/texture-patch"
rm -rf "$RES" "$WORK"
mkdir -p "$VDIR" "$WORK"

# 仅供 javac 的编译期 stub：补丁类引用 agent 域的真 CacheProbe，但此时 agent
# 尚未编译。stub 只进 $WORK/classes，不复制进 $RES；运行期由 agent jar 提供真类。
mkdir -p "$WORK/stub/hypernova/agent/textures"
cat > "$WORK/stub/hypernova/agent/textures/CacheProbe.java" <<'JAVA'
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

sha_of() { sha256sum "$1" | cut -d' ' -f1; }
index=0
declare -a INDEX_LINES=()
declare -A SEEN=()

for spec in "${VARIANTS[@]}"; do
  version="${spec%%=*}"
  rest="${spec#*=}"
  jar_spec="${rest%%|*}"
  src_spec=""
  if [ "$rest" != "$jar_spec" ]; then src_spec="${rest#*|}"; fi
  if [ "$version" = "$spec" ]; then echo "FATAL: bad variant spec: $spec" >&2; exit 2; fi
  GLIB="$(resolve "$jar_spec")"
  if [ ! -f "$GLIB" ]; then echo "FATAL: missing GraphicsLib jar for $version: $GLIB" >&2; exit 2; fi

  VWORK="$WORK/$version"
  mkdir -p "$VWORK/orig" "$VWORK/src/org/dark/shaders/util" "$VWORK/classes"
  unzip -p "$GLIB" org/dark/shaders/util/TextureData.class > "$VWORK/orig/TextureData.class"
  actual_class="$(sha_of "$VWORK/orig/TextureData.class")"

  if [ -n "${SEEN[$actual_class]:-}" ]; then
    echo "note: $version shares TextureData.class with ${SEEN[$actual_class]}; keeping the first label"
    continue
  fi

  # 源码优先取 jar 内嵌的 .java（1.12.1 有）；没有就用显式 source（1.12.2 起 jar 不带源码）。
  if unzip -l "$GLIB" org/dark/shaders/util/TextureData.java >/dev/null 2>&1 \
      && unzip -p "$GLIB" org/dark/shaders/util/TextureData.java > "$VWORK/orig/TextureData.java" 2>/dev/null \
      && [ -s "$VWORK/orig/TextureData.java" ]; then
    src_origin="jar"
  elif [ -n "$src_spec" ]; then
    SRC="$(resolve "$src_spec")"
    if [ ! -f "$SRC" ]; then echo "FATAL: missing TextureData.java for $version: $SRC" >&2; exit 2; fi
    cp "$SRC" "$VWORK/orig/TextureData.java"
    src_origin="file"
  else
    echo "FATAL: $version jar ships no TextureData.java; provide '<version>=<jar>|<source.java>'" >&2
    exit 2
  fi

  expected_src="$(grep -E "^$version[[:space:]]" "$ROOT_W/tools/java/texture-patch/sources.sha256" 2>/dev/null | awk '{print $2}')"
  if [ -z "$expected_src" ]; then
    echo "FATAL: no pinned source sha256 for $version in tools/java/texture-patch/sources.sha256" >&2
    exit 2
  fi
  actual_src="$(sha_of "$VWORK/orig/TextureData.java")"
  if [ "$actual_src" != "$expected_src" ]; then
    echo "FATAL: $version TextureData.java sha256 mismatch: $actual_src != $expected_src" >&2
    exit 2
  fi

  python "$ROOT_W/tools/java/texture_patch.py" \
    --source "$VWORK/orig/TextureData.java" \
    --out    "$VWORK/src/org/dark/shaders/util/TextureData.java" \
    --expect-source-sha "$expected_src"

  CP="$CORE/*;$GLIB"
  javac_bin="$JAVAC"
  # 先编译未打补丁的源码：能逐字节复现厂商 class 就说明源码与编译器都对齐。
  mkdir -p "$VWORK/ref"
  "$javac_bin" --release 17 -encoding UTF-8 -nowarn -cp "$CP" -d "$VWORK/ref" \
    "$VWORK/orig/TextureData.java" 2>/dev/null || true
  reproducible=no
  if [ -f "$VWORK/ref/org/dark/shaders/util/TextureData.class" ] \
      && [ "$(sha_of "$VWORK/ref/org/dark/shaders/util/TextureData.class")" = "$actual_class" ]; then
    reproducible=yes
  fi

  "$javac_bin" --release 17 -encoding UTF-8 -nowarn -cp "$CP" -d "$VWORK/classes" \
    "$VWORK/src/org/dark/shaders/util/TextureData.java" \
    "$WORK/stub/hypernova/agent/textures/CacheProbe.java"

  javap -verbose -cp "$VWORK/classes" org.dark.shaders.util.TextureData 2>/dev/null \
    | grep -q "major version: 61" || { echo "FATAL: $version patched class major != 61" >&2; exit 2; }

  # 合成类守卫：javac 会把 switch-on-enum 编译进 TextureData$1 之类的外围类。
  # 补丁只替换 TextureData 本体，运行期加载的是 jar 里的合成类，所以补丁编译出来的
  # 合成类必须与厂商版语义一致，否则 switch 映射会错位（静默走错分支）。
  for extra in "$VWORK/classes/org/dark/shaders/util"/TextureData\$*.class; do
    [ -e "$extra" ] || continue
    extra_name="$(basename "$extra")"
    if ! unzip -p "$GLIB" "org/dark/shaders/util/$extra_name" > "$VWORK/orig/$extra_name" 2>/dev/null; then
      echo "FATAL: $version patched compile produced $extra_name missing from the vendor jar" >&2
      exit 2
    fi
    if ! diff -q <(javap -p -c -cp "$VWORK/classes" "org.dark.shaders.util.${extra_name%.class}") \
                 <(javap -p -c "$VWORK/orig/$extra_name") >/dev/null 2>&1; then
      echo "FATAL: $version $extra_name differs semantically from the vendor jar (switch map drift)" >&2
      exit 2
    fi
  done

  cp "$VWORK/classes/org/dark/shaders/util/TextureData.class" "$VDIR/$actual_class.class.bin"
  cp "$VWORK/orig/TextureData.class" "$ROOT_W/build/agent/texture-original-$actual_class.class"
  patched_sha="$(sha_of "$VDIR/$actual_class.class.bin")"
  SEEN[$actual_class]="$version"

  INDEX_LINES+=("variant.$index.graphicsLibVersion=$version"
                "variant.$index.sourceSha256=$actual_class"
                "variant.$index.patchedSha256=$patched_sha"
                "variant.$index.resource=/hypernova/agent/textures/v/$actual_class.class.bin")
  index=$((index + 1))
  echo "variant $version: shipped=$actual_class source-from=$src_origin reproducible=$reproducible patched=$patched_sha"
done

if [ "$index" -eq 0 ]; then echo "FATAL: no variants built" >&2; exit 2; fi

{
  printf 'format=1\ncount=%d\n' "$index"
  printf '%s\n' "${INDEX_LINES[@]}"
} > "$RES/variants.properties"

echo "OK: $RES/variants.properties ($index variant(s))"
