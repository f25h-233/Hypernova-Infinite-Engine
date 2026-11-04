#!/usr/bin/env python3
"""给玩家用的一键安装 / 一键回滚脚本，管的是启动文件里那一行 -javaagent。

为什么要有回滚：-javaagent 指向的 jar 不存在或损坏时，JVM 会直接拒绝启动，
玩家连启动器和 Mod 管理都进不去，只能手改启动文件。所以回滚必须是最笨的
一步操作，不依赖游戏、不依赖任何参数。

设计约束：
- 不改动除启动文件以外的任何东西，每改一个文件都留 *.bak-hypernova* 备份。
- 安装：把任意含 hypernova.agent.jar 的旧行先全删掉，再在 FR 的 agent 行
  之前插入规范的一行（没有 FR 行就插在主类之前）。重复执行不会产生重复行。
- 回滚：把所有候选文本文件里含 hypernova.agent.jar 的行删掉，不管它在哪个
  启动文件里、也不管当前 jar 还在不在。找不到就什么也不做，照样退出 0。
- 写回统一用 LF：argfile 必须是 LF，CRLF 会让 JVM 把参数吞掉或报错。

用法：
    python -I manage_agent.py --action install
    python -I manage_agent.py --action rollback
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

MARKER = "hypernova.agent.jar"
FR_MARKER = "fr.agent.jar"
MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"
AGENT_REL = Path("jars") / "hypernova.agent.jar"
MAX_BYTES = 512 * 1024


def here() -> tuple[Path, Path | None]:
    """返回 (mod 目录, 游戏目录)。

    游戏目录靠"往上找带 starsector-core 的祖先"确定，不假定固定层数：
    玩家把 zip 解压成 mods/hypernova-1.9.3/hypernova_infinite_engine/ 也能认出来。
    """
    tool_dir = Path(__file__).resolve().parent
    mod_root = tool_dir.parent
    for cand in mod_root.parents:
        if (cand / "starsector-core").is_dir():
            return mod_root, cand
    return mod_root, None


def is_text(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return False
        head = path.open("rb").read(4096)
    except OSError:
        return False
    return b"\x00" not in head


def candidates(game: Path) -> list[Path]:
    """启动参数文件的候选集：游戏根目录的 *.txt / *.vmparams，starsector-core 下的同类文件。"""
    out: list[Path] = []
    roots = [game, game / "starsector-core"]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ("", ".txt", ".vmparams"):
                continue
            if is_text(path):
                out.append(path)
    return out


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def write_lf(path: Path, lines: list[str]) -> None:
    text = "".join(line.replace("\r\n", "\n").replace("\r", "\n") for line in lines)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def backup(path: Path, stamp: str) -> Path:
    dst = path.with_name(f"{path.name}.bak-hypernova-{stamp}")
    if not dst.exists():
        shutil.copy2(path, dst)
    return dst


def canonical_line(mod_root: Path, game_root: Path) -> str:
    # 启动脚本的工作目录是 starsector-core，路径按它算相对路径，
    # 这样 mod 文件夹叫什么名字、套了几层都不用管。
    rel = os.path.relpath(mod_root / AGENT_REL, game_root / "starsector-core")
    return "-javaagent:" + Path(rel).as_posix()


def patch(lines: list[str], canonical: str) -> list[str] | None:
    """删掉所有旧 agent 行，再插一行规范的。找不到锚点返回 None。

    锚点优先级：FR 的 -javaagent 行 > 主类所在的行。主类这一档允许行内包含
    （有些启动文件把整份参数挤成一行，主类在行中间），插在那一行之前即可，
    JVM 只要求 -javaagent 出现在主类 token 之前。
    """
    body = [line for line in lines if MARKER not in line]
    anchor = None
    for i, line in enumerate(body):
        if FR_MARKER in line and line.lstrip().startswith("-javaagent:"):
            anchor = i
            break
    if anchor is None:
        for i, line in enumerate(body):
            if MAIN_CLASS in line:
                anchor = i
                break
    if anchor is None:
        return None
    out = body[:anchor] + [canonical + "\n"] + body[anchor:]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--action", choices=["install", "rollback"], default="install")
    ap.add_argument("--game-root", type=Path)
    ap.add_argument("--mod-root", type=Path)
    args = ap.parse_args(argv)

    default_mod, default_game = here()
    mod_root = (args.mod_root or default_mod).resolve()
    game_arg = args.game_root or default_game
    game = game_arg.resolve() if game_arg is not None else None

    jar = mod_root / AGENT_REL
    if game is None or not (game / "starsector-core").is_dir():
        print("[错误] 没找到游戏目录。")
        print(f"       从 {mod_root} 往上找，没有哪一层下面有 starsector-core 文件夹。")
        print("       请把整个 mod 文件夹放在 游戏目录\\mods\\ 下再运行。")
        return 1
    if not mod_root.is_dir():
        print(f"[错误] 找不到 mod 目录：{mod_root}")
        return 1

    files = candidates(game)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    if args.action == "install":
        import zipfile

        if not jar.is_file() or not zipfile.is_zipfile(jar):
            print(f"[错误] agent 文件缺失或损坏：{jar}")
            print("       没有动任何启动文件。重新解压一次压缩包再试。")
            return 1
        canonical = canonical_line(mod_root, game)
        changed = 0
        already = 0
        unanchored: list[Path] = []
        for path in files:
            lines = read_lines(path)
            text = "".join(lines)
            if MAIN_CLASS not in text:
                continue
            new = patch(lines, canonical)
            if new is None:
                unanchored.append(path)
                continue
            if new == lines:
                already += 1
                continue
            bak = backup(path, stamp)
            write_lf(path, new)
            changed += 1
            print(f"  已写入：{path}")
            print(f"  备份：  {bak}")
        print()
        if changed == 0:
            if already:
                print("已经装好了，不需要重复安装。")
                return 0
            print("没找到能改的启动文件。")
            for path in unanchored:
                print(f"  认不出该往哪插：{path}")
            print("把 hypernova-tools\\README-tools.txt 和你的启动文件发到帖子里，我看看。")
            return 1
        print(f"完成，改了 {changed} 个启动文件。重启游戏生效。")
        print(f"jar 路径：{canonical.split(':', 1)[1]}")
        print()
        print("如果之后游戏起不来，双击同目录下的 rollback-agent.bat 就能退回去。")
        return 0

    # rollback：不看主类，只要是含 agent 行的文本文件都清掉
    changed = 0
    for path in files:
        lines = read_lines(path)
        if not any(MARKER in line for line in lines):
            continue
        new = [line for line in lines if MARKER not in line]
        bak = backup(path, stamp)
        write_lf(path, new)
        changed += 1
        print(f"  已清理：{path}")
        print(f"  备份：  {bak}")
    print()
    if changed == 0:
        print("没找到任何带 Hypernova agent 的启动文件，已经是干净的。")
        print("如果游戏仍然起不来，可能是别的原因，把 starsector-core\\starsector.log 发到帖子里。")
    else:
        print(f"回滚完成，清理了 {changed} 个启动文件。现在直接启动游戏就行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
