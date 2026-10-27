"""Run the technology-assessment skill on the synthetic generic synthetic example."""

import json
import sys
from pathlib import Path

from technology_assessment import from_dict


def main() -> None:
    spec = json.loads((Path(__file__).parent / "example_novel_technology.json").read_text(encoding="utf-8"))
    result = from_dict(spec).assess()

    summary = result["summary"]
    print(f"Technology:        {result['technology']}")
    print(f"Role:              {summary['role']}")
    print(f"Highest category:  {summary['highest_category']}")
    print(f"System TRL:        {summary['system_trl']} ({summary['system_trl_name']})")
    print("Elements:")
    for element in result["elements"]:
        print(
            f"  {element['id']:<4} category {element['category_label']:<3} "
            f"TRL {element['trl']}  {element['name']}"
        )
    print("Step-out:")
    for row in result["step_out"]:
        print(f"  {row['dimension']:<22} {row['status']}")
    print("Flags:")
    for flag in result["flags"]:
        print(f"  - {flag}")

    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
