"""玩家侧入口：安装 / 回滚可选 agent。

同 run_manifest.py：中文文案全在 Python 里，.bat 只负责找 Python 和转发参数。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import manage_agent  # noqa: E402


def _pause(prompt: str = "按回车键关闭这个窗口…") -> None:
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        pass


def install() -> int:
    print("=" * 62)
    print(" Hypernova 无限引擎 — 安装可选组件 agent")
    print("=" * 62)
    print()
    print("这个操作会修改游戏的启动文件，往里面加一行 -javaagent。")
    print("每改一个文件都会留一份 .bak-hypernova-时间戳 的备份。")
    print()
    print("装完之后收益更大：启动期脚本预编译缓存、文件索引、法线图缓存都在这一半。")
    print("不装也能玩，主 mod 单独工作。")
    print()
    print("风险说在前面：启动文件写错的话，游戏会直接启动不了。")
    print("真遇到那样的情况，双击同目录下的 rollback-agent.bat，一步退回去。")
    print()
    _pause("确认继续请按回车；不想装就直接关掉这个窗口…")
    print()
    return manage_agent.main(["--action", "install"])


def rollback() -> int:
    print("=" * 62)
    print(" Hypernova 无限引擎 — 一键回滚 agent")
    print("=" * 62)
    print()
    print("正在把启动文件里所有 Hypernova 的 -javaagent 行删掉。")
    print("每个改动过的文件都会留一份 .bak-hypernova-时间戳 的备份。")
    print()
    return manage_agent.main(["--action", "rollback"])


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    action = "rollback" if "--rollback" in args else "install"
    code = rollback() if action == "rollback" else install()
    print()
    _pause()
    return code


if __name__ == "__main__":
    sys.exit(main())
