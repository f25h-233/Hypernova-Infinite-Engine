#!/usr/bin/env bash
# 用法: bash tools/java/cache-tool.sh key [--verify] | inspect [key] | seed ...
#
# 必须在「与游戏启动等价的 cwd + classpath」下运行：ScriptCacheKey 把
# java.version 和 classpath 中各条目的绝对路径按顺序写进 canonical 文本，
# 所以这里的 JRE 必须是 Base 自带的 17（系统 java 是 21，key 会完全不同），
# classpath 也必须与 fr.vmparams 的 -classpath 行逐项同序。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
JAVA="$ROOT_W/Starsector-098-Base/jre/bin/java.exe"
if [ ! -x "$JAVA" ]; then
  echo "FATAL: Base JRE not found at $JAVA" >&2
  echo "        ScriptCacheKey embeds java.version into the cache key;" >&2
  echo "        system java is 21 while the game runs on 17, so the key would differ." >&2
  exit 1
fi
cd "$CORE"

# 顺序逐项照抄 fr.vmparams 的 -classpath 行（19 个 jar，见下方断言）。
CP_GAME="$CORE/fr.jar;$CORE/janino.jar;$CORE/commons-compiler.jar;$CORE/commons-compiler-jdk.jar;$CORE/starfarer.api.jar;$CORE/starfarer_obf.jar;$CORE/jogg-0.0.7.jar;$CORE/jorbis-0.0.15.jar;$CORE/json.jar;$CORE/lwjgl.jar;$CORE/jinput.jar;$CORE/log4j-1.2.9.jar;$CORE/lwjgl_util.jar;$CORE/fs.sound_obf.jar;$CORE/fs.common_obf.jar;$CORE/xstream-1.4.10.jar;$CORE/txw2-3.0.2.jar;$CORE/jaxb-api-2.4.0-b180830.0359.jar;$CORE/webp-imageio-0.1.6.jar"

# 机械核对：把 vmparams 的 -classpath 行展开成同样的绝对路径串再比较，防止手工抄错顺序。
VM_CP_LINE=$(tr -d '\r' < "$CORE/fr.vmparams" | sed -n '/^-classpath$/{n;p;}' | head -1)
EXPECTED_CP=$(printf '%s' "$VM_CP_LINE" | tr ';' '\n' | sed "s|^|$CORE/|" | paste -sd ';' -)
if [ "$CP_GAME" != "$EXPECTED_CP" ]; then
  echo "FATAL: classpath order diverges from fr.vmparams" >&2
  echo "  vmparams: $EXPECTED_CP" >&2
  echo "  script  : $CP_GAME" >&2
  exit 1
fi

# 工具自身与 agent 类放在游戏 classpath 之后；它们不在 gameRoot 下，
# ScriptCacheKey.classpathOrder 会把它们过滤掉，不参与 key。
CP="$CP_GAME;$ROOT_W/build/agent/classes;$ROOT_W/build/agent/tools-classes"

"$JAVA" -cp "$CP" \
  -Dcom.fs.starfarer.settings.paths.mods=../mods \
  -Dcom.fs.starfarer.settings.paths.saves=../saves \
  hypernova.agent.tools.CacheTool "$@"
