#!/usr/bin/env python3
"""Consolidation pass for the skill catalog: find near-duplicate skills and orphans.

Skill/agent sprawl is the main long-term maintenance risk for these catalogs.
This advisory tool surfaces two consolidation signals over every
``skills/*/*/SKILL.md`` so a periodic review can dedupe, merge, or retire:

1. **Near-duplicate skills** — pairs whose ``description`` (and optionally name)
   are highly similar, which usually means overlapping methods that should be
   merged or cross-referenced. Similarity is a dependency-free blend of a token
   Jaccard overlap and a ``difflib`` sequence ratio over the description text.

2. **Orphan skills** — skills that no agent declares in ``required_skills`` or
   ``context_skills`` and that no other skill lists in ``required_skills``. When
   the agent catalogs are reachable (via a sibling checkout or the
   ``NEQSIM_COMMUNITY_AGENTS_DIR`` / ``NEQSIM_ENTERPRISE_AGENTS_DIR`` env vars),
   the referenced-skill set is built from every ``agents/*/agent.yaml``; when
   they are not reachable, the orphan check is skipped with a note (it never
   hard-fails on a missing sibling repo). Enterprise agents are scanned too when
   present, because an enterprise agent may be the only consumer of a community
   skill.

The script is **advisory**: it exits 0 by default so it can run in CI as an
informational step. Use ``--fail-on-duplicates`` to make a high-similarity pair
fail the build once a catalog is clean.

Usage
-----
    python scripts/find_skill_overlap.py                 # console report
    python scripts/find_skill_overlap.py --threshold 0.82
    python scripts/find_skill_overlap.py --json report.json
    python scripts/find_skill_overlap.py --fail-on-duplicates

Exit codes
----------
    0 - report produced (advisory), or no pairs at/above threshold with --fail-on-duplicates
    1 - with --fail-on-duplicates, at least one pair is at/above the threshold
    2 - usage / I/O error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
NAME_RE = re.compile(r'^\s*name:\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)
DESC_RE = re.compile(r'^\s*description:\s*(.+?)\s*$', re.MULTILINE)
SKILL_ID_RE = re.compile(r"(?<![a-z0-9-])((?:neqsim|enterprise)-[a-z0-9]+(?:-[a-z0-9]+)*)")

# Common words that carry little discriminating signal for skill descriptions.
STOPWORDS = frozenset(
    """a an and the of to for in on with use used using when this that these those
    or as is are be by from at into it its screening skill agent neqsim enterprise
    company style community method methods before verified review human required
    placeholder demo internal workflows workflow task tasks not final only public""".split()
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def read_frontmatter(path: Path) -> Optional[Dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    m = FRONTMATTER_RE.search(text)
    block = m.group(1) if m else text[:2000]
    name_m = NAME_RE.search(block)
    desc_m = DESC_RE.search(block)
    if not name_m:
        return None
    desc = desc_m.group(1).strip().strip('"').strip("'") if desc_m else ""
    return {"name": name_m.group(1).strip(), "description": desc, "path": str(path)}


def collect_skills(skills_dir: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for skill_md in sorted(skills_dir.glob("*/*/SKILL.md")):
        fm = read_frontmatter(skill_md)
        if fm:
            out.append(fm)
    return out


def tokenize(text: str) -> frozenset:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w for w in words if w not in STOPWORDS and len(w) > 2)


def similarity(a: Dict[str, str], b: Dict[str, str]) -> float:
    """Blend token Jaccard and sequence ratio over the descriptions (0..1)."""
    ta, tb = tokenize(a["description"]), tokenize(b["description"])
    if ta and tb:
        jacc = len(ta & tb) / len(ta | tb)
    else:
        jacc = 0.0
    seq = SequenceMatcher(None, a["description"], b["description"]).ratio()
    # Name closeness nudges the score (near-identical names are a strong signal).
    name_seq = SequenceMatcher(None, a["name"], b["name"]).ratio()
    return round(0.5 * jacc + 0.4 * seq + 0.1 * name_seq, 3)


def find_duplicates(skills: List[Dict[str, str]], threshold: float) -> List[Tuple[float, str, str]]:
    pairs: List[Tuple[float, str, str]] = []
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            score = similarity(skills[i], skills[j])
            if score >= threshold:
                pairs.append((score, skills[i]["name"], skills[j]["name"]))
    pairs.sort(reverse=True)
    return pairs


def _candidate_agent_dirs(repo_root: Path) -> List[Path]:
    candidates: List[Path] = []
    for env in ("NEQSIM_COMMUNITY_AGENTS_DIR", "NEQSIM_ENTERPRISE_AGENTS_DIR"):
        val = os.environ.get(env)
        if val:
            candidates.append(Path(val))
    parent = repo_root.parent
    for name in ("neqsim-community-agents", "neqsim-enterprise-agents"):
        candidates.append(parent / name)
    return [c for c in candidates if (c / "agents").is_dir()]


def referenced_skill_ids(agent_dirs: List[Path]) -> Optional[set]:
    if not agent_dirs:
        return None
    referenced: set = set()
    for agent_dir in agent_dirs:
        for manifest in (agent_dir / "agents").glob("*/agent.yaml"):
            try:
                text = manifest.read_text(encoding="utf-8")
            except OSError:
                continue
            for sid in SKILL_ID_RE.findall(text):
                referenced.add(sid)
    return referenced


def referenced_by_skills(skills_dir: Path) -> set:
    """Skill ids that appear in another skill's required_skills frontmatter."""
    referenced: set = set()
    for skill_md in skills_dir.glob("*/*/SKILL.md"):
        fm_self = read_frontmatter(skill_md)
        self_name = fm_self["name"] if fm_self else None
        try:
            text = skill_md.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        m = FRONTMATTER_RE.search(text)
        block = m.group(1) if m else ""
        for sid in SKILL_ID_RE.findall(block):
            if sid != self_name:
                referenced.add(sid)
    return referenced


