#!/usr/bin/env python3
"""Thin launcher for check_setup.py, bundled with the mod."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    try:
        import check_setup
    except ImportError:
        print("[ERROR] check_setup.py is missing next to this file.")
        print("        Re-extract the mod zip; antivirus may have removed it.")
        input("Press Enter to close...")
        return 1
    return check_setup.main()


if __name__ == "__main__":
    raise SystemExit(main())
