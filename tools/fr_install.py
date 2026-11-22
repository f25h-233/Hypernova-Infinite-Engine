#!/usr/bin/env python3
"""Install or roll back a Fast Rendering distribution in a Starsector install.

The file set is version dependent: FR <= 0.9.8 ships ``fr.jar`` **and** the
separate ``fr.agent.jar``; from 1.0.0rc1 the agent (and its ASM copies) moved
inside ``fr.jar`` and ``fr.agent.jar`` no longer exists. ``files_for()`` is the
single place that decides, and every install/rollback path goes through it.

``fr.version.txt`` is written next to them. ``fr.vmparams`` is never rewritten
wholesale: it carries local memory settings and the Hypernova agent line. But
the FR ``-javaagent`` line itself is structural (the game will not start if it
points at a jar the installed version does not ship), so install/rollback
repoint that one line in the recognised launch files, keeping a backup.
Pass ``--no-repoint`` to skip it.

The 0.9.7rc2 / 0.9.8 / 1.0.0 / 1.0.1 pins are recorded below; pass ``--no-verify``
only for synthetic fixtures. A backup is created as
``<name>.bak-hypernova-<old-version>`` and is never overwritten with different
content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

FR_JAR = "fr.jar"
FR_AGENT = "fr.agent.jar"
FR_VERSION = "fr.version.txt"
CORE = "starsector-core"
VERSION_CLASS = "com/genir/renderer/Version.class"
VERSION_RE = re.compile(rb"v\d+\.\d+\.[0-9A-Za-z][0-9A-Za-z.\-]{0,19}")

# 1.0.0rc1 起 agent 与 ASM 内嵌进 fr.jar，独立 jar 不再存在。
AGENT_IN_JAR_SINCE = (1, 0, 0)

EXPECTED_PINS = {
    "v0.9.7rc2": {
        FR_JAR: "5f811d32eaeb4cc359a80ae5bae95c8ee3414d3f3786abb99996afaaa6e16703",
        FR_AGENT: "3caea920626d666b275c8352ce1fb2f2393ff26816ec8aab89d705b2673ad7d4",
    },
    "v0.9.8": {
        FR_JAR: "c7d91b0c8f7aaaa3380b52d6549681d75a93f6b626ad06a673002b845da04ffd",
        FR_AGENT: "55eecda58608cf1c6a23466acc957bdb93d648d6800d7527769c07450a884cbb",
    },
    # No fr.agent.jar: the agent classes live inside fr.jar (Premain-Class entry).
    "v1.0.0": {
        FR_JAR: "04d7ae12a2fb78c5aedf75909bd78255fddcc97bae75f250483243bf7cac08ed",
    },
    "v1.0.1": {
        FR_JAR: "150ebc21f0191acb4c1452aaa809f3fc129f98933d9e7c8f5b366e2888291187",
    },
    # v1.0.2 stable (2026-11-18): still one embedded-agent fr.jar, and it still
    # reserves texture ids from getImageFileCount(). The agent refills that map
    # during index replay, which is what makes the file index usable here.
    "v1.0.2": {
        FR_JAR: "7aba2a13e3d9af8f0b3c06a792ed8398171b437bb2f66e5a8784b65f1ab349b3",
    },
}
DEFAULT_SRC = ".cache/fr098/release/fast-rendering-0.9.8"

# FR's own -javaagent line as it appears in launch files, old shape first.
FR_LAUNCH_LINES = ("-javaagent:fr.agent.jar", "-javaagent:fr.jar")
# Launch files repointed on install/rollback. Fixed paths plus a glob for the
# Miko_*.txt family: the 260mods test install keeps m27/m28/phase/verbose
# variants, and leaving one of them on the removed fr.agent.jar would make that
# profile silently refuse to start.
LAUNCH_FILES = (
    Path("starsector-core") / "fr.vmparams",
    Path("starsector-core") / "launch_launcher.vmparams",
)
LAUNCH_GLOBS = ("Miko_*.txt",)


class FrInstallError(Exception):
    """The install/rollback cannot proceed safely."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """'v1.0.2rc1' -> (1, 0, 2). Prerelease suffixes are ignored for ordering."""
    if not text:
        return None
    m = re.match(r"\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def uses_embedded_agent(version: str | None) -> bool:
    """True when the distribution ships no separate fr.agent.jar (FR >= 1.0.0)."""
    parts = parse_version(version)
    return parts is not None and parts >= AGENT_IN_JAR_SINCE


def files_for(version: str | None) -> tuple[str, ...]:
    """The jar files a given FR version ships."""
    return (FR_JAR,) if uses_embedded_agent(version) else (FR_JAR, FR_AGENT)


def fr_launch_line_for(version: str | None) -> str:
    """The -javaagent line the installed version needs."""
    return "-javaagent:fr.jar" if uses_embedded_agent(version) else "-javaagent:fr.agent.jar"


def jar_version(jar: Path) -> str | None:
    """Read the version string baked into com/genir/renderer/Version.class."""
    try:
        with zipfile.ZipFile(jar) as z:
            data = z.read(VERSION_CLASS)
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    m = VERSION_RE.search(data)
    return m.group(0).decode("ascii") if m else None


def installed_version(game: Path) -> str | None:
    core = game / CORE
    version_file = core / FR_VERSION
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text
    return jar_version(core / FR_JAR)


def status(game: Path) -> dict:
    core = game / CORE
    version = installed_version(game)
    return {
        "game": str(game),
        "core": str(core),
        "version": version,
        "version_file": (core / FR_VERSION).is_file(),
        "embedded_agent": uses_embedded_agent(version),
        "fr_sha256": sha256_file(core / FR_JAR) if (core / FR_JAR).is_file() else None,
        "agent_sha256": sha256_file(core / FR_AGENT) if (core / FR_AGENT).is_file() else None,
    }


def _validate_source(src: Path, expected: dict[str, str] | None,
                     version: str | None) -> str:
    if not src.is_dir():
        raise FrInstallError(f"source directory not found: {src}")
    if version is None:
        version_file = src / FR_VERSION
        if version_file.is_file():
            version = version_file.read_text(encoding="utf-8", errors="replace").strip() or None
    names = files_for(version)
    for name in names:
        if not (src / name).is_file():
            raise FrInstallError(f"source is missing {name}: {src}")
    if expected:
        for name, want in expected.items():
            got = sha256_file(src / name)
            if got != want:
                raise FrInstallError(f"{name} sha256 mismatch: {got} != {want}")
    version_file = src / FR_VERSION
    if version is not None:
        if not version_file.is_file():
            raise FrInstallError(f"source is missing {FR_VERSION}: {src}")
        got = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if got != version:
            raise FrInstallError(f"version mismatch: {got!r} != {version!r}")
    if version is None and version_file.is_file():
        version = version_file.read_text(encoding="utf-8", errors="replace").strip() or None
    return version or "unknown"


def pins_for(src: Path, version: str | None) -> tuple[dict[str, str], str]:
    """Resolve the pinned hashes for the source tree's FR version.

    Reads fr.version.txt when --version is omitted, then requires an entry in
    EXPECTED_PINS. Unknown versions are fail-closed; --no-verify is the only
    bypass and is reserved for synthetic fixtures.
    """
    if not src.is_dir():
        raise FrInstallError(f"source directory not found: {src}")
    if version is None:
        version_file = src / FR_VERSION
        if not version_file.is_file():
            raise FrInstallError(f"source is missing {FR_VERSION}: {src}")
        version = version_file.read_text(encoding="utf-8", errors="replace").strip() or None
    if version is None:
        raise FrInstallError(f"cannot determine FR version from: {src}")
    pins = EXPECTED_PINS.get(version)
    if pins is None:
        known = ", ".join(sorted(EXPECTED_PINS))
        raise FrInstallError(f"unsupported FR version: {version!r}; known: {known}")
    return pins, version


def _backup(path: Path, version: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-hypernova-{version}")
    if backup.exists():
        if sha256_file(backup) != sha256_file(path):
            raise FrInstallError(
                f"backup {backup} already exists with different content; refusing to overwrite")
        return backup
    shutil.copy2(path, backup)
    return backup


def _launch_files(game: Path) -> list[Path]:
    out: list[Path] = [game / rel for rel in LAUNCH_FILES if (game / rel).is_file()]
    for pattern in LAUNCH_GLOBS:
        out.extend(sorted(p for p in game.glob(pattern) if p.is_file()))
    return out


def _repoint_lines(lines: list[str], wanted: str) -> list[str] | None:
    """Rewrite FR's own -javaagent line to ``wanted``; None when already correct."""
    out = list(lines)
    changed = False
    for i, line in enumerate(lines):
        if line.strip() in FR_LAUNCH_LINES and line.strip() != wanted:
            eol = "\n" if line.endswith("\n") else ""
            out[i] = wanted + eol
            changed = True
    return out if changed else None


