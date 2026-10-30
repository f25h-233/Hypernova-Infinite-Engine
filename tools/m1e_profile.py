#!/usr/bin/env python3
"""Derive a true no-Fast-Rendering launch profile from an existing profile.

The no-FR arm must remove FR from the *classpath* as well as from the
`-javaagent` list. `HypernovaAgent.frPresent()` is
`Class.forName("com.genir.renderer.Version")`, so deleting only the agent line
leaves FR present and the arm proves nothing about a missing FR.

The tool writes a new file and never touches the source. It fails closed when
the source has no Hypernova agent line (the derived profile would not exercise
our agent) or when the layout is not understood.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FR_AGENT_LINE = "-javaagent:fr.agent.jar"
FR_CLASSPATH_TOKENS = {"fr.jar", "fr.agent.jar"}
HYPERNOVA_AGENT_TOKEN = "hypernova.agent.jar"
MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"


class ProfileError(Exception):
    """The source profile cannot be converted without guessing."""


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _classpath_tokens(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("-classpath"):
        return []
    rest = stripped[len("-classpath"):].strip()
    return [t.strip() for t in rest.split(";") if t.strip()]


def convert(text: str) -> tuple[str, dict]:
    newline = _newline_for(text)
    lines = text.splitlines()
    out: list[str] = []
    removed_agents = 0
    removed_tokens = 0
    classpath_lines = 0

    for line in lines:
        stripped = line.strip()
        if stripped == FR_AGENT_LINE:
            removed_agents += 1
            continue
        if stripped.startswith("-classpath"):
            rest = stripped[len("-classpath"):].strip()
            if not rest:
                raise ProfileError(
                    "-classpath must carry its jars on the same line; "
                    "split -classpath lines are not supported")
            classpath_lines += 1
            if classpath_lines > 1:
                raise ProfileError("multiple -classpath lines are not supported")
            tokens = [t.strip() for t in rest.split(";") if t.strip()]
            kept = [t for t in tokens if t not in FR_CLASSPATH_TOKENS]
            removed_tokens += len(tokens) - len(kept)
            if not kept:
                raise ProfileError("-classpath would become empty")
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}-classpath {';'.join(kept)}")
            continue
        out.append(line)

    if classpath_lines == 0:
        raise ProfileError("no -classpath line found")
    if not any(HYPERNOVA_AGENT_TOKEN in line for line in out):
        raise ProfileError(
            "Hypernova agent line is missing; install the agent into the source "
            "profile first (tools/install_agent.py)")
    if any(line.strip() == FR_AGENT_LINE for line in out):
        raise ProfileError("FR agent line survived conversion")
    for line in out:
        if any(t in FR_CLASSPATH_TOKENS for t in _classpath_tokens(line)):
            raise ProfileError("FR jar survived conversion")

    nonempty = [line.strip() for line in out if line.strip()]
    if not nonempty or nonempty[-1] != MAIN_CLASS:
        raise ProfileError(
            f"main class must stay last; got {nonempty[-1] if nonempty else '<empty>'!r}")

    stats = {
        "removed_fr_agent_lines": removed_agents,
        "removed_fr_classpath_tokens": removed_tokens,
        "classpath_lines": classpath_lines,
    }
    return newline.join(out) + newline, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    src = Path(args.src)
    out = Path(args.out)
    if src.resolve() == out.resolve():
        print("FATAL: --out must differ from --src", file=sys.stderr)
        return 2
    if out.exists() and not args.force:
        print(f"FATAL: {out} exists; pass --force to overwrite", file=sys.stderr)
        return 2

    raw = src.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    try:
        converted, stats = convert(text)
    except ProfileError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    payload = converted.encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    print(f"wrote {out}: removed {stats['removed_fr_agent_lines']} FR agent line(s), "
          f"{stats['removed_fr_classpath_tokens']} classpath token(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
