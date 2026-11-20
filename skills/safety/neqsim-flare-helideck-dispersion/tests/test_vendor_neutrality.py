"""The skill is vendor neutral: no company, asset, tool or document identifiers anywhere."""

from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
# built from fragments so that this file does not contain the terms itself
BANNED = [
    "equi" + "nor",
    "gull" + "faks",
    "st" + "id",
    "ec" + "ho 3d",
    "tr" + "1965",
    "tr" + "2237",
    "tr" + "3001",
    "sd-" + "308",
    "kfx " + "study",
    "2003 " + "flacs",
]
SUFFIXES = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt"}


def skill_files():
    for path in SKILL_ROOT.rglob("*"):
        if (
            path.is_file()
            and path.suffix in SUFFIXES
            and "__pycache__" not in path.parts
            and "egg-info" not in str(path)
        ):
            yield path


def test_no_vendor_or_site_identifiers():
    hits = []
    for path in skill_files():
        if path.name == "test_vendor_neutrality.py":
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in BANNED:
            if term in text:
                hits.append(f"{path.relative_to(SKILL_ROOT)}: {term}")
    assert not hits, hits


def test_no_absolute_user_paths_in_code():
    for path in skill_files():
        if path.suffix != ".py" or path.name == "test_vendor_neutrality.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users" not in text and "/home/" not in text, path
