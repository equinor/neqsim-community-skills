"""Aggregate every ``skills/<category>/<skill>/src/<package>`` into one install.

``pyproject.toml`` holds the static project metadata; this file only supplies
the dynamic ``packages`` / ``package_dir`` mapping that setuptools cannot
express declaratively for a monorepo of independently laid-out skills. It lets
an agent plugin (or a developer) make every skill importable in the shared
NeqSim Python environment with a single command::

    <python-executable> -m pip install -e <repo-root>

Package names are unique across the repo (enforced by ``skills/test_skill_packaging.py``).
"""

from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT / "skills"


def discover_packages():
    packages = []
    package_dir = {}
    for src in sorted(SKILLS.glob("*/*/src")):
        if not src.is_dir():
            continue
        rel_src = src.relative_to(ROOT).as_posix()
        for package in find_packages(where=str(src), exclude=("*.tests", "*.tests.*")):
            top = package.split(".", 1)[0]
            if top not in package_dir:
                package_dir[top] = "{}/{}".format(rel_src, top)
            packages.append(package)
    return packages, package_dir


PACKAGES, PACKAGE_DIR = discover_packages()

if __name__ == "__main__":
    setup(packages=PACKAGES, package_dir=PACKAGE_DIR, include_package_data=True)
