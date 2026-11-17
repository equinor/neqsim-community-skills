"""Load the TimeSeriesAnalysis .NET library (equinor/TimeSeriesAnalysis) through pythonnet.

The assemblies are found in this order:

1. ``TIMESERIESANALYSIS_ASSEMBLY_PATH`` (the variable equinor/timeseriesanalysis-py also uses);
2. the ``_assemblies`` folder of an installed ``timeseriesanalysis`` package (equinor/timeseriesanalysis-py);
3. ``~/.neqsim/timeseriesanalysis/<version>``, written by ``<python> -m dynamic_identification setup``.

Nothing is downloaded or built at run time. ``setup`` is an explicit, user-run command.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_VERSION = "1.4.38"
ASSEMBLY = "TimeSeriesAnalysis"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_loaded: Path | None = None


class TsaUnavailable(RuntimeError):
    """The TimeSeriesAnalysis assemblies or the .NET runtime cannot be loaded."""


def default_bundle_dir(version: str = DEFAULT_VERSION) -> Path:
    return Path.home() / ".neqsim" / "timeseriesanalysis" / version


def find_assemblies(version: str = DEFAULT_VERSION) -> Path | None:
    """Directory holding ``TimeSeriesAnalysis.dll``, or None."""
    candidates = []
    if os.environ.get("TIMESERIESANALYSIS_ASSEMBLY_PATH"):
        candidates.append(Path(os.environ["TIMESERIESANALYSIS_ASSEMBLY_PATH"]))
    try:
        import timeseriesanalysis  # type: ignore[import-not-found]

        candidates.append(
            Path(timeseriesanalysis.__file__).resolve().parent / "_assemblies"
        )
    except Exception:  # noqa: BLE001 - the py package is optional
        pass
    candidates.append(default_bundle_dir(version))
    for path in candidates:
        if (path / f"{ASSEMBLY}.dll").exists():
            return path
    return None


def load(version: str = DEFAULT_VERSION) -> Path:
    """Load CoreCLR and the TimeSeriesAnalysis assembly once; return the assembly folder."""
    global _loaded
    if _loaded is not None:
        return _loaded
    folder = find_assemblies(version)
    if folder is None:
        raise TsaUnavailable(
            "TimeSeriesAnalysis.dll not found. Run '<python> -m dynamic_identification setup' once (needs the .NET SDK), "
            "or set TIMESERIESANALYSIS_ASSEMBLY_PATH to a folder with the published assemblies."
        )
    try:
        from pythonnet import load as load_runtime

        load_runtime("coreclr")
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise TsaUnavailable(
                f".NET runtime (CoreCLR) could not be loaded: {exc}. Install the .NET 8 runtime "
                f"or newer, and pythonnet (declared in this skill's pyproject.toml)."
            ) from exc
    import clr  # type: ignore[import-not-found]

    if str(folder) not in sys.path:
        sys.path.append(str(folder))
    clr.AddReference(ASSEMBLY)
    _loaded = folder
    return folder


_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Library</OutputType>
    <CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>
  </PropertyGroup>
  <ItemGroup><PackageReference Include="TimeSeriesAnalysis" Version="{version}" /></ItemGroup>
</Project>
"""


def setup_assemblies(version: str = DEFAULT_VERSION, dest: Path | None = None) -> Path:
    """Publish TimeSeriesAnalysis and its dependencies from NuGet into ``dest`` with the .NET SDK.

    Run once, on purpose. It needs ``dotnet`` on PATH and network access to nuget.org.
    """
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise TsaUnavailable(
            "the .NET SDK (dotnet) is not on PATH; install it or point "
            "TIMESERIESANALYSIS_ASSEMBLY_PATH at published assemblies"
        )
    dest = Path(dest) if dest else default_bundle_dir(version)
    build = dest.parent / f"_build_{version}"
    build.mkdir(parents=True, exist_ok=True)
    (build / "tsa_bundle.csproj").write_text(
        _PROJECT.format(version=version), encoding="utf-8"
    )
    result = subprocess.run(
        [
            dotnet,
            "publish",
            str(build / "tsa_bundle.csproj"),
            "-c",
            "Release",
            "-o",
            str(dest),
            "--nologo",
            "-v",
            "q",
        ],
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    shutil.rmtree(build, ignore_errors=True)
    if result.returncode != 0 or not (dest / f"{ASSEMBLY}.dll").exists():
        raise TsaUnavailable(
            f"dotnet publish failed: {result.stdout[-800:]} {result.stderr[-800:]}"
        )
    return dest
