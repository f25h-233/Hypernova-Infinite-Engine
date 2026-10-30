#!/usr/bin/env python3
"""Audit compiled classes for Java 17 compatibility (M-1e gate 3).

Checks:
  1. Every class under each --classes directory has major version 61.
     Third-party classes bundled in --jar are reported but not failed.
  2. No Java 18-21-only API appears in --source files or in any class
     constant pool (checked with one batched `javap -verbose` per directory).

The major version is read from the class-file header, which is the same field
`javap -verbose` prints. Reading it per class covers every class without
spawning one process per class.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

CLASS_MAGIC = b"\xca\xfe\xba\xbe"
JAVA21_RE = re.compile(
    r"java/util/Sequenced(?:Collection|Set|Map)"
    r"|java/lang/Math[./\s]clamp|Math\.clamp"
    r"|java/lang/Thread[./\s]of(?:Virtual|Platform)|Thread\.of(?:Virtual|Platform)"
    r"|java/util/concurrent/StructuredTaskScope"
    r"|java/util/concurrent/ScopedValue"
    r"|java/lang/StringTemplate"
    r"|java/util/FormatProcessor"
    r"|java/lang/foreign/"
)


def class_major(data: bytes) -> int:
    if len(data) < 8:
        raise ValueError("class file too short")
    if data[:4] != CLASS_MAGIC:
        raise ValueError("bad class magic")
    return int.from_bytes(data[6:8], "big")


def scan_class_dir(root: Path) -> list[tuple[Path, int]]:
    return [(p, class_major(p.read_bytes())) for p in sorted(root.rglob("*.class"))]


def scan_jar(path: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name.endswith(".class"):
                out.append((name, class_major(z.read(name))))
    return out


def audit_text(text: str) -> list[str]:
    return sorted({m.group(0) for m in JAVA21_RE.finditer(text)})


def class_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def javap_dump(javap: str, root: Path, names: list[str], chunk: int = 40) -> str:
    parts: list[str] = []
    for i in range(0, len(names), chunk):
        r = subprocess.run(
            [javap, "-verbose", "-classpath", str(root), *names[i:i + chunk]],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"javap failed for {root}: {r.stderr.strip()[:300]}")
        parts.append(r.stdout)
    return "\n".join(parts)


def _majors(entries: list[tuple[object, int]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, major in entries:
        counts[str(major)] = counts.get(str(major), 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", action="append", default=[],
                    help="first-party class directory; every class must be --expect-major")
    ap.add_argument("--jar", action="append", default=[],
                    help="jar to report (third-party classes are not failed)")
    ap.add_argument("--source", action="append", default=[],
                    help="source root to scan for Java 18-21 APIs")
    ap.add_argument("--javap", default="javap")
    ap.add_argument("--expect-major", type=int, default=61)
    ap.add_argument("--skip-api-scan", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    if not args.classes and not args.jar and not args.source:
        print("FATAL: pass at least one --classes, --jar or --source", file=sys.stderr)
        return 2

    result: dict = {
        "expected_major": args.expect_major,
        "class_dirs": {},
        "jars": {},
        "java21_api_hits": [],
        "ok": False,
    }
    bad: list[str] = []

    for d in args.classes:
        root = Path(d)
        if not root.is_dir():
            print(f"FATAL: class dir not found: {root}", file=sys.stderr)
            return 2
        entries = scan_class_dir(root)
        wrong = [(p, m) for p, m in entries if m != args.expect_major]
        bad.extend(f"{p}: major {m}" for p, m in wrong)
        result["class_dirs"][d] = {
            "count": len(entries),
            "majors": _majors(entries),
            "bad": [f"{p}: major {m}" for p, m in wrong],
        }
        if not args.skip_api_scan and entries:
            names = [class_name(root, p) for p, _ in entries
                     if p.name != "module-info.class"]
            if names:
                try:
                    result["java21_api_hits"].extend(
                        audit_text(javap_dump(args.javap, root, names)))
                except (OSError, RuntimeError) as e:
                    print(f"FATAL: {e}", file=sys.stderr)
                    return 2

    for j in args.jar:
        path = Path(j)
        if not path.is_file():
            print(f"FATAL: jar not found: {path}", file=sys.stderr)
            return 2
        entries = scan_jar(path)
        result["jars"][j] = {"count": len(entries), "majors": _majors(entries)}

    for s in args.source:
        root = Path(s)
        if not root.is_dir():
            print(f"FATAL: source root not found: {root}", file=sys.stderr)
            return 2
        for p in sorted(root.rglob("*.java")):
            result["java21_api_hits"].extend(
                audit_text(p.read_text(encoding="utf-8", errors="replace")))

    result["java21_api_hits"] = sorted(set(result["java21_api_hits"]))
    result["ok"] = not bad and not result["java21_api_hits"]

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
