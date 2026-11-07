#!/usr/bin/env python3
"""Install or roll back a Fast Rendering distribution in a Starsector install.

Only ``fr.jar``, ``fr.agent.jar`` and ``fr.version.txt`` are touched.
``fr.vmparams`` and the launch profiles are never modified: they carry local
memory settings and the Hypernova agent line.

The 0.9.7rc2 / 0.9.8 pins are recorded below; pass ``--no-verify`` only for synthetic
fixtures. A backup is created as ``<name>.bak-hypernova-<old-version>`` and is
never overwritten with different content.
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
VERSION_RE = re.compile(rb"v0\.9\.[0-9A-Za-z][0-9A-Za-z.\-]{0,19}")

EXPECTED_PINS = {
    "v0.9.7rc2": {
        FR_JAR: "5f811d32eaeb4cc359a80ae5bae95c8ee3414d3f3786abb99996afaaa6e16703",
        FR_AGENT: "3caea920626d666b275c8352ce1fb2f2393ff26816ec8aab89d705b2673ad7d4",
    },
    "v0.9.8": {
        FR_JAR: "c7d91b0c8f7aaaa3380b52d6549681d75a93f6b626ad06a673002b845da04ffd",
        FR_AGENT: "55eecda58608cf1c6a23466acc957bdb93d648d6800d7527769c07450a884cbb",
    },
}
DEFAULT_SRC = ".cache/fr098/release/fast-rendering-0.9.8"


class FrInstallError(Exception):
    """The install/rollback cannot proceed safely."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    return {
        "game": str(game),
        "core": str(core),
        "version": installed_version(game),
        "version_file": (core / FR_VERSION).is_file(),
        "fr_sha256": sha256_file(core / FR_JAR) if (core / FR_JAR).is_file() else None,
        "agent_sha256": sha256_file(core / FR_AGENT) if (core / FR_AGENT).is_file() else None,
    }


def _validate_source(src: Path, expected: dict[str, str] | None,
                     version: str | None) -> str:
    if not src.is_dir():
        raise FrInstallError(f"source directory not found: {src}")
    for name in (FR_JAR, FR_AGENT):
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


def install(src: Path, game: Path, *, expected: dict[str, str] | None = None,
            version: str | None = None, dry_run: bool = False) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    for name in (FR_JAR, FR_AGENT):
        if not (core / name).is_file():
            raise FrInstallError(
                f"refusing to install into {core}: {name} is missing (not an FR install?)")
    new_version = _validate_source(src, expected, version)
    old_version = installed_version(game) or "unknown"
    backups: list[str] = []
    changed = False
    for name in (FR_JAR, FR_AGENT):
        src_file = src / name
        dst_file = core / name
        if sha256_file(src_file) == sha256_file(dst_file):
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
    return {
        "game": str(game),
        "old_version": old_version,
        "new_version": new_version,
        "backups": backups,
        "changed": changed,
        "dry_run": dry_run,
    }


def rollback(game: Path, *, to_version: str | None = None, dry_run: bool = False) -> dict:
    core = game / CORE
    if not core.is_dir():
        raise FrInstallError(f"target directory not found: {core}")
    current = installed_version(game) or "unknown"
    chosen: dict[str, Path] = {}
    for name in (FR_JAR, FR_AGENT):
        if to_version is not None:
            wanted = core / f"{name}.bak-hypernova-{to_version}"
            backups = [wanted] if wanted.is_file() else []
        else:
            backups = [p for p in core.glob(f"{name}.bak-hypernova-*")
                       if p.name != f"{name}.bak-hypernova-{current}"]
            backups.sort(key=lambda p: p.stat().st_mtime)
            backups = backups[-1:]
        if not backups:
            raise FrInstallError(
                f"no rollback backup for {name}"
                + (f" at {to_version}" if to_version else ""))
        chosen[name] = backups[0]
    target_version = to_version
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
    return {"game": str(game), "from_version": current, "to_version": target_version,
            "restored": restored, "dry_run": dry_run}


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
                           dry_run=args.dry_run)
        else:
            data = rollback(game, to_version=args.to, dry_run=args.dry_run)
    except FrInstallError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
