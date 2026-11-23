# Process Safety Study

Workflow and gates for a full process safety study of a tie-in, modification or new facility: the order of work, the skill or agent per step, the evidence and acceptance gate per step and the traps found in earlier studies. The helpers turn the rules into checks: an unread document becomes a data gap, a number without a hand calculation is not a basis, a transient result is classified conservative or not, a drawing item without a tag is an orphan.

## Install

```bash
python -m pip install -e skills/safety/neqsim-process-safety-study
```

## Run Tests

```bash
python -m pytest skills/safety/neqsim-process-safety-study/tests
```

No NeqSim is needed. Pair it with the step skills named in `SKILL.md` and the agent `process-safety-study-agent`.

## Public Scope

Generic and vendor-neutral. Company document systems and criteria belong in an enterprise overlay.
