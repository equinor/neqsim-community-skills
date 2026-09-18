"""Guard the single-install packaging contract used by agent plugins.

``setup.py`` aggregates every ``skills/<category>/<skill>/src/<package>`` into
one distribution so a plugin ``SessionStart`` hook can run one
``pip install -e`` for the whole repo. That only works while every top-level
package name is unique, which this test enforces.
"""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills"

sys.path.insert(0, str(REPOSITORY_ROOT))


def _top_level_packages():
    owners = {}
    for src in sorted(SKILL_ROOT.glob("*/*/src")):
        for child in sorted(src.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                owners.setdefault(child.name, []).append(src.parent.name)
    return owners


def test_skill_package_names_are_unique() -> None:
    owners = _top_level_packages()
    assert owners, "no skill packages found under skills/*/*/src"
    duplicates = {name: skills for name, skills in owners.items() if len(skills) > 1}
    assert not duplicates, f"duplicate top-level packages across skills: {duplicates}"


def test_setup_discovers_every_skill_package() -> None:
    import setup as root_setup  # noqa: PLC0415  (imports the repo's setup.py)

    expected = set(_top_level_packages())
    assert set(root_setup.PACKAGE_DIR) == expected
    assert all(rel.startswith("skills/") for rel in root_setup.PACKAGE_DIR.values())
