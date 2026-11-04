"""玩家侧入口：双击批处理实际调用的就是它。

为什么中文提示不放在 .bat 里：cmd.exe 逐字节解析批处理文件，UTF-8 的中文在
非 65001 代码页下会被撕碎，甚至把半行当成命令去执行（线上已经出现过
`'没效果。' is not recognized as an internal or external command`）。
Python 是在运行时按控制台代码页编码输出，不存在这个问题，所以所有面向玩家的
文案都放在这里，.bat 保持纯 ASCII。
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOD_ROOT = HERE.parent

sys.path.insert(0, str(HERE))


def find_game_root(start: Path) -> Path | None:
    """从 mod 目录往上找含 starsector-core 的祖先。

    不假定固定层数：正常是 mods/<mod>/，解压时多套一层（mods/x/<mod>/）也能认出来，
    不然玩家只会看到"没找到游戏目录"。
    """
    for cand in start.parents:
        if (cand / "starsector-core").is_dir():
            return cand
    return None


GAME_ROOT = find_game_root(MOD_ROOT)

import install_manifest as im  # noqa: E402

OUT_REL = Path("data") / "config" / "hypernova" / "manifest-v1.json"


def _pause() -> None:
    try:
        input("按回车键关闭这个窗口…")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    print("=" * 62)
    print(" Hypernova 无限引擎 — 按你的游戏目录重新生成 manifest")
    print("=" * 62)
    print()

    if GAME_ROOT is None or not (MOD_ROOT / "mod_info.json").is_file():
        print("[错误] 没找到游戏目录。")
        print(f"       从 {MOD_ROOT} 往上找，没有哪一层下面有 starsector-core 文件夹。")
        print("       请把整个 mod 文件夹放在 游戏目录\\mods\\ 下面，再运行这个脚本。")
        print()
        _pause()
        return 1

    if MOD_ROOT.parent.name.casefold() != "mods":
        print(f"[注意] 这个 mod 文件夹不在 mods 正下方：{MOD_ROOT}")
        print("       如果它是套在另一个文件夹里（比如 解压出来的 hypernova-1.9.3\\hypernova_infinite_engine\\），")
        print("       把里面这层 hypernova_infinite_engine 直接挪到 mods\\ 下面，游戏才扫得到。")
        print()

    print(f"游戏目录：{GAME_ROOT}")
    print(f"模组目录：{MOD_ROOT}")
    print()
    print("正在扫描 mods 目录。mod 多的话要一两分钟，屏幕不动是在干活，别关窗口。")
    print()

    target = MOD_ROOT / OUT_REL
    try:
        code = im.main(["--game-root", str(GAME_ROOT), "--out", str(target)])
    except Exception:
        print()
        print("[失败] 生成过程报错了，上面的信息就是原因。")
        print("       游戏不会因此坏掉，原来的 manifest 还在，最多是预取没效果。")
        print("       把这段报错复制到帖子下面，我看看。")
        print()
        traceback.print_exc()
        _pause()
        return 1

    if code != 0:
        print()
        print("[失败] 清单没写成功（原因见上面几行）。")
        print("       游戏照常能玩，只是主 mod 的预取效果会打折。")
        print("       把上面的信息复制到帖子下面，我看看。")
        print()
        _pause()
        return code

    blank_src = MOD_ROOT / "graphics" / "hypernova" / "blank.png"
    if blank_src.is_file():
        blank_dst = GAME_ROOT / "starsector-core" / "graphics" / "hypernova" / "blank.png"
        try:
            blank_dst.parent.mkdir(parents=True, exist_ok=True)
            blank_dst.write_bytes(blank_src.read_bytes())
        except OSError:
            pass  # 占位图只影响懒加载，复制不了也不该打断整个流程

    print()
    print("=" * 62)
    print(" 完成。重启游戏即可。")
    print(f" 新清单已经写进 {target.parent}")
    print("=" * 62)
    print()
    _pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
