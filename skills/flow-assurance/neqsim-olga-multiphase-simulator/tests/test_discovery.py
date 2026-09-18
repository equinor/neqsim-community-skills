from __future__ import annotations

from pathlib import Path

import pytest

from olga_multiphase_simulator import (
    OlgaNotFoundError,
    find_olga,
    find_olga_installations,
    license_environment,
    olgas_point_model_roots,
)


def test_finds_versions_newest_first(fake_install_root: Path) -> None:
    installations = find_olga_installations(search_roots=[fake_install_root], env={})
    assert [i.version for i in installations] == ["2025.1.0", "2024.1.5"]


def test_excludes_olga_s_and_namespace_explorer(fake_install_root: Path) -> None:
    roots = {i.root.name for i in find_olga_installations(search_roots=[fake_install_root], env={})}
    assert roots == {"Olga 2025.1.0", "Olga 2024.1.5"}


def test_engine_and_gui_are_resolved(fake_install_root: Path) -> None:
    installation = find_olga(search_roots=[fake_install_root], env={})
    assert installation.engine.name == "Olga-2025.1.0.exe"
    assert installation.gui is not None and installation.gui.name == "OPGFramework.exe"
    assert installation.version_key == (2025, 1, 0)


def test_version_filter(fake_install_root: Path) -> None:
    installation = find_olga("2024", search_roots=[fake_install_root], env={})
    assert installation.version == "2024.1.5"


def test_olga_home_environment_override(fake_install_root: Path) -> None:
    env = {"OLGA_HOME": str(fake_install_root / "Olga 2024.1.5")}
    installations = find_olga_installations(search_roots=[], env=env)
    assert [i.version for i in installations] == ["2024.1.5"]


def test_olga_engine_environment_override(fake_install_root: Path) -> None:
    engine = fake_install_root / "Olga 2025.1.0" / "OlgaExecutables" / "Olga-2025.1.0.exe"
    installations = find_olga_installations(search_roots=[], env={"OLGA_ENGINE": str(engine)})
    assert len(installations) == 1
    assert installations[0].engine == engine
    assert installations[0].root.name == "Olga 2025.1.0"


def test_missing_installation_raises_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(OlgaNotFoundError) as excinfo:
        find_olga(search_roots=[tmp_path], env={})
    assert "OLGA_HOME" in str(excinfo.value)


def test_describe_is_json_friendly(fake_install_root: Path) -> None:
    described = find_olga(search_roots=[fake_install_root], env={}).describe()
    assert described["version"] == "2025.1.0"
    assert isinstance(described["tools"], dict)
    assert all(isinstance(v, str) for v in described["tools"].values())


def test_license_and_point_model_environment_are_filtered() -> None:
    env = {
        "LM_LICENSE_FILE": "7570@licence.example",
        "PATH": "/usr/bin",
        "OLGAS_SLB_x64": r"C:\olgas\Win64",
        "OLGAS_SLB_x64_2025.1.0": r"C:\olgas\Win64",
    }
    assert license_environment(env) == {"LM_LICENSE_FILE": "7570@licence.example"}
    assert set(olgas_point_model_roots(env)) == {"OLGAS_SLB_x64", "OLGAS_SLB_x64_2025.1.0"}
