#!/usr/bin/env python3
"""Install/uninstall the optional Hypernova scripts-cache agent.

The agent line is inserted immediately after the Fast Rendering agent line, so
the transformer chain order is FR -> scripts. Writes LF line endings (argfiles
must be LF) and is idempotent. A backup is kept as *.bak-hypernova.

Backup semantics: *.bak-hypernova is a snapshot of the launch file as it was
*before the most recent install*. Every install refreshes it (including installs
that find the file already patched and change nothing else). uninstall never
consumes, deletes or restores the backup -- it only removes the agent line, and
the backup stays on disk for manual reference.
"""
import argparse
import shutil
import sys
from pathlib import Path

AGENT_LINE = "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
FR_LINE = "-javaagent:fr.agent.jar"
MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"


def launch_file(game: Path, env: str) -> Path:
    return (game / "starsector-core" / "fr.vmparams"
            if env == "base" else game / "Miko_Lite.txt")


def _assert_main_class_last(lines: list[str]) -> None:
    """P1 防御：主类之后的内容会被 JVM 当作程序参数，agent 会静默不加载。

    真实启动文件一定有主类行（base 的 fr.vmparams 末行还没有行尾换行），
    因此只要输入里出现主类，写回后它就必须仍是最后一行。合成夹具（单测、
    临时目录演练）可以没有主类行，此时无可断言。
    """
    if not any(line.strip() == MAIN_CLASS for line in lines):
        return
    if lines[-1].strip() != MAIN_CLASS:
        raise SystemExit(
            f"refusing to patch: {AGENT_LINE} would not precede the main class; "
            f"{MAIN_CLASS} must stay the last line, actual last line: {lines[-1]!r}")


def patch_lines(lines: list[str]) -> list[str]:
    if any(line.strip() == AGENT_LINE for line in lines):
        _assert_main_class_last(lines)
        return lines
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip() == FR_LINE:
            out.append(AGENT_LINE + "\n")
            inserted = True
    if not inserted:
        raise SystemExit(f"FR agent line not found; expected: {FR_LINE}")
    _assert_main_class_last(out)
    return out


def unpatch_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() != AGENT_LINE]


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def write_lf(path: Path, lines: list[str]) -> None:
    # 这里的 CRLF/CR 归一化在当前调用路径上是死代码：read_lines() 用的
    # read_text() 已做 universal-newline 翻译，进到这里时行尾只剩 "\n"。
    # 真正保证写出 LF 的是下面的 open(..., newline="\n")。保留 replace 是为了
    # 将来若改成直接读字节（如 --dry-run 走字节路径）时仍然安全。
    text = "".join(line.replace("\r\n", "\n").replace("\r", "\n") for line in lines)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--env", choices=["base", "260mods"], required=True)
    parser.add_argument("--action", choices=["install", "uninstall"], default="install")
    parser.add_argument("--jar", default="build/agent/hypernova.agent.jar")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    game = Path(args.game)
    launch = launch_file(game, args.env)
    if not launch.is_file():
        print(f"launch file not found: {launch}", file=sys.stderr)
        return 2

    lines = read_lines(launch)
    new = patch_lines(lines) if args.action == "install" else unpatch_lines(lines)

    # F-1：jar 复制必须先于 "no vmparams change" 早退。launch 文件已含 agent 行时
    # 该早退会触发，若仍在其后复制，升级（重建出新 jar 再 install）就会静默沿用旧 jar。
    # --dry-run 承诺不写盘，因此排除在外。
    jar_copied = False
    if args.action == "install" and not args.dry_run:
        jar = Path(args.jar)
        if not jar.is_file():
            print(f"agent jar not found: {jar}", file=sys.stderr)
            return 2
        dst = game / "mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jar, dst)
        print(f"installed: {dst}")
        jar_copied = True

    # 备份语义：*.bak-hypernova 是"最近一次安装前"的启动文件快照。
    # 每次 install 都用本次安装前的内容覆盖备份（不是只在首次创建）；
    # 位置必须在读完 lines、写盘之前。已打过补丁（new == lines）的早退路径
    # 也要走到这里，否则用户手动改过的启动文件不会被留档。
    # uninstall 不写、不删、不消费备份；--dry-run 承诺不写盘，因此排除。
    if args.action == "install" and not args.dry_run:
        backup = launch.with_name(launch.name + ".bak-hypernova")
        shutil.copy2(launch, backup)

    if new == lines:
        # 措辞区分：jar 已被刷新时，说 "vmparams" 无变化，避免读成"什么都没做"。
        print(f"no vmparams change: {launch}" if jar_copied else f"no change: {launch}")
        return 0
    if args.dry_run:
        print("".join(new), end="")
        return 0

    write_lf(launch, new)
    print(f"{args.action}: {launch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