def repoint_launch_files(game: Path, version: str | None, *,
                         old_version: str | None = None,
                         dry_run: bool = False) -> list[str]:
    """Point FR's -javaagent line at what ``version`` actually ships.

    A launch file that still references the removed ``fr.agent.jar`` after a
    1.0.x install makes the JVM refuse to start, so this is part of installing,
    not an optional nicety. Each rewritten file keeps a ``.bak-hypernova-<old>``
    backup, matching the rest of this tool's backup rules.

    ``old_version`` names that backup. Callers must pass the version that was
    installed *before* the jar swap; ``None`` falls back to reading the tree.
    """
    wanted = fr_launch_line_for(version)
    if old_version is None:
        old_version = installed_version(game) or "unknown"
    changed: list[str] = []
    for path in _launch_files(game):
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            continue
        new_lines = _repoint_lines(lines, wanted)
        if new_lines is None:
            continue
        changed.append(str(path))
        if dry_run:
            continue
        backup = path.with_name(f"{path.name}.bak-hypernova-{old_version}")
        if not backup.exists():
            shutil.copy2(path, backup)
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write("".join(new_lines))
    return changed


def install(src: Path, game: Path, *, expected: dict[str, str] | None = None,
            version: str | None = None, dry_run: bool = False,
            repoint: bool = True) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    if not (core / FR_JAR).is_file():
        raise FrInstallError(
            f"refusing to install into {core}: {FR_JAR} is missing (not an FR install?)")
    new_version = _validate_source(src, expected, version)
    old_version = installed_version(game) or "unknown"
    backups: list[str] = []
    changed = False
    for name in files_for(new_version):
        src_file = src / name
        dst_file = core / name
        if dst_file.is_file() and sha256_file(src_file) == sha256_file(dst_file):
            continue
        changed = True
        if dry_run:
            backups.append(str(dst_file.with_name(
                f"{dst_file.name}.bak-hypernova-{old_version}")))
            continue
        backup = _backup(dst_file, old_version)
        if backup is not None:
            backups.append(str(backup))
        shutil.copy2(src_file, dst_file)
    src_version_file = src / FR_VERSION
    if src_version_file.is_file():
        dst_version_file = core / FR_VERSION
        new_text = src_version_file.read_text(encoding="utf-8", errors="replace").strip()
        old_text = (dst_version_file.read_text(encoding="utf-8", errors="replace").strip()
                    if dst_version_file.is_file() else "")
        if new_text != old_text:
            changed = True
            if not dry_run:
                if dst_version_file.is_file():
                    _backup(dst_version_file, old_version)
                shutil.copy2(src_version_file, dst_version_file)
    launch_files: list[str] = []
    if repoint:
        launch_files = repoint_launch_files(game, new_version,
                                           old_version=old_version, dry_run=dry_run)
    return {
        "game": str(game),
        "old_version": old_version,
        "new_version": new_version,
        "backups": backups,
        "launch_files": launch_files,
        "changed": changed or bool(launch_files),
        "dry_run": dry_run,
    }


