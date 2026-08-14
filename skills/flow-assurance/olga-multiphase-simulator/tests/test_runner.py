from __future__ import annotations

from pathlib import Path

import pytest

from olga_multiphase_simulator import OlgaRunner, describe_exit_code
from olga_multiphase_simulator.discovery import find_olga
from olga_multiphase_simulator.runner import collect_outputs


@pytest.fixture()
def runner(fake_install_root: Path) -> OlgaRunner:
    return OlgaRunner(installation=find_olga(search_roots=[fake_install_root], env={}))


def test_minimal_command_puts_case_last(runner: OlgaRunner, tmp_path: Path) -> None:
    case = tmp_path / "case.genkey"
    case.write_text("", encoding="utf-8")
    command = runner.build_command(case)
    assert command[0].endswith("Olga-2025.1.0.exe")
    assert command[-1] == str(case.resolve())


def test_options_are_rendered(runner: OlgaRunner, tmp_path: Path) -> None:
    case = tmp_path / "case.genkey"
    case.write_text("", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    command = runner.build_command(
        case,
        out_dir=out_dir,
        nthreads=4,
        disable_outputs=("ppl", "plt"),
        console_log=True,
    )
    assert "-nthreads" in command and command[command.index("-nthreads") + 1] == "4"
    assert "-outDir" in command and command[command.index("-outDir") + 1] == str(out_dir.resolve())
    assert "-noppl" in command and "-noplt" in command
    assert "-consoleLog" in command


def test_rule_check_flag(runner: OlgaRunner, tmp_path: Path) -> None:
    case = tmp_path / "case.genkey"
    case.write_text("", encoding="utf-8")
    assert "-exitRC" in runner.build_command(case, rule_check_only=True)
    assert "-exitID" in runner.build_command(case, init_check_only=True)


def test_unknown_output_kind_rejected(runner: OlgaRunner, tmp_path: Path) -> None:
    case = tmp_path / "case.genkey"
    case.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        runner.build_command(case, disable_outputs=("h5",))


def test_missing_case_raises(runner: OlgaRunner, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        runner.run(tmp_path / "absent.genkey")


@pytest.mark.parametrize(
    ("code", "category", "name"),
    [
        (0, "Normal stop", "OK"),
        (26, "Initialization failure", "LICENSE_FAIL"),
        (34, "Module error", "PVT_FAIL"),
        (67, "Simulation error", "PT_NAN"),
        (4242, "Unknown", "UNMAPPED"),
    ],
)
def test_exit_code_table(code: int, category: str, name: str) -> None:
    resolved_category, resolved_name, description = describe_exit_code(code)
    assert (resolved_category, resolved_name) == (category, name)
    assert description


def test_collect_outputs(tmp_path: Path) -> None:
    for suffix in (".out", ".tpl", ".ppl", ".unrelated"):
        (tmp_path / f"case{suffix}").write_text("", encoding="utf-8")
    outputs = collect_outputs(tmp_path, "case")
    assert set(outputs) == {"out", "tpl", "ppl"}
