#!/usr/bin/env python3
"""Report (and optionally backfill) the ``calculation_basis`` field on every SKILL.md.

``calculation_basis`` tells an agent how a skill's numbers are produced, so a
multi-skill pipeline can weigh rigor programmatically instead of parsing prose:

    screening      public/educational correlations in pure Python
    neqsim-java    drives the NeqSim Java engine (EOS flash, process solve, PVT)
    hybrid         screening correlations plus at least one NeqSim-backed step
    data-retrieval returns source data/evidence, performs no engineering calculation
    advisory       methodology/governance/reporting guidance, no numeric output

The classifier is evidence-based, not name-based: it inspects the frontmatter
``requires`` block and the body for NeqSim imports/MCP tools, retrieval verbs,
and explicit "screening" self-declarations. It is deliberately conservative --
anything it cannot justify is reported as ``unclassified`` for a human to set,
rather than guessed.

Usage
-----
    python scripts/classify_calculation_basis.py            # report only
    python scripts/classify_calculation_basis.py --write    # backfill frontmatter
    python scripts/classify_calculation_basis.py --check    # exit 1 if any missing

Exit codes
----------
    0 - report produced, or --check passed
    1 - with --check, at least one skill has no calculation_basis
    2 - usage / I/O error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
NAME_RE = re.compile(r'^\s*name:\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)
BASIS_RE = re.compile(r'^\s*calculation_basis:\s*["\']?([a-z-]+)["\']?\s*$', re.MULTILINE)

VALID = ("screening", "neqsim-java", "hybrid", "data-retrieval", "advisory")

# Evidence that the skill actually drives the NeqSim Java engine.
NEQSIM_JAVA_PATTERNS = (
    re.compile(r"\bfrom\s+neqsim\s+import\b"),
    re.compile(r"\bjneqsim\b"),
    re.compile(r"\bneqsim\.(?:thermo|process|pvtsimulation|standards)\b"),
    re.compile(r"\bSystemSrkEos\b|\bSystemPrEos\b|\bSystemSrkCPA\w*\b"),
    re.compile(r"\bProcessSystem\b|\bThermodynamicOperations\b"),
    re.compile(r"\bTPflash\(\)|\binitProperties\(\)"),
    re.compile(r"\bmcp_neqsim\w*_run\w+", re.IGNORECASE),
)
# Evidence the skill only fetches/normalizes source data.
RETRIEVAL_PATTERNS = (
    re.compile(r"\bread-only\b", re.IGNORECASE),
    re.compile(r"\bREST (?:API|client)\b", re.IGNORECASE),
    re.compile(r"\brequest plan(?:ner)?\b", re.IGNORECASE),
    re.compile(r"\bdownload(?:s|ed)?\b.*\bdocument", re.IGNORECASE),
)
# Explicit self-declared screening language (the community catalog uses this a lot).
SCREENING_PATTERNS = (
    re.compile(r"\bscreening[- ]level\b", re.IGNORECASE),
    re.compile(r"\beducational\b", re.IGNORECASE),
    re.compile(r"\border[- ]of[- ]magnitude\b", re.IGNORECASE),
    re.compile(r"\bbefore (?:a )?(?:detailed|rigorous|validated|verified)\b", re.IGNORECASE),
)
ADVISORY_PATTERNS = (
    re.compile(r"\bno numeric output\b", re.IGNORECASE),
    re.compile(r"\breporting (?:standard|convention|schema)\b", re.IGNORECASE),
    re.compile(r"\bgovernance\b", re.IGNORECASE),
    re.compile(r"\bmethodology\b", re.IGNORECASE),
)
# Enterprise catalogs express the same three ideas with a different vocabulary:
# a policy overlay that gates a community screening result, an evidence pack that
# only structures source data, and a renderer that only formats a deliverable.
POLICY_OVERLAY_PATTERNS = (
    re.compile(r"\bpolicy\b", re.IGNORECASE),
    re.compile(r"\bverdict\b", re.IGNORECASE),
    re.compile(r"\bcompliance\b", re.IGNORECASE),
    re.compile(r"\bpass\s*/\s*review\s*/\s*fail\b", re.IGNORECASE),
    re.compile(r"\bacceptance (?:criteri|gate)", re.IGNORECASE),
    re.compile(r"\bon top of the (?:community|public)\b", re.IGNORECASE),
)
EVIDENCE_PACK_PATTERNS = (
    re.compile(r"\bhand-?off\b", re.IGNORECASE),
    re.compile(r"\bevidence pack\b", re.IGNORECASE),
    re.compile(r"\bingestion shape\b", re.IGNORECASE),
    re.compile(r"\bscaffold\b", re.IGNORECASE),
    re.compile(r"\bpreparation document\b", re.IGNORECASE),
    re.compile(r"\bsource-?traceable\b", re.IGNORECASE),
    re.compile(r"\bnever collects? secrets?\b", re.IGNORECASE),
    re.compile(r"\bSSO\b|\bbearer\b|\bAPIM\b"),
)
RENDERER_PATTERNS = (
    re.compile(r"\bconvert(?:ing|s)?\b.*\b(?:to|into)\s+(?:PDF|HTML|PowerPoint)", re.IGNORECASE),
    re.compile(r"\b(?:python-pptx|headless browser|renderer)\b", re.IGNORECASE),
    re.compile(r"\bdeliverable\b", re.IGNORECASE),
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


CODE_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)


def _code_blocks(body: str) -> str:
    """Concatenate fenced code blocks.

    A skill that *calls* NeqSim has the import/class inside a code fence; a
    screening skill that merely *refers* to NeqSim for the rigorous follow-up
    mentions it in prose. Counting only code blocks is what separates the two.
    """
    return "\n".join(CODE_FENCE_RE.findall(body))


def _count(patterns, text: str) -> int:
    return sum(1 for p in patterns if p.search(text))


def classify(text: str, area: str = "", folder: str = "") -> Tuple[Optional[str], str]:
    """Return (basis, rationale) or (None, reason) when it cannot be justified.

    @param text the full SKILL.md content
    @param area the catalog area folder (e.g. ``engineering-data``, ``reporting``)
    @param folder the skill's own folder name, used only by the fallback tier
    """
    m = FRONTMATTER_RE.search(text)
    front = m.group(2) if m else ""
    body = text[m.end():] if m else text
    code = _code_blocks(body)

    # A wrapper skill hides NeqSim behind its own package API, so the code fence
    # shows `from <skill_pkg> import ...` rather than a NeqSim import. Declaring
    # java_packages: [neqsim] is then the reliable evidence it drives the engine.
    declares_java_dep = bool(re.search(r"java_packages:\s*\[[^\]]*neqsim", front))
    declares_neqsim_dep = declares_java_dep or bool(re.search(r"requires_mcp_tools:", front))
    java_hits = _count(NEQSIM_JAVA_PATTERNS, code)
    screening_hits = _count(SCREENING_PATTERNS, text)
    retrieval_hits = _count(RETRIEVAL_PATTERNS, text)
    advisory_hits = _count(ADVISORY_PATTERNS, text)
    policy_hits = _count(POLICY_OVERLAY_PATTERNS, text)
    evidence_hits = _count(EVIDENCE_PACK_PATTERNS, text)
    renderer_hits = _count(RENDERER_PATTERNS, text)
    # An overlay whose required_skills point at a community screening skill is,
    # by construction, a policy gate on a screening result.
    overlays_screening = bool(re.search(r"required_skills:[^\n]*\n(?:\s*-\s*neqsim-[a-z-]*screening[^\n]*\n)", front))

    if java_hits >= 2 or declares_java_dep or (java_hits >= 1 and declares_neqsim_dep):
        evidence = f"java_code={java_hits}, java_dep={declares_java_dep}"
        if screening_hits >= 3:
            return "hybrid", f"neqsim engine ({evidence}) plus screening language ({screening_hits})"
        return "neqsim-java", f"neqsim engine ({evidence})"
    if screening_hits >= 2:
        return "screening", f"screening language ({screening_hits}), no neqsim call in code"
    if overlays_screening or policy_hits >= 3:
        return "screening", f"policy overlay on a screening method (policy={policy_hits}, overlays={overlays_screening})"
    if retrieval_hits >= 2 or evidence_hits >= 3:
        return "data-retrieval", f"retrieval/evidence language (retrieval={retrieval_hits}, evidence={evidence_hits})"
    if renderer_hits >= 2 or advisory_hits >= 2:
        return "advisory", f"renderer/advisory language (renderer={renderer_hits}, advisory={advisory_hits})"

    # Fallback tier: catalog placement and name suffix are weaker but transparent
    # signals. The rationale records that the call came from here, so a reviewer
    # can see which assignments were structural rather than evidence-based.
    if area == "reporting":
        return "advisory", "fallback: reporting area (formats a deliverable, no calculation)"
    if area == "engineering-data":
        return "data-retrieval", "fallback: engineering-data area (connector/reader/extractor)"
    if folder.endswith(("-review", "-compliance", "-screening")):
        return "screening", f"fallback: '{folder}' name suffix indicates a screening/policy gate"

    return None, (
        f"inconclusive (java_code={java_hits}, screening={screening_hits}, "
        f"retrieval={retrieval_hits}, advisory={advisory_hits}, "
        f"policy={policy_hits}, evidence={evidence_hits}, renderer={renderer_hits})"
    )


def write_basis(path: Path, text: str, basis: str) -> bool:
    """Insert calculation_basis into the frontmatter after the name line."""
    m = FRONTMATTER_RE.search(text)
    if not m:
        return False
    front = m.group(2)
    if BASIS_RE.search(front):
        return False
    name_m = NAME_RE.search(front)
    if not name_m:
        return False
    insert_at = name_m.end()
    new_front = front[:insert_at] + f'\ncalculation_basis: "{basis}"' + front[insert_at:]
    path.write_text(text[:m.start(2)] + new_front + text[m.end(2):], encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Report/backfill skill calculation_basis")
    parser.add_argument("--write", action="store_true", help="Backfill confidently-classified skills")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any skill lacks calculation_basis")
    args = parser.parse_args()

    skills_dir = repo_root_from_script() / "skills"
    if not skills_dir.is_dir():
        print(f"ERROR: skills/ not found under {repo_root_from_script()}", file=sys.stderr)
        return 2

    existing: List[str] = []
    assigned: List[Tuple[str, str, str]] = []
    unclassified: List[Tuple[str, str]] = []

    for skill_md in sorted(skills_dir.glob("*/*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        m = FRONTMATTER_RE.search(text)
        front = m.group(2) if m else ""
        name_m = NAME_RE.search(front)
        name = name_m.group(1).strip() if name_m else skill_md.parent.name

        current = BASIS_RE.search(front)
        if current:
            existing.append(f"{name}: {current.group(1)}")
            continue

        basis, rationale = classify(text, area=skill_md.parent.parent.name, folder=skill_md.parent.name)
        if basis is None:
            unclassified.append((name, rationale))
            continue
        assigned.append((name, basis, rationale))
        if args.write:
            write_basis(skill_md, text, basis)

    total = len(existing) + len(assigned) + len(unclassified)
    print(f"calculation_basis pass over {total} skills\n")
    print(f"Already set: {len(existing)}")
    for line in existing:
        print(f"  {line}")
    verb = "Backfilled" if args.write else "Would set"
    print(f"\n{verb}: {len(assigned)}")
    by_basis: Dict[str, int] = {}
    for name, basis, rationale in assigned:
        by_basis[basis] = by_basis.get(basis, 0) + 1
        print(f"  {basis:<14} {name}   [{rationale}]")
    if by_basis:
        print("\n  totals: " + ", ".join(f"{k}={v}" for k, v in sorted(by_basis.items())))
    print(f"\nUnclassified (set manually): {len(unclassified)}")
    for name, rationale in unclassified:
        print(f"  {name}   [{rationale}]")

    if args.check and (assigned or unclassified):
        print("\nFAIL: skills without calculation_basis (--check).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