def rollback(game: Path, *, to_version: str | None = None, dry_run: bool = False,
             repoint: bool = True) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    current = installed_version(game) or "unknown"
    # The jar set is decided by the target version, not by today's install:
    # rolling back to 0.9.8 must bring fr.agent.jar back, and rolling forward
    # to 1.0.x must not touch a stale fr.agent.jar the user may have removed.
    target_version = to_version
    if target_version is None:
        fr_backups = [p for p in core.glob(f"{FR_JAR}.bak-hypernova-*")
                      if p.name != f"{FR_JAR}.bak-hypernova-{current}"]
        fr_backups.sort(key=lambda p: p.stat().st_mtime)
        if fr_backups:
            target_version = fr_backups[-1].name.split(
                f"{FR_JAR}.bak-hypernova-", 1)[1]
    names = files_for(target_version)
    chosen: dict[str, Path] = {}
    for name in names:
        if target_version is not None:
            wanted = core / f"{name}.bak-hypernova-{target_version}"
            backups = [wanted] if wanted.is_file() else []
        else:
            backups = [p for p in core.glob(f"{name}.bak-hypernova-*")
                       if p.name != f"{name}.bak-hypernova-{current}"]
            backups.sort(key=lambda p: p.stat().st_mtime)
            backups = backups[-1:]
        if not backups:
            raise FrInstallError(
                f"no rollback backup for {name}"
                + (f" at {target_version}" if target_version else ""))
        chosen[name] = backups[0]
    if target_version is None:
        target_version = chosen[FR_JAR].name.split(f"{FR_JAR}.bak-hypernova-", 1)[1]
    restored: list[str] = []
    for name, backup in chosen.items():
        dst = core / name
        if dry_run:
            restored.append(str(dst))
            continue
        _backup(dst, current)
        shutil.copy2(backup, dst)
        restored.append(str(dst))
    version_file = core / FR_VERSION
    new_text = target_version if target_version and target_version.startswith("v") else ""
    old_text = (version_file.read_text(encoding="utf-8", errors="replace").strip()
                if version_file.is_file() else "")
    if old_text != new_text:
        if not dry_run:
            if version_file.is_file():
                _backup(version_file, current)
            version_file.write_text(new_text, encoding="utf-8")
    launch_files: list[str] = []
    if repoint:
        launch_files = repoint_launch_files(game, target_version,
                                           old_version=current, dry_run=dry_run)
    return {"game": str(game), "from_version": current, "to_version": target_version,
            "restored": restored, "launch_files": launch_files, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--version", default=None,
                    help="expected FR version; default: read fr.version.txt from --src")
    ap.add_argument("--action", choices=("install", "rollback", "status"), default="status")
    ap.add_argument("--to", default=None, help="rollback target version, e.g. v0.9.5")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the pinned sha256/version checks (tests only)")
    ap.add_argument("--no-repoint", action="store_true",
                    help="do not rewrite FR's -javaagent line in launch files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    game = Path(args.game)
    try:
        if args.action == "status":
            data = status(game)
        elif args.action == "install":
            expected = None
            version = None
            if not args.no_verify:
                expected, version = pins_for(Path(args.src), args.version)
            data = install(Path(args.src), game, expected=expected, version=version,
                           dry_run=args.dry_run, repoint=not args.no_repoint)
        else:
            data = rollback(game, to_version=args.to, dry_run=args.dry_run,
                            repoint=not args.no_repoint)
    except FrInstallError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
