# Python quality checks

- Use the repository's uv environment and Ruff configuration for Python changes.
- Run `uv run pre-commit run --files <changed-files>` and the relevant tests
  before handing over changes. The hooks run Ruff linting and Black formatting.
- Fix findings introduced by your changes. Do not weaken rules, add blanket
  suppressions, or bypass hooks to make checks pass.
- Report unrelated existing failures explicitly rather than claiming success.
