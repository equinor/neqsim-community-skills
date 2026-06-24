"""Pytest bootstrap for the community skills monorepo.

Each skill ships its importable module under ``skills/<category>/<skill>/src``.
Rather than enumerating every skill in ``pyproject.toml``'s ``pythonpath``,
this conftest discovers all such ``src`` directories and prepends them to
``sys.path`` so the per-skill test modules can import their package directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def _register_skill_src_paths() -> None:
    skills_dir = _ROOT / "skills"
    if not skills_dir.is_dir():
        return
    for src_dir in sorted(skills_dir.glob("*/*/src")):
        if src_dir.is_dir():
            path_str = str(src_dir)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)


_register_skill_src_paths()
