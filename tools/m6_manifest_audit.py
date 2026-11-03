"""M6：manifest/skip generation 配对、宿主污染与 fail-open 审计。"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from hn_json import load  # noqa: E402
from install_manifest import DEFAULT_REL, install  # noqa: E402
from l1_core import CORE_STATIC, PLANET_FIELDS, PLANET_TYPES  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generation(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# generation="):
            return line.split("=", 1)[1].strip()
    return None


def audit_installed(game_root: str | Path) -> dict:
    root = Path(game_root).resolve()
    manifest = root / DEFAULT_REL
    skip_dir = manifest.parent
    findings: list[str] = []
    manifest_info = {"path": str(manifest), "exists": manifest.is_file(),
                     "sha256": None, "schema": None,
                     "l1": 0, "l2": 0, "l3": 0}
    if manifest.is_file():
        data = load(manifest)
        layers = data.get("layers") or {}
        manifest_info.update({
            "sha256": _sha256(manifest),
            "schema": data.get("schema"),
            "l1": len(layers.get("L1") or []),
            "l2": len(layers.get("L2") or []),
            "l3": len(layers.get("L3") or []),
        })
    else:
        findings.append("manifest_missing")
    skip_v1 = skip_dir / "lazy-skip-v1.txt"
    skip_v2 = skip_dir / "lazy-skip-v2.txt"
    skip_info = {
        "v1": {"path": str(skip_v1), "exists": skip_v1.is_file(),
               "generation": _generation(skip_v1)},
        "v2": {"path": str(skip_v2), "exists": skip_v2.is_file(),
               "generation": _generation(skip_v2)},
    }
    for key in ("v1", "v2"):
        if not skip_info[key]["exists"]:
            findings.append(f"skip_{key}_missing")
        elif manifest_info["sha256"] and skip_info[key]["generation"] != manifest_info["sha256"]:
            findings.append(f"skip_{key}_generation_mismatch")
    host = sorted(
        str(p.relative_to(root))
        for p in (root / "starsector-core").glob("lazy-skip-*.txt")
    )
    if host:
        findings.append("host_lazy_skip")
    hn = root / "mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json"
    cfg = load(hn) if hn.is_file() else {}
    textures = cfg.get("textures") or {}
    lazy = textures.get("lazy") or {}
    eviction = lazy.get("eviction") or {}
    defaults = {
        "textures_enabled": bool(textures.get("enabled", False)),
        "lazy": bool(lazy.get("enabled", False)),
        "eviction": bool(eviction.get("enabled", False)),
        "scene_unload": bool(eviction.get("sceneUnload", False)),
    }
    if defaults["lazy"] or defaults["eviction"] or defaults["scene_unload"]:
        findings.append("default_not_off")
    return {
        "manifest": manifest_info,
        "skip_v1": skip_info["v1"],
        "skip_v2": skip_info["v2"],
        "host_pollution": {"found": host},
        "defaults": defaults,
        "findings": findings,
        "ok": not findings,
    }


def _png(w: int, h: int) -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00"
            + b"\x00\x00\x00\x00")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_broken_game(root: Path) -> None:
    for rel in CORE_STATIC:
        path = root / "starsector-core" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png(2, 2))
    planets = {
        t: {f: f"graphics/planets/{t}_{f}.jpg" for f in PLANET_FIELDS}
        for t in PLANET_TYPES
    }
    for t, fields in planets.items():
        for rel in fields.values():
            path = root / "starsector-core" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_png(2, 2))
    _write(root / "starsector-core/data/config/planets.json", json.dumps(planets))
    _write(root / "mods/enabled_mods.json", json.dumps({
        "enabledMods": ["good_mod", "dup_a", "dup_b", "tail_mod", "missing_mod"],
    }))
    # 正常 mod
    good = root / "mods/good_mod"
    _write(good / "mod_info.json", '{"id":"good_mod","name":"good"}')
    (good / "graphics/ships").mkdir(parents=True)
    (good / "graphics/ships/ship.png").write_bytes(_png(4, 4))
    # duplicate ModID：两个目录同 id
    for folder in ("dup_a", "dup_b"):
        _write(root / "mods" / folder / "mod_info.json",
               '{"id":"dup_same","name":"dup"}')
    # 尾逗号 mod_info（ChineseInputFix 风格）
    _write(root / "mods/tail_mod/mod_info.json",
           '{"id":"tail_mod","name":"tail",}')
    (root / "mods/tail_mod/graphics").mkdir(parents=True)
    (root / "mods/tail_mod/graphics/tail.png").write_bytes(_png(3, 3))
    # 空目录（无 mod_info）
    (root / "mods/empty_mod").mkdir(parents=True)


def audit_fail_open(workdir: str | Path) -> dict:
    base = Path(workdir).resolve()
    root = base / "game"
    if root.exists():
        raise FileExistsError(f"workdir already exists: {root}")
    _seed_broken_game(root)
    out = base / "runtime" / "manifest-v1.json"
    result = install(root, out=out)
    conflicts = (result.full.get("stats") or {}).get("conflicts") or {}
    return {
        "duplicate_ids": conflicts.get("duplicate_mod_ids", {}),
        "parse_errors": conflicts.get("mod_parse_errors", {}),
        "manifest_written": out.is_file(),
        "findings": [f"{f.severity}:{f.code}" for f in result.findings],
        "skip_v1_count": result.skip_count,
        "skip_v2_count": result.skip_v2_count,
        "ok": out.is_file() and result.skip_count > 0 and result.skip_v2_count > 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-open-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = {"installed": audit_installed(args.game_root)}
        if args.fail_open_dir:
            report["fail_open"] = audit_fail_open(args.fail_open_dir)
            # Step 6 / docs 期望 evidence/fail-open.json；与 --out 并列落一份摘要。
            if args.out:
                fail_out = args.out.parent / "fail-open.json"
                fail_out.parent.mkdir(parents=True, exist_ok=True)
                fail_out.write_text(
                    json.dumps(
                        report["fail_open"], ensure_ascii=False,
                        indent=2, sort_keys=True,
                    ) + "\n",
                    encoding="utf-8",
                )
    except Exception as exc:  # noqa: BLE001 - fail-closed
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["installed"]["ok"] and report.get("fail_open", {"ok": True})["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