def find_orphans(skills: List[Dict[str, str]], skills_dir: Path, repo_root: Path):
    agent_dirs = _candidate_agent_dirs(repo_root)
    by_agents = referenced_skill_ids(agent_dirs)
    if by_agents is None:
        return None, []  # agent catalogs unreachable
    by_skills = referenced_by_skills(skills_dir)
    referenced = by_agents | by_skills
    orphans = [s["name"] for s in skills if s["name"] not in referenced]
    orphans.sort()
    return [str(d) for d in agent_dirs], orphans


def main() -> int:
    parser = argparse.ArgumentParser(description="Find near-duplicate and orphan skills")
    parser.add_argument("--threshold", type=float, default=0.80, help="Similarity threshold (0..1) for near-duplicates")
    parser.add_argument("--json", metavar="PATH", help="Also write the report as JSON")
    parser.add_argument("--fail-on-duplicates", action="store_true", help="Exit 1 if any pair >= threshold")
    args = parser.parse_args()

    repo_root = repo_root_from_script()
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        print(f"ERROR: skills/ not found under {repo_root}", file=sys.stderr)
        return 2

    skills = collect_skills(skills_dir)
    duplicates = find_duplicates(skills, args.threshold)
    agent_dirs, orphans = find_orphans(skills, skills_dir, repo_root)

    print(f"Consolidation pass over {len(skills)} skills (threshold {args.threshold})\n")

    print(f"Near-duplicate skill pairs (>= {args.threshold}): {len(duplicates)}")
    for score, a, b in duplicates:
        print(f"  {score:.3f}  {a}  <->  {b}")
    if not duplicates:
        print("  (none)")

    print()
    if agent_dirs is None:
        print("Orphan skills: SKIPPED (agent catalogs not reachable — set "
              "NEQSIM_COMMUNITY_AGENTS_DIR / NEQSIM_ENTERPRISE_AGENTS_DIR or place "
              "the agent repos as siblings)")
    else:
        print(f"Orphan skills (not referenced by any agent or skill): {len(orphans)}")
        print(f"  [agent catalogs scanned: {', '.join(agent_dirs) or 'none'}]")
        for name in orphans:
            print(f"  {name}")
        if not orphans:
            print("  (none)")

    if args.json:
        report = {
            "schema": "skill_overlap_report.v1",
            "skill_count": len(skills),
            "threshold": args.threshold,
            "near_duplicates": [
                {"score": s, "a": a, "b": b} for s, a, b in duplicates
            ],
            "orphans": None if agent_dirs is None else orphans,
            "agent_catalogs_scanned": agent_dirs or [],
        }
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")

    if args.fail_on_duplicates and duplicates:
        print("\nFAIL: near-duplicate skills found (--fail-on-duplicates).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
