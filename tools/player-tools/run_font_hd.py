"""玩家侧入口：还原 Hypernova 高清字体桥覆盖过的字体文件。

中文文案放在 Python 里，.bat 只负责找 Python 和转发参数。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import manage_font_hd  # noqa: E402


def _pause(prompt: str = "按回车键关闭这个窗口…") -> None:
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        pass


def main(argv: list[str] | None = None) -> int:
    print("=" * 62)
    print(" Hypernova 无限引擎 — 还原高清字体覆盖")
    print("=" * 62)
    print()
    print("这个操作会把 graphics\\fonts\\ 下的")
    print("*.bak-hypernova-hd 备份复制回原文件名，然后删除备份。")
    print("适用于优化测试版想回到原版字体、或覆盖后字体异常的情况。")
    print("删掉 agent 的 -javaagent 行之后，这个还原才是永久的；")
    print("否则下次启动 agent 会重新生成并覆盖。")
    print()
    code = manage_font_hd.main(["--action", "restore"])
    print()
    _pause()
    return code


if __name__ == "__main__":
    sys.exit(main())
