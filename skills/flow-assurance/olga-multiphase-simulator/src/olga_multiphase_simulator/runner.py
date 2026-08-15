"""Run OLGA cases in batch and interpret the engine exit status.

The OLGA batch solver is invoked as::

    Olga-<version>.exe [options] casefile.[key|genkey]

and communicates success or failure through its process exit code. The
``EXIT_CODES`` table below is transcribed from ``exit_code_lookup.exe list``
shipped with OLGA 2025.1.0, so exit-status interpretation works offline.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .discovery import OlgaInstallation, find_olga

__all__ = [
    "EXIT_CODES",
    "OlgaRunResult",
    "OlgaRunner",
    "describe_exit_code",
]

#: ``{exit_code: (category, symbolic_name, description)}`` — from ``exit_code_lookup list``.
EXIT_CODES: Dict[int, Tuple[str, str, str]] = {
    0: ("Normal stop", "OK", "OK"),
    1: ("Normal stop", "STOP_TOGGLED", "OPC Stop command"),
    2: ("Normal stop", "CTRL_C", "Ctrl-C pressed event"),
    3: ("Normal stop", "SERVICE_STOPPED", "service stopped from service manager"),
    4: ("Normal stop", "CONSOLE_CLOSE", "console close event"),
    17: ("Initialization failure", "CMDLINE_FAILED", "illegal command line"),
    18: ("Initialization failure", "VERIFY_FAILED", "verification failed"),
    19: ("Initialization failure", "STILL_ACTIVE", "the thread tells the parent process it is still alive"),
    20: ("Initialization failure", "INIT_FAILED", "initialization failed"),
    21: ("Initialization failure", "RESTART_FAILED", "restart failed"),
    22: ("Initialization failure", "SSPP_FAILED", "steady state pre-processor failed"),
    23: ("Initialization failure", "FLUID_FAILED", "fluid initialization failed"),
    24: ("Initialization failure", "OUTPUT_FAILED", "output initialization failed"),
    25: ("Initialization failure", "TOPO_FAILED", "internal error; initializing topology"),
    26: ("Initialization failure", "LICENSE_FAIL", "license checkout failed"),
    27: ("Initialization failure", "USER_PRVLGS_INSUFF", "insufficient user privileges"),
    33: ("Module error", "MUFFIN_FAIL", "internal error; initializing muffin"),
    34: ("Module error", "PVT_FAIL", "component fluid initialization failed"),
    35: ("Module error", "WAX_FAIL", "wax module"),
    36: ("Module error", "PLUGIN_FAIL", "plugin module"),
    37: ("Module error", "ROCX_FAIL", "nearwell module"),
    38: ("Module error", "SLUG_FAIL", "slug tracking module"),
    39: ("Module error", "TRACER_FAIL", "tracer tracking module"),
    40: ("Module error", "PROCEQ_FAIL", "process equipment"),
    49: ("Communication failure", "COMM_FAIL", "communication failure"),
    50: ("Communication failure", "SERVICE_FAIL", "service failure"),
    51: ("Communication failure", "PROCESS_FAIL", "submodel or child process stopped"),
    52: ("Communication failure", "SUBMODEL_ABORT", "submodel or child process aborted"),
    65: ("Simulation error", "PT_BELOW", "pressure below"),
    66: ("Simulation error", "PT_ABOVE", "pressure above"),
    67: ("Simulation error", "PT_NAN", "pressure NaN"),
    68: ("Simulation error", "TM_BELOW", "temperature below"),
    69: ("Simulation error", "TM_ABOVE", "temperature above"),
    70: ("Simulation error", "TM_NAN", "temperature NaN"),
    71: ("Simulation error", "H_BELOW", "enthalpy below"),
    72: ("Simulation error", "H_ABOVE", "enthalpy above"),
    73: ("Simulation error", "H_NAN", "enthalpy NaN"),
    97: ("Internal error", "STD_EXCEPTION", "exception: std"),
    98: ("Internal error", "STD_INVALID_ARGUMENT", "exception: invalid argument"),
    99: ("Internal error", "INTERNAL_ERROR", "internal error"),
    100: ("Internal error", "OBSOLETE", "internal error: obsolete function"),
    101: ("Internal error", "UNKNOWN", "unknown"),
}

_OUTPUT_SUFFIXES = (".out", ".tpl", ".ppl", ".plt", ".rsw", ".h5", ".log")

_DISABLE_FLAGS = {
    "out": "-noout",
    "plt": "-noplt",
    "ppl": "-noppl",
    "tpl": "-notpl",
    "opc": "-noopc",
}


def describe_exit_code(code: int) -> Tuple[str, str, str]:
    """Return ``(category, symbolic_name, description)`` for an OLGA exit code."""
    return EXIT_CODES.get(code, ("Unknown", "UNMAPPED", f"exit code {code} is not in the OLGA table"))


@dataclass(frozen=True)
class OlgaRunResult:
    """Outcome of one OLGA engine invocation."""

    case: Path
    out_dir: Path
    command: Tuple[str, ...]
    returncode: int
    category: str
    code_name: str
    description: str
    duration_s: float
    stdout: str
    outputs: Mapping[str, Path] = field(default_factory=dict)
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        """``True`` only when OLGA reported a normal stop (exit code 0)."""
        return self.returncode == 0 and not self.timed_out

    def summary(self) -> Dict[str, object]:
        """Return a JSON-friendly summary suitable for a task ``results.json``."""
        return {
            "case": str(self.case),
            "out_dir": str(self.out_dir),
            "command": list(self.command),
            "returncode": self.returncode,
            "exit_category": self.category,
            "exit_code_name": self.code_name,
            "exit_description": self.description,
            "succeeded": self.succeeded,
            "timed_out": self.timed_out,
            "duration_s": round(self.duration_s, 3),
            "outputs": {k: str(v) for k, v in sorted(self.outputs.items())},
        }


class OlgaRunner:
    """Thin, auditable wrapper around the OLGA batch solver.

    Example:
        >>> runner = OlgaRunner()                      # doctest: +SKIP
        >>> check = runner.rule_check("case.genkey")   # doctest: +SKIP
        >>> if check.succeeded:                        # doctest: +SKIP
        ...     result = runner.run("case.genkey", nthreads=4)
    """

    def __init__(
        self,
        installation: Optional[OlgaInstallation] = None,
        version: Optional[str] = None,
        default_nthreads: Optional[int] = None,
    ) -> None:
        self.installation = installation or find_olga(version=version)
        self.default_nthreads = default_nthreads

    # -- command construction -------------------------------------------------

    def build_command(
        self,
        case: str | os.PathLike[str],
        out_dir: Optional[str | os.PathLike[str]] = None,
        nthreads: Optional[int] = None,
        rule_check_only: bool = False,
        init_check_only: bool = False,
        disable_outputs: Sequence[str] = (),
        log: Optional[str | os.PathLike[str]] = None,
        console_log: bool = False,
        extra_args: Sequence[str] = (),
    ) -> List[str]:
        """Build the OLGA command line without running anything.

        Args:
            case: Path to the ``.genkey`` or ``.key`` input file.
            out_dir: Directory for OLGA output files (``-outDir``). Defaults to
                the case directory.
            nthreads: Number of OpenMP threads (``-nthreads``).
            rule_check_only: Only run input rule checks (``-exitRC``), no simulation.
            init_check_only: Rule checks plus object initialization (``-exitID``).
            disable_outputs: Any of ``out``, ``plt``, ``ppl``, ``tpl``, ``opc``.
            log: Log file path (``-log``).
            console_log: Also write console output to the log file (``-consoleLog``).
            extra_args: Additional raw engine arguments appended before the case.

        Returns:
            The argument list, with the case file last as OLGA requires.
        """
        case_path = Path(case).resolve()
        command: List[str] = [str(self.installation.engine)]

        threads = self.default_nthreads if nthreads is None else nthreads
        if threads is not None:
            command += ["-nthreads", str(int(threads))]
        if out_dir is not None:
            command += ["-outDir", str(Path(out_dir).resolve())]
        for key in disable_outputs:
            flag = _DISABLE_FLAGS.get(key.lower())
            if flag is None:
                raise ValueError(
                    f"Unknown output kind {key!r}; expected one of {sorted(_DISABLE_FLAGS)}"
                )
            command.append(flag)
        if log is not None:
            command += ["-log", str(Path(log))]
        if console_log:
            command.append("-consoleLog")
        if rule_check_only:
            command.append("-exitRC")
        if init_check_only:
            command.append("-exitID")
        command += [str(a) for a in extra_args]
        command.append(str(case_path))
        return command

    # -- execution ------------------------------------------------------------

    def run(
        self,
        case: str | os.PathLike[str],
        out_dir: Optional[str | os.PathLike[str]] = None,
        timeout: Optional[float] = None,
        env: Optional[Mapping[str, str]] = None,
        **command_kwargs: object,
    ) -> OlgaRunResult:
        """Run a case to completion and return a structured result.

        The working directory is set to the case directory because OLGA resolves
        relative ``FILES PVTFILE=./x.tab`` references against the current
        directory, not against the case file.

        Args:
            case: Path to the ``.genkey`` or ``.key`` input file.
            out_dir: Directory for OLGA output files; defaults to the case directory.
            timeout: Wall-clock limit in seconds; ``None`` waits indefinitely.
            env: Environment for the child process; defaults to the current one.
            **command_kwargs: Forwarded to :meth:`build_command`.

        Raises:
            FileNotFoundError: If the case file does not exist.
        """
        case_path = Path(case).resolve()
        if not case_path.is_file():
            raise FileNotFoundError(f"OLGA case file not found: {case_path}")

        work_dir = case_path.parent
        output_dir = Path(out_dir).resolve() if out_dir is not None else work_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        command = self.build_command(case_path, out_dir=out_dir, **command_kwargs)  # type: ignore[arg-type]

        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(
                command,
                cwd=str(work_dir),
                env=None if env is None else dict(env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            returncode = completed.returncode
            stdout = (completed.stdout or "") + (completed.stderr or "")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = -1
            stdout = _as_text(exc.stdout) + _as_text(exc.stderr)
        duration = time.monotonic() - started

        category, code_name, description = describe_exit_code(returncode)
        if timed_out:
            category, code_name = "Timeout", "TIMEOUT"
            description = f"engine killed after {timeout} s"

        return OlgaRunResult(
            case=case_path,
            out_dir=output_dir,
            command=tuple(command),
            returncode=returncode,
            category=category,
            code_name=code_name,
            description=description,
            duration_s=duration,
            stdout=stdout,
            outputs=collect_outputs(output_dir, case_path.stem),
            timed_out=timed_out,
        )

    def rule_check(
        self,
        case: str | os.PathLike[str],
        timeout: Optional[float] = 600.0,
        **kwargs: object,
    ) -> OlgaRunResult:
        """Validate case input without simulating (``-exitRC``).

        Always do this before a long run: it catches keyword, unit and topology
        errors in seconds instead of after a licence checkout and a full solve.
        """
        return self.run(case, timeout=timeout, rule_check_only=True, **kwargs)  # type: ignore[arg-type]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def collect_outputs(out_dir: str | os.PathLike[str], case_stem: str) -> Dict[str, Path]:
    """Return the OLGA output files produced for ``case_stem`` in ``out_dir``."""
    directory = Path(out_dir)
    outputs: Dict[str, Path] = {}
    for suffix in _OUTPUT_SUFFIXES:
        candidate = directory / f"{case_stem}{suffix}"
        if candidate.is_file():
            outputs[suffix.lstrip(".")] = candidate
    return outputs
