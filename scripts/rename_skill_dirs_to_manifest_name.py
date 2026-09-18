#!/usr/bin/env python3
"""Rename ``skills/<category>/<dir>`` folders to the SKILL.md frontmatter ``name``.

Agent-plugin loaders (VS Code, Copilot CLI, Claude) silently skip a skill whose
directory name differs from the ``name`` declared in ``SKILL.md``. This script
brings the repository layout in line with that rule and rewrites every textual
reference to the old ``skills/<category>/<old-dir>`` path across the repo.

Usage:
    python scripts/rename_skill_dirs_to_manifest_name.py            # dry run
    python scripts/rename_skill_dirs_to_manifest_name.py --apply    # git mv + rewrite
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^name:\s*[\"']?([A-Za-z0-9_.-]+)[\"']?\s*$", re.MULTILINE)
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".toml", ".txt", ".cfg", ".ini"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "data"}


def frontmatter_name(skill_md: Path) -> str | None:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    block = text.split("---", 2)[1]
    match = NAME_RE.search(block)
    return match.group(1) if match else None


def collect_renames() -> list[tuple[Path, Path]]:
    renames = []
    for skill_md in sorted((ROOT / "skills").glob("*/*/SKILL.md")):
        name = frontmatter_name(skill_md)
        if not name or name == skill_md.parent.name:
            continue
        renames.append((skill_md.parent, skill_md.parent.with_name(name)))
    return renames


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        yield path


def rewrite_references(renames, apply: bool) -> int:
    # Longest old path first so a prefix rename cannot clobber a longer one.
    pairs = sorted(
        (
            (old.relative_to(ROOT).as_posix(), new.relative_to(ROOT).as_posix())
            for old, new in renames
        ),
        key=lambda pair: -len(pair[0]),
    )
    touched = 0
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for old_rel, new_rel in pairs:
            updated = updated.replace(old_rel, new_rel)
            updated = updated.replace(old_rel.replace("/", "\\"), new_rel.replace("/", "\\"))
        if updated != text:
            touched += 1
            print("rewrite {}".format(path.relative_to(ROOT).as_posix()))
            if apply:
                path.write_text(updated, encoding="utf-8")
    return touched


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform git mv and rewrite files")
    args = parser.parse_args(argv)

    renames = collect_renames()
    if not renames:
        print("all skill directories already match their manifest name")
        return 0

    for old, new in renames:
        if new.exists():
            print("ERROR: target already exists: {}".format(new), file=sys.stderr)
            return 1
        print("git mv {} -> {}".format(old.relative_to(ROOT).as_posix(), new.name))
        if args.apply:
            subprocess.run(["git", "mv", str(old), str(new)], check=True, cwd=str(ROOT))

    touched = rewrite_references(renames, args.apply)
    verb = "rewrote" if args.apply else "would rewrite"
    print("{} {} directories; {} {} files".format(
        "renamed" if args.apply else "would rename", len(renames), verb, touched))
    if not args.apply:
        print("dry run - re-run with --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
