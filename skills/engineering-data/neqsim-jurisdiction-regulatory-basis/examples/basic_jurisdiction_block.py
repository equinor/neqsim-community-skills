"""Print the jurisdiction block a study would record for a Norwegian offshore platform."""

import json

from jurisdiction_basis import jurisdiction_block

if __name__ == "__main__":
    print(json.dumps(jurisdiction_block("Norway", "offshore production platform", True), indent=2))
