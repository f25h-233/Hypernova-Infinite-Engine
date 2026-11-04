#!/usr/bin/env python3
"""Release zip checks for the Hypernova mod (M2.7 W5/W6 gates)."""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

MOD_FOLDER = "hypernova_infinite_engine"
PREFIX = MOD_FOLDER + "/"

REQUIRED = (
    "mod_info.json",
    "README-install.txt",
    "data/config/hypernova/manifest-v1.json",
    "data/config/hypernova/lazy-skip-v1.txt",
    "graphics/hypernova/blank.png",
    "jars/hypernova.agent.jar",
    "jars/hypernova.jar",
)
FORBIDDEN = ("data/config/hypernova/lazy-skip-v2.txt",)
# 发行包内的 manifest 只覆盖 Base 纹理集，装了其它 mod 的玩家必须就地重新生成，
# 所以生成脚本是发行包的一部分，缺了就等于主 mod 对目标用户无效。
TOOL_FILES = (
    "hypernova-tools/generate-manifest.bat",
    "hypernova-tools/generate-manifest.sh",
    "hypernova-tools/install-agent.bat",
    "hypernova-tools/rollback-agent.bat",
    "hypernova-tools/manage_agent.py",
    "hypernova-tools/run_manifest.py",
    "hypernova-tools/run_agent.py",
    "hypernova-tools/README-tools.txt",
    "hypernova-tools/install_manifest.py",
    "hypernova-tools/manifest_builder.py",
    "hypernova-tools/gen_lazy_skip.py",
    "hypernova-tools/trim_manifest.py",
    "hypernova-tools/validate_manifest.py",
    "hypernova-tools/image_probe.py",
    "hypernova-tools/l1_core.py",
    "hypernova-tools/mod_index.py",
    "hypernova-tools/sprite_closure.py",
    "hypernova-tools/hn_json.py",
    "hypernova-tools/python/python.exe",
    "hypernova-tools/python/python312.zip",
)
AGENT_MARKERS = (
    "hypernova/agent/HypernovaAgent.class",
    "hypernova/agent/textures/LazyTextures.class",
    "hypernova/agent/textures/LazyProxyObject.class",
)
MAIN_MARKERS = (
    "hypernova/HypernovaPlugin.class",
    "hypernova/adapter/HypernovaCombatPlugin.class",
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


def check_zip(zip_path: Path, agent_jar: Path | None = None,
              main_jar: Path | None = None) -> list[str]:
    failures: list[str] = []
    if not zip_path.is_file():
        return [f"zip missing: {zip_path}"]
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        return [f"bad zip {zip_path}: {exc}"]
    with zf:
        raw = set(zf.namelist())
        roots = {n.split("/")[0] for n in raw}
        if roots != {MOD_FOLDER}:
            failures.append(
                f"zip root must be exactly {MOD_FOLDER}/, got {sorted(roots)[:5]}")
        # 内部检查一律用相对 mod 文件夹的路径，读文件时再拼回前缀。
        names = {n[len(PREFIX):] for n in raw if n.startswith(PREFIX)}

        def full(name: str) -> str:
            return PREFIX + name

        for req in REQUIRED:
            if req not in names:
                failures.append(f"missing {PREFIX}{req}")
            elif zf.getinfo(full(req)).file_size == 0:
                failures.append(f"empty {PREFIX}{req}")
        for bad in FORBIDDEN:
            if bad in names:
                failures.append(f"forbidden host artifact: {PREFIX}{bad}")
        for tool in TOOL_FILES:
            info = zf.getinfo(full(tool)) if tool in names else None
            if info is None:
                failures.append(f"missing {PREFIX}{tool}")
            elif info.file_size <= 0:
                failures.append(f"empty {PREFIX}{tool}")
        manifest_name = "data/config/hypernova/manifest-v1.json"
        if manifest_name in names:
            manifest = zf.read(full(manifest_name))
            expected = hashlib.sha256(manifest).hexdigest()
            for skip in ("data/config/hypernova/lazy-skip-v1.txt",
                         "data/config/hypernova/lazy-skip-v2.txt"):
                if skip not in names:
                    continue
                got = generation_header(zf.read(full(skip)))
                if got != expected:
                    failures.append(
                        f"{skip} generation {got or '<none>'} != manifest {expected}")
        main_name = "jars/hypernova.jar"
        if main_name in names:
            entries = jar_entries(zf.read(full(main_name)))
            for marker in MAIN_MARKERS:
                info = entries.get(marker)
                if info is None or info[1] <= 0:
                    failures.append(f"packaged main jar missing {marker}")
            if main_jar is not None:
                if not main_jar.is_file():
                    failures.append(f"main jar missing: {main_jar}")
                else:
                    built = jar_entries(main_jar.read_bytes())
                    for marker in MAIN_MARKERS:
                        info = built.get(marker)
                        if info is None or info[1] <= 0:
                            failures.append(f"built main jar missing {marker}")
                    if entries and entries != built:
                        failures.append(
                            "packaged main jar entries differ from "
                            f"{main_jar}")
        if agent_jar is not None:
            if "jars/hypernova.agent.jar" in names:
                if agent_jar.is_file():
                    packaged = zf.read(full("jars/hypernova.agent.jar"))
                    entries = jar_entries(packaged)
                    built = jar_entries(agent_jar.read_bytes())
                    for marker in AGENT_MARKERS:
                        info = entries.get(marker)
                        if info is None or info[1] <= 0:
                            failures.append(
                                f"packaged agent jar missing {marker}")
                        info = built.get(marker)
                        if info is None or info[1] <= 0:
                            failures.append(
                                f"built agent jar missing {marker}")
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
    ap.add_argument("--main-jar", type=Path)
    ap.add_argument("--sources", type=Path)
    args = ap.parse_args(argv)
    failures = check_zip(args.zip, args.agent_jar, args.main_jar)
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
