# Contributing to NeqSim Community Skills

Thank you for helping build a public catalog of reusable NeqSim skills. Contributions should be useful to students, researchers, engineers, and open-source users without exposing private or proprietary information.

## Where Does This Belong?

Before adding a skill here, confirm this is the right repository. See the
[Where Does This Go? placement guide](docs/where-does-this-go.md): community
skills hold **educational, screening-level** methods that reference — but do not
replace — the validated Java classes in core NeqSim. Validated calculations
belong in core neqsim; company-policy or confidential content belongs in the
enterprise repos.

For company-private skills, set up paired enterprise skills and agents repositories instead of adding the content here. The main NeqSim [Enterprise Agent and Skill Repositories](https://github.com/equinor/neqsim/blob/master/docs/integration/enterprise_agent_skill_repos.md) guide explains the `enterprise-skills.yaml` / `enterprise-agents.yaml` catalogs and Engineering Harness discovery/install configuration.

## Add a New Skill

1. Copy [templates/skill-template](templates/skill-template) into the relevant domain folder under [skills](skills).
2. Rename the folder with a short kebab-case topic name, for example `skills/pvt/phase-envelope-check`.
3. Give the skill a catalog name that starts with `neqsim-`, for example `neqsim-phase-envelope-check`.
4. Fill in `SKILL.md` using the required sections in [docs/skill-standard.md](docs/skill-standard.md).
5. Add Python code under `src` if the skill includes executable logic.
6. Add examples that run with public inputs only.
7. Add pytest tests for all executable behavior.
8. Add or update the root `community-skills.yaml` catalog entry.
9. Update any local catalog preview, README tables, or documentation that should mention the skill.

## Required Files

Each skill folder must contain:

```text
skill-name/
├── SKILL.md
├── README.md
├── pyproject.toml
├── src/
├── examples/
└── tests/
```

`SKILL.md` is required even for a documentation-only skill. Python code is optional, but tests and examples are still expected when the skill describes runnable code patterns.

## Testing Requirements

Run the full repository tests before opening a pull request:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

For a single skill, run its example and tests:

```bash
python -m pip install -e skills/<domain>/<skill-name>
python skills/<domain>/<skill-name>/examples/<example>.py
python -m pytest skills/<domain>/<skill-name>/tests
```

Tests should verify normal behavior, boundary conditions, invalid inputs, and documented warnings or flags.

## Documentation Requirements

Every skill must document:

- when to use it
- inputs and units
- outputs and interpretation
- engineering method and assumptions
- Python usage pattern
- validation checklist
- common mistakes
- limitations
- references

Documentation must distinguish educational screening logic from validated NeqSim calculations.

## Public Data and Confidentiality

Do not contribute:

- proprietary or unpublished engineering methods
- confidential plant data, production data, composition data, or project data
- internal URLs, host names, authentication patterns, tag names, or document identifiers
- company-specific standards, procedures, or design bases
- text copied from licensed standards or restricted documents

Use small synthetic examples and cite public references only.

## Quiet by default (no pop-ups, no installs, no surprise sign-ins)

Agents and skills run from hooks, MCP servers and chat tool calls with no visible console. Anything that opens a window or asks the user to act breaks the flow, so every new or changed skill and agent must follow these rules:

- **Hidden child processes.** Every `subprocess.run/Popen/check_output/call` in skill code passes `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`. Never use `os.system`, `os.startfile` or `shell=True` to start tools. The repository test `test_quiet_processes.py` fails the build otherwise; annotate a deliberate user-requested exception with `# quiet-ok: <reason>`.
- **No installs at run time.** Declare dependencies in the skill's `pyproject.toml`; the plugin installs them once, in the background. Skill code and agent instructions must not run `pip install`, `npm install` or download tools mid-task. If a package is missing, report the blocker and the remedy.
- **Silent authentication first.** Get tokens through `enterprise-sso-auth` (cached tokens, `az account get-access-token`, session warm-up via `session_warmup.json`). Register new APIs in its service registry so they are warmed at session start. Never call `az login`, device-code flows, browser sign-in or credential prompts from skill code or agent steps unless every silent route has failed, and then ask once with the exact remedy.
- **Background by default.** Long installs, downloads and warm-ups run detached with output in a log file, never in the foreground chat. Agent instructions must tell the model to continue with other work rather than wait on them.
- **GUI automation is the exception.** Computer-use skills may start a visible application only when the user's task needs it; say so in the skill's Limitations section.

## Review Checklist

Before requesting review, confirm that:

- [ ] The skill name starts with `neqsim-`.
- [ ] The skill appears in `community-skills.yaml` with the canonical `neqsim-*` ID.
- [ ] `SKILL.md` has valid YAML frontmatter and all required sections.
- [ ] Examples run with public data.
- [ ] Tests pass with Python 3.10 or newer.
- [ ] Optional NeqSim integration has a fallback when NeqSim is not installed.
- [ ] The contribution contains no confidential or company-specific information.
- [ ] Limitations are explicit enough to prevent production misuse.
- [ ] References are public and traceable.

Maintainers may ask for clearer limitations, stronger tests, or removal of content that is not appropriate for a public repository.