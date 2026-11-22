#!/usr/bin/env python3
"""Tell the player whether Hypernova is actually working, in plain language.

Players are not going to open `starsector.log` and grep for strings, so this
script does the reading for them and prints a short checklist. It never writes
anything: it only inspects the launch file, the agent jar, and the two logs the
runtime leaves behind.

Exit codes: 0 = everything it can check is fine, 1 = something is wrong.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import setup_agent as sa  # noqa: E402

OK = "  [OK]   "
BAD = "  [!!]   "
WARN = "  [??]   "

AGENT_RE = re.compile(r"-javaagent:[^\s\"]*hypernova\.agent\.jar")


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def ok(self, text: str, detail: str = "") -> None:
        print(OK + text)
        if detail:
            print("         " + detail)

    def bad(self, text: str, fix: str = "") -> None:
        self.failed += 1
        print(BAD + text)
        if fix:
            print("         怎么修：" + fix)

    def warn(self, text: str, detail: str = "") -> None:
        print(WARN + text)
        if detail:
            print("         " + detail)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_launch(game: Path) -> tuple[str, Path] | None:
    """Return (route, path) for whichever launch file this install uses."""
    for route, path in ((sa.ROUTE_B, game / "Miko_Simple.txt"),
                        (sa.ROUTE_A, game / "vmparams")):
        if not path.is_file():
            continue
        text = read(path)
        try:
            return sa.detect_route(text), path
        except sa.SetupError:
            continue
    return None


def check_agent(r: Report, game: Path) -> None:
    print("\n[1/5] 启动参数里的 Hypernova")
    found = find_launch(game)
    if found is None:
        r.bad("找不到启动文件（Miko_Simple.txt 或 vmparams）",
              "确认你选对了游戏目录，或者先按教程装好 FR / MixinFR")
        return
    route, path = found
    text = read(path)
    problems = sa.verify(text, route)
    if not problems:
        r.ok(f"已装好，顺序正确（{path.name}）")
    elif any("missing" in p for p in problems):
        r.bad("Hypernova 的启动参数没装",
              "双击 hypernova-tools\\setup-agent.bat")
    else:
        for p in problems:
            r.bad(p, "双击 hypernova-tools\\setup-agent.bat 重新装一次")


def check_jar(r: Report, game: Path) -> None:
    print("\n[2/5] Hypernova 本体文件")
    jar = game / "mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
    main = game / "mods/hypernova_infinite_engine/jars/hypernova.jar"
    if jar.is_file() and main.is_file():
        r.ok("mod 文件齐全")
    else:
        missing = [p.name for p in (jar, main) if not p.is_file()]
        r.bad("缺文件：" + "、".join(missing),
              "把 hypernova_infinite_engine 整个文件夹放进 mods\\ 里")


def check_agent_log(r: Report, game: Path) -> None:
    print("\n[3/5] 上次启动时 Hypernova 有没有真的跑起来")
    log = game / "saves/hypernova/scripts-agent.log"
    if not log.is_file():
        r.warn("还没跑过游戏（没有日志）", "先启动一次游戏，再双击这个检查")
        return
    text = read(log)
    # 只看最后一次 premain 之后的内容，避免旧会话误判
    idx = text.rfind("hypernova agent premain")
    if idx < 0:
        r.bad("Hypernova 启动时没加载",
              "启动参数没生效。双击 hypernova-tools\\setup-agent.bat")
        return
    tail = text[idx:]
    r.ok("Hypernova 已加载")
    if "scripts cache transformer registered" in tail:
        r.ok("脚本缓存已接管")
    else:
        r.warn("脚本缓存没接管", "可能被版本门禁关掉了")

    if "textures: patched" in tail:
        r.ok("纹理补丁已生效（GraphicsLib 缓存）")
    elif "textures: unsupported GraphicsLib TextureData" in tail:
        if "MixinFR" in text or (game / "mods/MixinFR").is_dir():
            r.warn("纹理补丁没生效（MixinFR 的正常现象，不是故障）",
                   "路线 A 本来就没有这一项，不用管")
        else:
            r.warn("纹理补丁没生效（GraphicsLib 版本不在支持列表）",
                   "升级 Hypernova 到最新版试试")
    elif "textures: patch resources loaded" in tail:
        r.warn("纹理补丁资源已加载，但没看到生效记录", "通常无害；有异常再来问")

    if "file index: disabled" in tail:
        r.warn("文件索引被关掉了（FR 版本不支持）", "路线 A 的正常现象")
    elif "file index: loaded" in tail or "file index: written" in tail:
        r.ok("文件索引已生效")
    elif "file index transformer registered" in tail:
        r.warn("文件索引已注册，但还没建过索引", "再启动一次看看")


def check_game_log(r: Report, game: Path) -> None:
    print("\n[4/5] 游戏本身有没有正常启动")
    log = game / "starsector-core/starsector.log"
    if not log.is_file():
        r.warn("还没有游戏日志", "先启动一次游戏")
        return
    text = read(log)
    if "Playing music with id [miscallenous_main_menu.ogg]" in text:
        r.ok("上次启动成功进到了主菜单")
    elif "OutOfMemoryError" in text:
        r.bad("上次启动内存不够", "在配置器里把内存调大一档")
    elif "Error opening zip file" in text or "JAR manifest missing" in text:
        r.bad("启动参数指向的 jar 不对", "双击 setup-agent.bat 重新装一次")
    else:
        r.warn("没找到「进到主菜单」的记录", "如果游戏能玩就忽略这一条")

    for line in re.findall(r"Java version: ([0-9].*)", text)[:1]:
        print("         游戏用的 Java 版本：" + line.strip())


def check_mods(r: Report, game: Path) -> None:
    print("\n[5/5] mod 清单")
    p = game / "mods/enabled_mods.json"
    if not p.is_file():
        r.warn("找不到 enabled_mods.json（还没在启动器里勾过 mod）")
        return
    text = read(p)
    if "hypernova_infinite_engine" in text:
        r.ok("Hypernova 已在启用列表里")
    else:
        r.bad("Hypernova 没被勾选", "在游戏启动器的 Mod 列表里勾上 Hypernova")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game", required=True, help="Starsector 安装根目录")
    args = ap.parse_args()

    game = Path(args.game)
    if not game.is_dir():
        print(f"找不到这个目录：{game}")
        return 1

    print("=" * 60)
    print(" Hypernova 安装自检")
    print("=" * 60)
    print(f" 游戏目录：{game}")

    r = Report()
    check_agent(r, game)
    check_jar(r, game)
    check_agent_log(r, game)
    check_game_log(r, game)
    check_mods(r, game)

    print("\n" + "=" * 60)
    if r.failed == 0:
        print(" 结论：可以玩。上面打 [??] 的是提醒，不影响使用。")
    else:
        print(f" 结论：有 {r.failed} 项要修，按上面的提示做。")
        print(" 修完再双击这个文件检查一次。")
    print("=" * 60)
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
