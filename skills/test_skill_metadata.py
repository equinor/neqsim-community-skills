import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills"
CATALOG = REPOSITORY_ROOT / "community-skills.yaml"
REQUIRED_SECTIONS = (
    "## When to Use",
    "## Inputs",
    "## Outputs",
    "## Engineering Method",
    "## Python Usage Pattern",
    "## Validation Checklist",
    "## Common Mistakes",
    "## Limitations",
    "## References",
)


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", 2)
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields


def test_all_public_skills_have_required_frontmatter_and_sections() -> None:
    skill_files = sorted(SKILL_ROOT.glob("*/*/SKILL.md"))

    assert len(skill_files) >= 9
    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        metadata = _frontmatter(text)

        assert metadata["name"].startswith("neqsim-")
        assert re.fullmatch(r"\d+\.\d+\.\d+", metadata["version"]), (
            f"{skill_file} has non-semver version {metadata['version']!r}"
        )
        assert "USE WHEN:" in metadata["description"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata["last_verified"]), (
            f"{skill_file} has invalid last_verified {metadata['last_verified']!r}"
        )
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{skill_file} missing {section}"


def test_catalog_preview_points_to_existing_skill_files() -> None:
    catalog_text = CATALOG.read_text(encoding="utf-8")

    for skill_file in sorted(SKILL_ROOT.glob("*/*/SKILL.md")):
        relative_path = skill_file.relative_to(REPOSITORY_ROOT).as_posix()
        metadata = _frontmatter(skill_file.read_text(encoding="utf-8"))

        assert f'name: {metadata["name"]}' in catalog_text
        assert f'path: "{relative_path}"' in catalog_text