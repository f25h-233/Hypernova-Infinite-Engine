#!/usr/bin/env python3
"""Thin launcher for setup_agent.py, bundled with the mod.

Kept separate so the .bat does not need to know the module layout, and so the
player gets a readable message instead of a traceback when the mod folder is in
the wrong place.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    try:
        import setup_agent
    except ImportError:
        print("[ERROR] setup_agent.py is missing next to this file.")
        print("        Re-extract the mod zip; antivirus may have removed it.")
        input("Press Enter to close...")
        return 1
    # setup_agent.main() returns the process exit code; propagate it so the .bat
    # and the player can tell success from failure.
    return setup_agent.main()


if __name__ == "__main__":
    raise SystemExit(main())
