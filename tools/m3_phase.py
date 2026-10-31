#!/usr/bin/env python3
"""Parse a Starsector session into 0-50 s phase timings.

Never assumes the M-1c (FR 0.9.5) table. Inputs may be rotated logs; the
parser takes the LAST Fast Rendering session and the LAST agent premain
session. Output is JSON so docs and the ledger can cite exact numbers.

Timeline anchors (all emitted by classes that are actually executed):
  loader.start/end  FileLoaderFast.<init>            (FR class, loaded directly)
  dds.start/end     DDSIntegration.initialize        (FR class, loaded directly)
  mods.start        MarkovNames.loadIfNeeded         (first statement of FR's
                    merged initMods; the donor FileLoader class is never loaded)
  script.loader     ScriptCacheHook.preload
  script.first      first ScriptCacheHook.onFindClass
  find span         first/last ScriptCacheHook find timestamps
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SESSION_RE = __import__("re").compile(
    r"^\s*(\d+)\s+\[[^\]]+\]\s+INFO\s+com\.genir\.renderer\.agent\.Agent\s+"
    r"-\s+Fast Rendering: v0\.9\.")
MENU_RE = __import__("re").compile(
    r"^\s*(\d+)\s+\[[^\]]+\]\s+INFO\s+sound\.H\s+"
    r"-\s+Playing music with id \[miscallenous_main_menu\.ogg\]")
CRAWL_RE = __import__("re").compile(r"Cached (\d+) files in (\d+)ms")
TIMELINE_RE = __import__("re").compile(
    r"timeline:\s*(\S+)\s+rel_ms=(\d+)\s+epoch_ms=(\d+)")
FIND_SPAN_RE = __import__("re").compile(
    r"find span:.*?first_epoch_ms=(\d+).*?last_epoch_ms=(\d+)")
PRELOAD_RE = __import__("re").compile(
    r"scripts cache preloaded:.*entries=(\d+).*in (\d+) ms")
# Game-log fallback used only when the agent has no mods.start mark. The vanilla
# ScriptStore logs these when it starts loading mod script jars.
MOD_INIT_RE = __import__("re").compile(
    r"^\s*(\d+)\s+.*?(?:Loading jar files|Getting ready to load jar file \[)")


def _read(paths: list[str]) -> str:
    """Concatenate files oldest->newest so the LAST session is the newest run."""
    try:
        ordered = sorted(paths, key=lambda p: Path(p).stat().st_mtime)
    except OSError:
        ordered = list(paths)
    return b"".join(Path(p).read_bytes() for p in ordered).decode("utf-8", "replace")


def parse_session(text: str):
    """Return (session_lines, start_ms, menu_ms, crawl, mod_anchor_ms).

    menu_ms and mod_anchor_ms are relative to the FR session anchor. The FR and
    Hypernova premains run back-to-back, so this axis is within a few ms of the
    agent's timeline rel_ms axis.
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if SESSION_RE.match(line)]
    if not starts:
        raise SystemExit("no Fast Rendering session anchor in log")
    session = lines[starts[-1]:]
    start_ms = int(SESSION_RE.match(session[0]).group(1))
    menu_ms = None
    for line in session:
        m = MENU_RE.match(line)
        if m:
            menu_ms = int(m.group(1)) - start_ms
    crawl = None
    for line in session:
        m = CRAWL_RE.search(line)
        if m:
            crawl = {"files": int(m.group(1)), "ms": int(m.group(2))}
    mod_anchor_ms = None
    for line in session:
        m = MOD_INIT_RE.match(line)
        if m:
            mod_anchor_ms = int(m.group(1)) - start_ms
    return session, start_ms, menu_ms, crawl, mod_anchor_ms


