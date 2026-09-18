"""Shared fixtures: synthetic OLGA files matching the verified 2025.1.0 layout."""

from __future__ import annotations

from pathlib import Path

import pytest

TPL_TEXT = """'OLGA 2025.1.0.24773'
TIME PLOT
INPUT FILE
'demo.genkey'
PVT FILES
'./demo.tab'
DATE
'26-08-14 12:00:00'
PROJECT
''
TITLE
''
AUTHOR
''
NETWORK
1
GEOMETRY' (M)  '
BRANCH
'PIPELINE'
2
0.000000e+00 5.000000e+02 1.000000e+03
0.000000e+00 0.000000e+00 0.000000e+00
CATALOG
2
PT 'POSITION:' 'BRANCH:' 'PIPELINE' 'PIPE:' 'PIPE-1' 'NR:' '1'  '(PA)' 'Pressure'
TM 'POSITION:' 'BRANCH:' 'PIPELINE' 'PIPE:' 'PIPE-1' 'NR:' '1'  '(C)' 'Fluid temperature'
TIME SERIES  ' (S)  '
0.000000e+00 1.000000e+07 5.000000e+01
1.000000e+01 9.500000e+06 4.800000e+01
2.000000e+01 9.000000e+06 4.500000e+01
"""

PPL_TEXT = """'OLGA 2025.1.0.24773'
PROFILE PLOT
INPUT FILE
'demo.genkey'
PVT FILES
'./demo.tab'
DATE
'26-08-14 12:00:00'
PROJECT
''
TITLE
''
AUTHOR
''
NETWORK
1
GEOMETRY ' (M)  '
BRANCH
'PIPELINE'
2
0.000000e+00 5.000000e+02 1.000000e+03
0.000000e+00 0.000000e+00 0.000000e+00
CATALOG
2
PT 'BOUNDARY:' 'BRANCH:' 'PIPELINE' '(PA)' 'Pressure'
HOL 'SECTION:' 'BRANCH:' 'PIPELINE' '(-)' 'Holdup (liquid volume fraction including solids)'
TIME SERIES  ' (S)  '
0.000000e+00
1.000000e+07 9.000000e+06 8.000000e+06
5.000000e-01 4.000000e-01
1.000000e+01
9.500000e+06 8.500000e+06 7.500000e+06
5.500000e-01 4.500000e-01
"""

GENKEY_TEXT = """!*******************************************
! Demo case
!*******************************************
OPTIONS TEMPERATURE=WALL, STEADYSTATE=ON, COMPOSITIONAL=OFF
FILES PVTFILE=(./demo.tab, ./water.tab)
INTEGRATION ENDTIME=5 h, MAXDT=1 s, MINDT=0.001 s, STARTTIME=0 s
! INTEGRATION ENDTIME=99 h   <- commented out, must be ignored
TREND DTPLOT=10 s
PIPE LABEL="Pipe-1", DIAMETER=0.2 m, NSEGMENT=10, \\
        ROUGHNESS=2.8e-05 m, WALL="WALL-1"
PIPE LABEL="Pipe-2", DIAMETER=0.3 m, NSEGMENT=5
"""


@pytest.fixture()
def tpl_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo.tpl"
    path.write_text(TPL_TEXT, encoding="utf-8")
    return path


@pytest.fixture()
def ppl_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo.ppl"
    path.write_text(PPL_TEXT, encoding="utf-8")
    return path


@pytest.fixture()
def genkey_text() -> str:
    return GENKEY_TEXT


@pytest.fixture()
def fake_install_root(tmp_path: Path) -> Path:
    """Create a search root holding two OLGA versions plus decoy folders."""
    root = tmp_path / "Schlumberger"
    for version in ("2025.1.0", "2024.1.5"):
        executables = root / f"Olga {version}" / "OlgaExecutables"
        executables.mkdir(parents=True)
        (executables / f"Olga-{version}.exe").write_text("", encoding="utf-8")
        (root / f"Olga {version}" / "OPGFramework.exe").write_text("", encoding="utf-8")
    # Decoys that must not be reported as the simulator.
    (root / "OLGA-S 2025.1.0" / "OlgaExecutables").mkdir(parents=True)
    (root / "OLGA-S 2025.1.0" / "OlgaExecutables" / "Olga-2025.1.0.exe").write_text("", encoding="utf-8")
    (root / "OLGA Namespace Explorer 7.3.34").mkdir(parents=True)
    (root / "Common").mkdir(parents=True)
    return root
