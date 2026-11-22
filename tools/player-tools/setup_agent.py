#!/usr/bin/env python3
"""Install the Hypernova agent line into a Starsector launch file.

Ships with the mod (``hypernova-tools``) and is also used to rebuild the audit
test roots. It exists because the two supported routes have structurally
different launch files:

* **Route B** (plain Fast Rendering) uses a multi-line argfile
  (``Miko_Simple.txt``). FR's own line is ``-javaagent:fr.agent.jar`` and
  Hypernova must be inserted immediately *before* it, because FR rewrites
  ``TextureData``'s constant pool and a transformer registered after FR sees
  rewritten bytes and silently no-ops.
* **Route A** (MixinFR) uses a **single-line** ``vmparams``. There is no
  ``fr.agent.jar`` line at all — FR rides inside
  ``-javaagent:..\\mods\\MixinFR\\jars\\MixinLib-bridge.jar``. Inserting by
  line (what ``install_agent.py`` does) would split that line and the native
  launcher can no longer read it, so this script edits within the line.

The script only edits the agent line. Memory, Java version and every other JVM
flag belong to the launcher configurator or the game's own ``vmparams``; this
script deliberately does not touch them, so re-running the configurator never
produces a conflict.

Fail-closed: every check runs before anything is written, and a backup is kept.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

AGENT_JAR = "hypernova.agent.jar"
AGENT_REL = "../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
# Route A addresses the agent relative to starsector-core as well, but its
# vmparams uses Windows separators and `..\mods\...`; both forms are accepted.
AGENT_ABS = "-javaagent:" + AGENT_REL

# Route B: FR's own javaagent line, both historical spellings.
FR_LINES = ("-javaagent:fr.agent.jar", "-javaagent:fr.jar")
# Route A: MixinFR's bridge plays FR's role ("must come after Hypernova").
MIXIN_LINES = ("-javaagent:..\\mods\\MixinFR\\jars\\MixinLib-bridge.jar",
               "-javaagent:../mods/MixinFR/jars/MixinLib-bridge.jar")
MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"

ROUTE_B = "b"
ROUTE_A = "a"


class SetupError(Exception):
    pass


# ------------------------------------------------------------------ parsing

def detect_route(text: str) -> str:
    """Decide which route a launch file belongs to, from its own content."""
    if any(line in text for line in MIXIN_LINES):
        return ROUTE_A
    if any(line in text for line in FR_LINES):
        return ROUTE_B
    raise SetupError(
        "no Fast Rendering agent line found.\n"
        "  Route A expects: " + MIXIN_LINES[0] + "\n"
        "  Route B expects: -javaagent:fr.agent.jar (or -javaagent:fr.jar)\n"
        "Install Fast Rendering / MixinFR first, then run this again.")


def _agent_present(text: str) -> bool:
    return re.search(r"-javaagent:[^\s\"]*hypernova\.agent\.jar", text) is not None


def _strip_agent(text: str) -> str:
    """Remove any existing Hypernova agent token, and the whitespace it used."""
    return re.sub(r'\s*-javaagent:[^\s"]*hypernova\.agent\.jar', "", text)


def _agent_present(text: str) -> bool:
    return re.search(r"-javaagent:[^\s\"]*hypernova\.agent\.jar", text) is not None


def _strip_agent(text: str) -> str:
    """Remove any existing Hypernova agent token, and the whitespace it used."""
    return re.sub(r'\s*-javaagent:[^\s"]*hypernova\.agent\.jar', "", text)


def patch_single_line(text: str, route: str) -> str:
    """Route A: everything lives on one line; tokens are space separated.

    Hypernova goes **after** the MixinFR bridge token.

    This is deliberately the opposite of route B. MixinFR's bridge is not a
    plain FR agent: it runs its own mixin service that rewrites
    ``org.dark.shaders.util.TextureData`` (``GLNormalMapBudgetMixin`` +
    ``FrNormalTakeoverMixin``, measured 50,438 -> 92,696 bytes). Hypernova's
    texture transformer matches that class by exact source SHA, so it cannot
    patch it on route A **no matter what the agent order is** — the class it
    would need to see no longer exists. Registering Hypernova afterwards is what
    the audit root does and what MixinFR's anchor list expects.
    """
    anchor = next((m for m in MIXIN_LINES if m in text), None)
    if anchor is None:
        raise SetupError("MixinFR bridge agent line not found in vmparams")
    if not text.rstrip().endswith(MAIN_CLASS):
        raise SetupError(
            f"main class {MAIN_CLASS} is not the last thing on the line; "
            "refusing to guess where to insert. Show vmparams to the author.")
    stripped = _strip_agent(text).rstrip()
    return stripped.replace(anchor, anchor + " " + AGENT_ABS, 1)


def patch_multi_line(text: str, route: str) -> str:
    """Route B: agent on its own line, immediately before FR's line."""
    lines = text.splitlines()
    fr_idx = next((i for i, l in enumerate(lines) if l.strip() in FR_LINES), None)
    if fr_idx is None:
        raise SetupError("Fast Rendering agent line not found")
    if lines[-1].strip() != MAIN_CLASS:
        raise SetupError(
            f"{MAIN_CLASS} must stay the last line (found {lines[-1]!r}). "
            "Anything after it is treated as a program argument and the agent "
            "silently fails to load.")
    body = [l for l in lines if not re.search(r"-javaagent:[^\s\"]*hypernova\.agent\.jar", l)]
    fr_idx = next(i for i, l in enumerate(body) if l.strip() in FR_LINES)
    body.insert(fr_idx, AGENT_ABS)
    if body[-1].strip() != MAIN_CLASS:
        raise SetupError("main class moved off the last line; aborting")
    return "\n".join(body) + "\n"


