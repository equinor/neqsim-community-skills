"""Run the FMIRR skill on the synthetic example register."""

import json
import sys
from pathlib import Path

from technology_fmirr import from_dict


def main() -> None:
    spec = json.loads((Path(__file__).parent / "example_fmirr.json").read_text(encoding="utf-8"))
    result = from_dict(spec).evaluate()

    summary = result["summary"]
    print(f"Technology:      {result['technology']}")
    print(f"Failure modes:   {summary['total']}  {summary['counts']}")
    print(f"Critical:        {summary['critical_ids']}")
    for row in result["rows"]:
        print(f"  {row['id']:<7} C{row['consequence_class']} P{row['probability_class']}  {row['risk']:<6} {row['failure_mode']}")
    print("Findings:")
    for finding in result["findings"]:
        print(f"  [{finding['level']}] {finding['entry_id']} {finding['text']}")

    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
