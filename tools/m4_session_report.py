#!/usr/bin/env python3
"""M4 手动会话报告：frame probe + lazy summary + 纹理错误 + GPU CSV。

读取最后一个 Starsector 会话切片里的 `HYPERNOVA_FRAME` 行和五类纹理错误，
读取最后一个 agent session 的 `lazy probe: summary`，可选合并 GPU CSV。
输出一份 JSON，避免手工抄数字。

用法：
    python tools/m4_session_report.py \
      --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
      --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
      --gpu-csv build/m4/gpu-ab.csv \
      --out build/m4/session.json --strict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import m28_scene_gate as gate

FRAME_MARKER = "HYPERNOVA_FRAME "
AGENT_SESSION_ANCHOR = "hypernova agent premain"
REQUIRED_FRAME_KEYS = (
    "frames", "over200", "maxMs", "p99Ms", "lastMs", "longGaps",
)
REQUIRED_LAZY_KEYS = (
    "queue", "failed", "disabled", "dimMismatch", "main",
    "liveBytes", "evictableBytes",
)
_KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")


def parse_pairs(text: str) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for key, value in _KEY_VALUE.findall(text):
        try:
            out[key] = int(value)
        except ValueError:
            out[key] = value
    return out


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _lazy_value_ok(key: str, value) -> bool:
    if key == "main":
        return isinstance(value, str)
    return _is_int(value)


def find_frame_probe(text: str, offset: int = 0) -> dict:
    """返回给定会话切片里最后一条 HYPERNOVA_FRAME 行。

    `line` 是切片内行号；提供会话起点 offset 时，`file_line` 换算成绝对行号。
    """
    found: dict[str, int | str] | None = None
    found_line = None
    for lineno, line in enumerate(text.splitlines(), 1):
        pos = line.find(FRAME_MARKER)
        if pos < 0:
            continue
        found = parse_pairs(line[pos + len(FRAME_MARKER):])
        found_line = lineno
    if found is None:
        return {"present": False, "line": None, "file_line": None,
                "missing_keys": list(REQUIRED_FRAME_KEYS),
                "invalid_keys": []}
    missing = [key for key in REQUIRED_FRAME_KEYS if key not in found]
    invalid = [key for key in REQUIRED_FRAME_KEYS
               if key in found and (
                   not _is_int(found[key]) or found[key] < 0)]
    # 类型合法的 frames=0 同样是无效探针：没有任何帧间隔数据，
    # 不能让它通过 --require-frame/--strict 的门禁。
    frames = found.get("frames")
    if _is_int(frames) and frames <= 0 and "frames" not in invalid:
        invalid.append("frames")
    if offset > 0:
        file_line = offset + found_line - 1
    else:
        file_line = found_line
    return {"present": True, "line": found_line, "file_line": file_line,
            "missing_keys": missing, "invalid_keys": invalid, **found}


def find_lazy_summary(text: str) -> dict:
    """只认最后一个 `hypernova agent premain` 之后的有效 summary。"""
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines)
               if AGENT_SESSION_ANCHOR in line]
    if not anchors:
        return {"present": False, "reason": "no agent session anchor",
                "anchor_line": None, "anchor_count": 0, "missing_keys": []}
    anchor = anchors[-1]
    session = "".join(lines[anchor + 1:])
    found = None
    found_line = None
    missing = list(REQUIRED_LAZY_KEYS)
    for offset, line in enumerate(session.splitlines()):
        if "lazy probe: summary" not in line or "summary failed" in line:
            continue
        parsed = parse_pairs(line)
        missing = [key for key in REQUIRED_LAZY_KEYS if key not in parsed]
        invalid = [key for key in REQUIRED_LAZY_KEYS
                   if key in parsed and not _lazy_value_ok(key, parsed[key])]
        if missing or invalid:
            continue
        found = parsed
        found_line = anchor + offset + 2
    if found is None:
        return {"present": False, "reason": "no valid summary after anchor",
                "anchor_line": anchor + 1, "anchor_count": len(anchors),
                "missing_keys": missing}
    return {"present": True, "summary": found, "line": found_line,
            "anchor_line": anchor + 1, "anchor_count": len(anchors),
            "missing_keys": []}


def _zero(summary: dict, key: str):
    value = summary.get(key)
    if not _is_int(value):
        return None
    return value == 0


def build_report(agent_text: str, starsector_text: str,
                 gpu_rows=None) -> dict:
    session, anchor_found, anchor_line, anchor_count = gate.last_session(
        starsector_text)
    errors = gate.count_texture_errors(session)
    frame = find_frame_probe(
        session, offset=anchor_line if anchor_found else 0)
    lazy = find_lazy_summary(agent_text)
    summary = lazy.get("summary", {})
    health = {
        "session_anchor_found": anchor_found,
        "frame_probe_present": frame["present"],
        "frame_probe_complete": (frame["present"]
                                 and not frame["missing_keys"]
                                 and not frame["invalid_keys"]),
        "lazy_present": lazy["present"],
        "lazy_failed_zero": _zero(summary, "failed"),
        "lazy_disabled_zero": _zero(summary, "disabled"),
        "lazy_dim_mismatch_zero": _zero(summary, "dimMismatch"),
        "lazy_failed_parked_zero": _zero(summary, "failedParked"),
        "lazy_main_bound": str(summary.get("main")).strip().lower() != "none",
        "texture_errors_zero": sum(errors.values()) == 0,
    }
    report = {
        "starsector_session": {
            "anchor_found": anchor_found,
            "anchor_line": anchor_line,
            "anchor_count": anchor_count,
        },
        "frame_probe": frame,
        "lazy": lazy,
        "texture_errors": errors,
        "texture_errors_total": sum(errors.values()),
        "health": health,
    }
    if gpu_rows is not None:
        report["gpu"] = gate.summarize_gpu(gpu_rows)
    return report


def human_text(report: dict) -> str:
    frame = report["frame_probe"]
    lazy = report["lazy"]
    lines = []
    if frame["present"]:
        lines.append("frame: frames={} over200={} max={}ms p99={}ms "
                     "last={}ms longGaps={}".format(
                         frame.get("frames", "?"), frame.get("over200", "?"),
                         frame.get("maxMs", "?"), frame.get("p99Ms", "?"),
                         frame.get("lastMs", "?"), frame.get("longGaps", "?")))
    else:
        lines.append("frame: absent")
    if lazy["present"]:
        summary = lazy["summary"]
        lines.append("lazy: failed={} disabled={} dimMismatch={} "
                     "failedParked={} main={} live={} evictable={}".format(
                         summary.get("failed"), summary.get("disabled"),
                         summary.get("dimMismatch"),
                         summary.get("failedParked"), summary.get("main"),
                         summary.get("liveBytes"),
                         summary.get("evictableBytes")))
    else:
        lines.append("lazy: absent ({})".format(lazy.get("reason")))
    lines.append("texture errors: total={}".format(
        report["texture_errors_total"]))
    gpu = report.get("gpu")
    if gpu:
        dedicated = gpu.get("dedicated_mb") or {}
        lines.append("gpu dedicated MB: {}".format(
            dedicated.get("median", "?")))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-log", type=Path, required=True)
    parser.add_argument("--starsector-log", type=Path, required=True)
    parser.add_argument("--gpu-csv", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-frame", action="store_true",
                        help="fail unless a complete HYPERNOVA_FRAME line "
                             "exists in the current session")
    parser.add_argument("--strict", action="store_true",
                        help="also require a healthy lazy summary and zero "
                             "texture errors")
    parser.add_argument("--text", action="store_true",
                        help="also print a human summary to stderr")
    args = parser.parse_args(argv)

    try:
        agent_text = args.agent_log.read_text(
            encoding="utf-8", errors="replace")
        starsector_text = args.starsector_log.read_text(
            encoding="utf-8", errors="replace")
        gpu_rows = None
        gpu_bad_rows = 0
        if args.gpu_csv is not None:
            gpu_rows, gpu_bad_rows = gate.read_gpu_csv(args.gpu_csv)
            if not gpu_rows:
                print("m4_session_report: no valid GPU samples in "
                      f"{args.gpu_csv} (bad_rows={gpu_bad_rows})",
                      file=sys.stderr)
                return 2
            gpu_summary = gate.summarize_gpu(gpu_rows)
            if gpu_summary["dedicated_mb"] is None:
                print("m4_session_report: no usable dedicated GPU memory "
                      f"samples in {args.gpu_csv} "
                      f"(bad_rows={gpu_bad_rows})", file=sys.stderr)
                return 2
        report = build_report(agent_text, starsector_text, gpu_rows)
        if gpu_bad_rows:
            report["gpu_bad_rows"] = gpu_bad_rows
        text = json.dumps(report, ensure_ascii=False, indent=2,
                          allow_nan=False)
    except (OSError, ValueError) as exc:
        print(f"m4_session_report: {exc}", file=sys.stderr)
        return 1

    print(text)
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"m4_session_report: {exc}", file=sys.stderr)
            return 1

    problems: list[str] = []
    health = report["health"]
    if not health["session_anchor_found"]:
        problems.append("no Fast Rendering session anchor")
    if not health["lazy_present"]:
        problems.append("no valid lazy probe summary")
    if health["texture_errors_zero"] is False:
        problems.append("texture errors > 0")
    if args.require_frame or args.strict:
        if not health["frame_probe_present"]:
            problems.append("no HYPERNOVA_FRAME line (frame probe off?)")
        else:
            frame = report["frame_probe"]
            if frame["invalid_keys"]:
                problems.append("frame probe line has invalid values: "
                                + ", ".join(frame["invalid_keys"]))
            if frame["missing_keys"]:
                problems.append("frame probe line missing keys: "
                                + ", ".join(frame["missing_keys"]))
    if args.strict and health["lazy_present"]:
        for key, label in (
                ("lazy_failed_zero", "failed != 0"),
                ("lazy_disabled_zero", "disabled != 0"),
                ("lazy_dim_mismatch_zero", "dimMismatch != 0"),
                ("lazy_failed_parked_zero", "failedParked != 0"),
                ("lazy_main_bound", "main not bound")):
            if health[key] is False:
                problems.append(label)
            elif health[key] is None:
                problems.append(label + " (missing key)")
    if args.text:
        print(human_text(report), file=sys.stderr)
    if problems:
        for problem in problems:
            print(f"m4_session_report: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
