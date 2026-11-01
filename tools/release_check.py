#!/usr/bin/env python3
"""Release zip checks for the Hypernova mod (M2.7 W5/W6 gates)."""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

REQUIRED = (
    "mod_info.json",
    "README-install.txt",
    "data/config/hypernova/manifest-v1.json",
    "data/config/hypernova/lazy-skip-v1.txt",
    "graphics/hypernova/blank.png",
)
FORBIDDEN = ("data/config/hypernova/lazy-skip-v2.txt",)
AGENT_MARKERS = (
    "hypernova/agent/HypernovaAgent.class",
    "hypernova/agent/textures/LazyTextures.class",
    "hypernova/agent/textures/LazyProxyObject.class",
)


def generation_header(data: bytes) -> str | None:
    for line in data.decode("utf-8", "replace").splitlines():
        if line.startswith("# generation="):
            return line[len("# generation="):].strip()
    return None


def jar_entries(data: bytes) -> dict[str, tuple[int, int]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {i.filename: (i.CRC, i.file_size) for i in zf.infolist()}
    except zipfile.BadZipFile:
        return {}


def check_zip(zip_path: Path, agent_jar: Path | None = None) -> list[str]:
    failures: list[str] = []
    if not zip_path.is_file():
        return [f"zip missing: {zip_path}"]
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        return [f"bad zip {zip_path}: {exc}"]
    with zf:
        names = set(zf.namelist())
        for req in REQUIRED:
            if req not in names:
                failures.append(f"missing {req}")
            elif zf.getinfo(req).file_size == 0:
                failures.append(f"empty {req}")
        for bad in FORBIDDEN:
            if bad in names:
                failures.append(f"forbidden host artifact: {bad}")
        manifest_name = "data/config/hypernova/manifest-v1.json"
        if manifest_name in names:
            manifest = zf.read(manifest_name)
            expected = hashlib.sha256(manifest).hexdigest()
            for skip in ("data/config/hypernova/lazy-skip-v1.txt",
                         "data/config/hypernova/lazy-skip-v2.txt"):
                if skip not in names:
                    continue
                got = generation_header(zf.read(skip))
                if got != expected:
                    failures.append(
                        f"{skip} generation {got or '<none>'} != manifest {expected}")
        if agent_jar is not None:
            if "jars/hypernova.agent.jar" not in names:
                failures.append("missing jars/hypernova.agent.jar")
            elif agent_jar.is_file():
                packaged = zf.read("jars/hypernova.agent.jar")
                entries = jar_entries(packaged)
                built = jar_entries(agent_jar.read_bytes())
                for marker in AGENT_MARKERS:
                    if marker not in entries:
                        failures.append(f"packaged agent jar missing {marker}")
                    if marker not in built:
                        failures.append(f"built agent jar missing {marker}")
                if entries and entries != built:
                    failures.append(
                        "packaged agent jar entries differ from "
                        f"{agent_jar}")
            else:
                failures.append(f"agent jar missing: {agent_jar}")
    return failures


def check_agent_fresh(agent_jar: Path, sources: Path) -> list[str]:
    if not agent_jar.is_file():
        return [f"agent jar missing: {agent_jar}"]
    if not sources.is_dir():
        return [f"agent sources missing: {sources}"]
    built = agent_jar.stat().st_mtime_ns
    stale = sorted(
        str(p.relative_to(sources))
        for p in sources.rglob("*.java")
        if "tools" not in p.relative_to(sources).parts
        and p.stat().st_mtime_ns > built
    )
    if not stale:
        return []
    shown = ", ".join(stale[:5])
    more = "" if len(stale) <= 5 else f" (+{len(stale) - 5} more)"
    return [f"agent sources newer than jar: {shown}{more}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", required=True, type=Path)
    ap.add_argument("--agent-jar", type=Path)
    ap.add_argument("--sources", type=Path)
    args = ap.parse_args(argv)
    failures = check_zip(args.zip, args.agent_jar)
    if args.agent_jar is not None and args.sources is not None:
        failures += check_agent_fresh(args.agent_jar, args.sources)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"OK: {args.zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
