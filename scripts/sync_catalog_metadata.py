"""Sync the skills catalogue (`*-skills.yaml`) metadata to each SKILL.md front matter.

The catalogue duplicates `version:` and `description:` per skill, so a SKILL.md edit
that misses the catalogue leaves the installable catalogue stale. Dry-run by default.

    python scripts/sync_catalog_metadata.py                     # dry run, all fields
    python scripts/sync_catalog_metadata.py --apply
    python scripts/sync_catalog_metadata.py --fields version    # versions only

Field selection matters per repo. In neqsim-community-skills the catalogue and the
SKILL.md share one description convention, so both fields sync. In
neqsim-enterprise-skills the catalogue deliberately carries a shorter house-style
summary rather than the SKILL.md "Use when:" text, so sync `version` ONLY there --
rewriting descriptions would destroy an intentional editorial difference.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CATALOG = next(REPO.glob("*-skills.yaml"))
ALL_FIELDS = ("version", "description")


def front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for key in ("name", "version", "description"):
        km = re.search(rf'^{key}:\s*"?(.*?)"?\s*$', m.group(1), re.M)
        if km:
            out[key] = km.group(1)
    return out


def skill_index() -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for skill in sorted((REPO / "skills").glob("*/*/SKILL.md")):
        fm = front_matter(skill)
        if fm.get("name"):
            index[fm["name"]] = fm
    return index


def main(apply: bool, fields: tuple[str, ...]) -> int:
    skills = skill_index()
    lines = CATALOG.read_text(encoding="utf-8").splitlines(keepends=True)
    current: str | None = None
    changes: list[str] = []

    for i, line in enumerate(lines):
        name = re.match(r"^\s*-\s*name:\s*(\S+)\s*$", line)
        if name:
            current = name.group(1)
            continue
        if not current or current not in skills:
            continue
        for key in fields:
            km = re.match(rf'^(\s*){key}:\s*"?(.*?)"?\s*$', line)
            if not km:
                continue
            want = skills[current].get(key)
            if want and km.group(2) != want:
                changes.append(f"{current}.{key}")
                lines[i] = f'{km.group(1)}{key}: "{want}"\n'

    for c in changes:
        print(f"  {c}")
    if not changes:
        print(f"catalogue already in sync ({', '.join(fields)})")
        return 0
    if apply:
        CATALOG.write_text("".join(lines), encoding="utf-8")
        print(f"updated {len(changes)} field(s) in {CATALOG.name}")
    else:
        print("(dry run; pass --apply to write)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    selected = ALL_FIELDS
    if "--fields" in argv:
        selected = tuple(argv[argv.index("--fields") + 1].split(","))
    raise SystemExit(main("--apply" in argv, selected))