def parse_agent(text: str):
    """Return (marks, preload, find_spans).

    find_spans is a list of (first_epoch_ms, last_epoch_ms) spans, oldest first.
    The post-menu periodic summary ticks add later spans; phases() selects the
    last span that completed before the menu.
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if "hypernova agent premain" in line]
    session = lines[starts[-1]:] if starts else lines
    marks: dict[str, dict[str, int]] = {}
    for line in session:
        m = TIMELINE_RE.search(line)
        if m:
            marks[m.group(1)] = {"rel_ms": int(m.group(2)), "epoch_ms": int(m.group(3))}
    preload = None
    for line in session:
        m = PRELOAD_RE.search(line)
        if m:
            preload = {"entries": int(m.group(1)), "ms": int(m.group(2))}
    find_spans = []
    for line in session:
        m = FIND_SPAN_RE.search(line)
        if m:
            first, last = int(m.group(1)), int(m.group(2))
            if last >= first:
                find_spans.append((first, last))
    return marks, preload, find_spans


def phases(marks: dict[str, dict[str, int]], menu_ms: int | None = None,
           fallback_mods_start_ms: int | None = None,
           find_spans=None):
    """Return (phases_ms, phases_approximate, script_span_ms).

    Only real anchors produce values. A missing mods.start uses the game-log
    fallback (when present) and marks the dependent phases approximate; no
    phase is synthesized from a guess.
    """
    out: dict[str, int] = {}
    approx: list[str] = []

    loader = marks.get("loader.start")
    dds_end = marks.get("dds.end")
    if loader and dds_end and dds_end["rel_ms"] >= loader["rel_ms"]:
        out["initFileLoaders"] = dds_end["rel_ms"] - loader["rel_ms"]

    mods_start = marks.get("mods.start")
    mods_ms = mods_start["rel_ms"] if mods_start else fallback_mods_start_ms
    if dds_end and mods_ms is not None and mods_ms >= dds_end["rel_ms"]:
        out["initSpecStore"] = mods_ms - dds_end["rel_ms"]
        if mods_start is None:
            approx.append("initSpecStore")
    if mods_ms is not None and menu_ms is not None and menu_ms >= mods_ms:
        out["initMods"] = menu_ms - mods_ms
        if mods_start is None:
            approx.append("initMods")

    script_span = None
    spans = _spans(find_spans)
    if spans:
        chosen = _span_before_menu(spans, loader, menu_ms)
        if chosen is not None:
            script_span = chosen[1] - chosen[0]

    return out, approx, script_span


def _spans(find_spans) -> list[tuple[int, int]]:
    if not find_spans:
        return []
    if isinstance(find_spans, tuple):
        return [find_spans]
    return list(find_spans)


def _span_before_menu(spans: list[tuple[int, int]],
                      loader: dict[str, int] | None,
                      menu_ms: int | None) -> tuple[int, int] | None:
    """Pick the last completed span that ended by the menu.

    The agent's 30 s summary tick keeps running after the menu (during the smoke
    linger), so the last logged span is not a startup measurement. The menu's
    epoch is derived from loader.start: both premains run back-to-back.
    """
    if loader is None or menu_ms is None:
        return spans[-1]
    menu_epoch = loader["epoch_ms"] + (menu_ms - loader["rel_ms"])
    chosen = None
    for span in spans:
        if span[0] <= menu_epoch and span[1] <= menu_epoch:
            chosen = span
    if chosen is not None:
        return chosen
    # No complete pre-menu span was logged; use the earliest completed one.
    return min(spans, key=lambda s: s[1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="append", required=True,
                    help="session log(s); rotated files are read oldest->newest by mtime")
    ap.add_argument("--agent-log", action="append", default=[])
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    _, start_ms, menu_ms, crawl, mod_anchor_ms = parse_session(_read(args.log))
    marks, preload, find_span = ({}, None, None)
    if args.agent_log:
        marks, preload, find_span = parse_agent(_read(args.agent_log))
    phases_ms, approx, script_span = phases(marks, menu_ms, mod_anchor_ms, find_span)
    result = {
        "session_start_ms": start_ms,
        "menu_ms": menu_ms,
        "crawl": crawl,
        "timeline": marks,
        "phases_ms": phases_ms,
        "phases_approximate": approx,
        "scriptSpanMs": script_span,
        "preload": preload,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
    return 0 if menu_ms is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
