# Python quality checks

- Use the repository's uv environment and Ruff configuration for Python changes.
- Run `uv run pre-commit run --files <changed-files>` and the relevant tests
  before handing over changes. The hooks run Ruff linting and Black formatting.
- Fix findings introduced by your changes. Do not weaken rules, add blanket
  suppressions, or bypass hooks to make checks pass.
- Report unrelated existing failures explicitly rather than claiming success.

## Portable paths and delegation

Never bake an author's absolute checkout, interpreter, EOS or task path into
code or prompts. Use explicit inputs, documented environment variables,
workspace-relative discovery or installed resources; validate configured paths
and report missing inputs instead of silently substituting another model.
Pass resolved absolute paths, the selected interpreter and this portability
requirement to every delegated agent. A plugin installation needs no checkout.
