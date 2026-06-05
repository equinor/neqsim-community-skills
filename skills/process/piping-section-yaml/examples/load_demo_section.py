from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from piping_section_yaml import (
    fittings_equivalent_length,
    inspect_section,
    load_section,
    load_yaml_file,
    total_elevation,
    total_length,
)


def main() -> None:
    yaml_path = Path(__file__).resolve().parent / "demo_inlet.yaml"
    section = load_section(load_yaml_file(str(yaml_path)))

    print(f"Section: {section.section_id}")
    print(f"  segments: {len(section.segments)}  equipment: {len(section.equipment)}")
    print(f"  total length [m]: {total_length(section):.2f}")
    print(f"  net elevation [m]: {total_elevation(section):.2f}")

    extra = fittings_equivalent_length(
        [{"type": "elbow_90", "count": 4}, {"type": "tee_branch", "count": 1}],
        inner_diameter_m=0.467,
    )
    print(f"  S1 fitting equiv length [m]: {extra:.2f}")

    print("  flow path:")
    for row in inspect_section(section):
        indent = "    " + "  " * row.get("depth", 0)
        print(f"{indent}{row['kind']} {row.get('id', '')}".rstrip())


if __name__ == "__main__":
    main()
