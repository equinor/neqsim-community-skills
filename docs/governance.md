# Governance and Review

NeqSim Community Skills is intended to stay public, reproducible, and useful across organizations.

## Maintainer Responsibilities

Maintainers review contributions for:

- public suitability
- technical clarity
- test coverage
- documentation quality
- compatibility with the NeqSim skill format
- clear separation between educational screening and validated calculations

## Contribution Scope

Accepted community skills should describe open workflows, public examples, and reusable agent guidance. A skill can be experimental if it is clearly labeled and does not make unsupported claims.

The repository does not accept confidential, proprietary, or company-specific content. Private workflows belong in local or private skill repositories, not in this public repository.

## Review Process

Pull requests should be small enough to review. Prefer one skill per pull request unless the change is a shared documentation or infrastructure update.

Reviewers should check:

- `SKILL.md` frontmatter and required sections
- examples and tests
- public-data compliance
- catalog path correctness
- references and limitation statements

## Publication to the NeqSim Catalog

After a skill is accepted here, it can be proposed for the main NeqSim community catalog by adding an entry to `community-skills.yaml` in the main `equinor/neqsim` repository. Use the same `repo` and `path` fields shown in this repository's [community-skills.yaml](../community-skills.yaml).

## Deprecation

A skill may be deprecated when it is replaced by a validated NeqSim method, duplicated by a better community skill, or no longer maintained. Deprecated skills should keep a clear note in `README.md` and `SKILL.md` that points to the replacement.