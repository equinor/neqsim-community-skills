"""Round calculated sizes up to standard sizes for a small example."""

import json

from standard_equipment_sizes import next_motor_kw, select_api526_orifice, select_pipe_nps

if __name__ == "__main__":
    print(
        json.dumps(
            {
                "pipe": select_pipe_nps(150.0, 7.1),
                "psv": select_api526_orifice(1200.0),
                "motor_kw": next_motor_kw(212.0, 0.1),
            },
            indent=2,
        )
    )
