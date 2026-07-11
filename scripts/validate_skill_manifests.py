#!/usr/bin/env python3
"""Validate SKILL.md frontmatter against the shared NeqSim skill schema.

This script is intentionally self-contained and identical across the community
and enterprise skill repositories. It performs three families of checks over
every ``skills/*/*/SKILL.md`` frontmatter block:

1. Structural validation against the vendored
   ``schemas/skill-manifest.schema.json``. Uses the ``jsonschema`` package when
   available; otherwise falls back to a minimal built-in structural check so the
   script never hard-fails on a missing optional dependency.

2. A ``USE WHEN:`` trigger clause must be present in ``description`` (checked
   case-insensitively) so agents can decide when to load the skill.

3. Namespace hygiene: ``name`` and every ``required_skills`` entry must use a
   canonical namespace (``neqsim-*`` for core/community, ``enterprise-*`` for
   internal skills). Enforced by the schema and re-checked here for a clearer
   message.

Exit codes:
    0 - all checks pass (warnings allowed)
    1 - one or more errors found
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:  # pragma: no cover
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

try:  # optional, richer validation when present
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


NAME_RE = re.compile(r"^(neqsim|enterprise)-[a-z0-9]+(-[a-z0-9]+)*$")


def repo_root_from_script():
    return Path(__file__).resolve().parents[1]


def load_schema(repo_root):
    schema_path = repo_root / "schemas" / "skill-manifest.schema.json"
    if not schema_path.exists():
        return None, schema_path
    return json.loads(schema_path.read_text(encoding="utf-8")), schema_path


def parse_frontmatter(text):
    """Return the parsed YAML frontmatter mapping, or None if absent/invalid."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def minimal_structural_check(manifest, schema):
    errors = []
    for key in schema.get("required", []):
        if key not in manifest:
            errors.append("missing required field '{}'".format(key))
    name = manifest.get("name")
    if isinstance(name, str) and not NAME_RE.match(name):
        errors.append("name '{}' is not a canonical skill id".format(name))
    version = manifest.get("version")
    if isinstance(version, str) and not re.match(r"^\d+\.\d+\.\d+$", version):
        errors.append("version '{}' is not semver".format(version))
    for skill in manifest.get("required_skills") or []:
        if not isinstance(skill, str) or not NAME_RE.match(skill):
            errors.append("required_skills entry '{}' is not a canonical id".format(skill))
    return errors


def validate_against_schema(manifest, schema):
    if jsonschema is not None:
        validator = jsonschema.Draft7Validator(schema)
        return [
            "{}: {}".format("/".join(str(p) for p in err.path) or "<root>", err.message)
            for err in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))
        ]
    return minimal_structural_check(manifest, schema)


def check_use_when(manifest):
    description = manifest.get("description")
    if not isinstance(description, str) or "use when" not in description.lower():
        return ["description must contain a 'USE WHEN:' trigger clause"]
    return []


def validate_repo(repo_root):
    schema, schema_path = load_schema(repo_root)
    if schema is None:
        return ["schema not found at {}".format(schema_path)], []

    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return ["skills/ directory not found at {}".format(skills_dir)], []

    manifests = sorted(skills_dir.glob("*/*/SKILL.md"))
    if not manifests:
        return ["no SKILL.md files found under {}".format(skills_dir)], []

    errors, warnings = [], []
    for skill_md in manifests:
        rel = skill_md.relative_to(repo_root).as_posix()
        text = skill_md.read_text(encoding="utf-8")
        manifest = parse_frontmatter(text)
        if manifest is None:
            errors.append("[{}] missing or invalid YAML frontmatter".format(rel))
            continue
        for err in validate_against_schema(manifest, schema):
            errors.append("[{}] schema: {}".format(rel, err))
        for err in check_use_when(manifest):
            errors.append("[{}] {}".format(rel, err))

    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (defaults to the parent of this scripts/ folder).",
    )
    args = parser.parse_args(argv)

    errors, warnings = validate_repo(args.repo_root.resolve())
    for warning in warnings:
        print("WARNING: {}".format(warning))
    for error in errors:
        print("ERROR: {}".format(error))
    if jsonschema is None:
        print("NOTE: jsonschema not installed - used minimal structural checks only.")

    if errors:
        print("\nSkill manifest validation FAILED ({} errors).".format(len(errors)))
        return 1
    print("\nSkill manifest validation passed ({} warnings).".format(len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
