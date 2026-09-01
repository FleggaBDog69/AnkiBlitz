#!/usr/bin/env python3
"""Package each add-on into dist/*.ankiaddon.

An .ankiaddon is a plain zip of the add-on folder's CONTENTS (no wrapping
directory). What goes in is taken from **git's tracked-file list**, not a walk of
the working tree — that is the whole point of doing it this way:

  - ``meta.json`` holds the live config of whoever built the package. Shipping it
    would push the builder's personal settings onto every user, silently
    overwriting theirs on install.
  - ``user_files/`` holds real user data — the break journal, Blitz stats, the
    music profile. Anki preserves it across updates precisely so it is nobody
    else's business.
  - ``__pycache__/`` is stale bytecode for whatever Python the builder happened
    to run.

All three are already in .gitignore, so sourcing from ``git ls-files`` excludes
them by construction rather than by a blocklist someone has to remember to keep
up to date. A file that isn't committed doesn't ship.

Usage:  python3 build.py [addon ...]      (default: all four)
"""

import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

# source folder -> the .ankiaddon name people download
ADDONS = {
    "AnkiBlitz": "AnkiBlitz.ankiaddon",
    "ankiblitz-core": "AnkiBlitzCore.ankiaddon",
    "aSFM": "aSFM.ankiaddon",
    "progressive-reveal": "ProgressiveWordReveal.ankiaddon",
}


def tracked(folder):
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "-z", "--", folder],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(p for p in out.split("\0") if p)


def build(folder, out_name):
    files = tracked(folder)
    if not files:
        raise SystemExit(f"{folder}: nothing tracked — wrong folder name?")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, out_name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            # Paths inside the zip are relative to the add-on folder: Anki
            # unpacks the archive straight into addons21/<package>/.
            z.write(os.path.join(ROOT, rel), os.path.relpath(rel, folder))
    return out, len(files)


def main(argv):
    wanted = argv[1:] or list(ADDONS)
    for folder in wanted:
        if folder not in ADDONS:
            raise SystemExit(f"unknown add-on {folder!r}; try one of {', '.join(ADDONS)}")
        out, n = build(folder, ADDONS[folder])
        size = os.path.getsize(out)
        print(f"{ADDONS[folder]:<28} {n:>3} files  {size/1024:>7.1f} KB")


if __name__ == "__main__":
    main(sys.argv)
