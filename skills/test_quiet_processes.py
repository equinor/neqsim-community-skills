"""Quiet-by-default rules for skill code: no console pop-ups, no runtime installs, no surprise sign-ins.

Skill code runs from hooks, MCP servers and agent tool calls where no console is visible, so every
console child process must start hidden. Installs belong in the skill's pyproject (the plugin
installs them in the background) and sign-in belongs to ``enterprise-sso-auth`` (silent token warm-up).
Add ``# quiet-ok: <reason>`` on the call line when a call genuinely must be visible or interactive.
"""

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills"
SPAWNERS = {"run", "Popen", "check_output", "check_call", "call"}
SSO_SKILL = "enterprise-sso-auth"
SKIPPED_DIRS = {"tests", "test", "examples", "__pycache__", ".venv", "node_modules"}


def _skill_sources():
    for path in sorted(SKILL_ROOT.rglob("*.py")):
        relative = path.relative_to(SKILL_ROOT).parts
        if SKIPPED_DIRS.intersection(relative) or path.name.startswith("test_"):
            continue
        yield path


def _strings(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _dotted(func):
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _findings():
    for path in _skill_sources():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        in_sso = SSO_SKILL in path.parts
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            name = _dotted(node.func)
            span = "\n".join(lines[node.lineno - 1:node.end_lineno])
            if "quiet-ok" in span:
                continue
            where = "{}:{}".format(path.relative_to(REPOSITORY_ROOT), node.lineno)
            if name.startswith("subprocess.") and name.split(".")[-1] in SPAWNERS:
                if not any(k.arg in ("creationflags", "startupinfo") for k in node.keywords):
                    yield where, "{} without creationflags=CREATE_NO_WINDOW".format(name)
                words = [s.strip().lower() for s in _strings(node)]
                if "pip" in words and "install" in words:
                    yield where, "runtime pip install; declare the dependency in pyproject instead"
                if not in_sso and "login" in words:
                    yield where, "interactive login; use enterprise-sso-auth tokens instead"
            elif name in ("os.system", "os.startfile") or (name == "webbrowser.open" and not in_sso):
                yield where, "{} opens a window or shell".format(name)


def test_skill_code_never_pops_up_windows_installs_or_signs_in():
    problems = ["{}: {}".format(where, why) for where, why in _findings()]
    assert not problems, (
        "Skill code must stay quiet (hidden child processes, no runtime installs, silent auth). "
        "Fix or annotate with '# quiet-ok: reason':\n" + "\n".join(problems)
    )