# ------------------------------------------------------------------ verify

def verify(text: str, route: str) -> list[str]:
    """Return a list of human-readable problems; empty means all good.

    Order requirements differ per route, so the check is per route:

    * **B** — Hypernova must come *before* ``fr.agent.jar``/``fr.jar``. FR
      rewrites ``TextureData``'s constant pool; a texture transformer running
      after it sees rewritten bytes and its SHA guard misses.
    * **A** — Hypernova goes *after* MixinFR's bridge (see
      :func:`patch_single_line`). On this route the texture patch cannot apply
      either way, because MixinFR rewrites the target class with its own mixins.
    """
    problems: list[str] = []
    agent_at = re.search(r"-javaagent:[^\s\"]*hypernova\.agent\.jar", text)
    if agent_at is None:
        problems.append("Hypernova agent line is missing")
        return problems
    if route == ROUTE_A:
        anchor = next((a for a in MIXIN_LINES if a in text), None)
        if anchor is None:
            problems.append("MixinFR bridge agent line is missing")
        elif agent_at.start() < text.find(anchor):
            problems.append(
                "Hypernova agent is registered BEFORE the MixinFR bridge; "
                "re-install it after the bridge.")
    else:
        found = next((text.find(a) for a in FR_LINES if a in text), -1)
        if found < 0:
            problems.append("Fast Rendering agent line is missing")
        elif agent_at.start() > found:
            problems.append(
                "Hypernova agent is registered AFTER Fast Rendering. It will "
                "load but every patch will silently do nothing "
                "(look for 'textures: unsupported GraphicsLib TextureData').")
    if not text.rstrip().endswith(MAIN_CLASS):
        problems.append(f"{MAIN_CLASS} is not the last token/line")
    if text.count("hypernova.agent.jar") > 1:
        problems.append("Hypernova agent line appears more than once")
    return problems


# ------------------------------------------------------------------ driver

def launch_file_for(game: Path, route: str | None) -> Path:
    if route == ROUTE_B:
        return game / "Miko_Simple.txt"
    if route == ROUTE_A:
        return game / "vmparams"
    raise SetupError("route must be 'a' or 'b'")


def auto_route(game: Path) -> str:
    """Pick the route by looking at which launch file exists and what it says."""
    candidates = [(ROUTE_B, game / "Miko_Simple.txt"), (ROUTE_A, game / "vmparams")]
    for route, path in candidates:
        if not path.is_file():
            continue
        try:
            return detect_route(path.read_text(encoding="utf-8", errors="replace"))
        except SetupError:
            continue
    raise SetupError(
        "could not work out which route this install uses.\n"
        "  Route B needs Miko_Simple.txt with a -javaagent:fr.agent.jar line\n"
        "  Route A needs vmparams with a MixinFR MixinLib-bridge.jar line")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", required=True, help="Starsector install root")
    ap.add_argument("--route", choices=(ROUTE_A, ROUTE_B),
                    help="a = MixinFR single-line vmparams, b = Miko argfile")
    ap.add_argument("--check", action="store_true",
                    help="only verify, never write")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    game = Path(args.game)
    if not game.is_dir():
        print(f"ERROR: not a directory: {game}", file=sys.stderr)
        return 2

    try:
        route = args.route or auto_route(game)
        launch = launch_file_for(game, route)
        if not launch.is_file():
            raise SetupError(f"launch file not found: {launch}")
        original = launch.read_text(encoding="utf-8", errors="replace")

        actual = detect_route(original)
        if actual != route:
            raise SetupError(
                f"you selected route {route!r} but {launch.name} looks like "
                f"route {actual!r}. Re-run without --route to auto-detect.")

        agent_jar = game / "mods/hypernova_infinite_engine/jars" / AGENT_JAR
        if not agent_jar.is_file():
            raise SetupError(
                f"{agent_jar} is missing. Put the hypernova_infinite_engine "
                "folder into mods/ before running this.")

        patched = (patch_single_line if route == ROUTE_A else patch_multi_line)(
            original, route)

        problems = verify(patched, route)
        if problems:
            raise SetupError("internal check failed:\n  " + "\n  ".join(problems))

        print(f"route        : {'A (MixinFR)' if route == ROUTE_A else 'B (Fast Rendering)'}")
        print(f"launch file  : {launch}")
        print(f"format       : {'single line' if route == ROUTE_A else 'multi line'}")

        if args.check:
            existing = verify(original, route)
            if existing:
                print("result       : NOT INSTALLED")
                for p in existing:
                    print(f"  - {p}")
                return 1
            print("result       : OK, agent is installed and correctly ordered")
            return 0

        if patched == original:
            print("result       : already installed, nothing to change")
            return 0

        if args.dry_run:
            print("\n--- would write ---")
            print(patched)
            return 0

        backup = launch.with_name(launch.name + ".bak-hypernova")
        if not backup.exists():
            shutil.copy2(launch, backup)
            print(f"backup       : {backup}")
        else:
            print(f"backup       : {backup} (kept from earlier install)")

        launch.write_text(patched, encoding="utf-8", newline="\n" if route == ROUTE_B else "")
        print("result       : installed")
        print()
        for line in patched.splitlines():
            if "-javaagent:" in line:
                print("  " + line if route == ROUTE_A else "  " + line.strip())
        return 0

    except SetupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
