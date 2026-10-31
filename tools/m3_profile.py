#!/usr/bin/env python3
"""Derive a launch profile with a different log4j config, byte-for-byte.

The 260mods launch profiles are CRLF and the agent must stay before FR.
This tool only swaps the log4j properties filename; it never rewrites the
file, so line endings and argument order are preserved.
"""
from __future__ import annotations

import argparse
from pathlib import Path

TOKEN = b"mikohime/mikohime.properties"


def derive(src: Path, dst: Path, props: str) -> None:
    data = src.read_bytes()
    count = data.count(TOKEN)
    if count != 1:
        raise ValueError(f"expected exactly one {TOKEN!r} token, found {count}")
    if b"hn-verbose" in data or b"hn-phase" in data:
        raise ValueError("source already points at a probe log4j config")
    dst.write_bytes(data.replace(TOKEN, props.encode("ascii")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--props", default="mikohime/hn-phase.properties")
    args = ap.parse_args(argv)
    derive(Path(args.src), Path(args.out), args.props)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
