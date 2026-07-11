"""Validate every SKILL.md against the shared skill-manifest schema.

Exercises the vendored ``scripts/validate_skill_manifests.py`` so schema
conformance, the ``USE WHEN:`` trigger clause, and canonical skill namespaces
are enforced in CI. Also guards against drift between the vendored schema copy
and the canonical schema in the core NeqSim repo when it is checked out
alongside this one.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_skill_manifests as validator  # noqa: E402


class SkillManifestSchemaTests(unittest.TestCase):
    def test_schema_file_present(self):
        self.assertTrue((REPO_ROOT / "schemas" / "skill-manifest.schema.json").exists())

    def test_all_manifests_conform(self):
        errors, _warnings = validator.validate_repo(REPO_ROOT)
        self.assertEqual(errors, [], "skill manifest errors:\n" + "\n".join(errors))

    def test_use_when_clause_is_required(self):
        self.assertTrue(validator.check_use_when({"description": "no trigger here"}))
        self.assertEqual(
            validator.check_use_when({"description": "Screening. USE WHEN: a task needs it."}),
            [],
        )

    def test_vendored_schema_matches_core_canonical_when_present(self):
        canonical = (
            REPO_ROOT.parent
            / "neqsim"
            / "docs"
            / "integration"
            / "schemas"
            / "skill-manifest.schema.json"
        )
        if not canonical.exists():
            self.skipTest("core neqsim repo not checked out alongside this repo")
        vendored = REPO_ROOT / "schemas" / "skill-manifest.schema.json"
        self.assertEqual(
            json.loads(vendored.read_text(encoding="utf-8")),
            json.loads(canonical.read_text(encoding="utf-8")),
            "vendored skill schema has drifted from the canonical core schema",
        )


if __name__ == "__main__":
    unittest.main()
