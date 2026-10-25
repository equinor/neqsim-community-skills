# neqsim-concept-longlist-shortlist-screening

Educational concept long-list to short-list screening for field development.

- Generate a long list from a decision-element option matrix with compatibility rules and givens.
- Flag capacity variants posing as concepts and decision elements that are never varied.
- Apply must-pass screens where only an evidenced fail eliminates a concept.
- Rank survivors with a weighted decision matrix, Pareto front, rank acceptability under weight
  uncertainty and crossover weights.
- Select a robust, diverse short list with a reference concept and a full elimination log.

Results are labelled `SCREENING` and need human review; the skill does not replace a
concept-selection study or company decision-gate governance.

```bash
pip install -e .[test]
pytest
python examples/basic_screening.py
```

See [SKILL.md](SKILL.md) for the method, inputs and outputs.

Figures (optional, needs matplotlib: `pip install .[figures]`): `render_screening_figures(result, out_dir)` writes the funnel, decision-matrix heatmap, Pareto trade-off, rank-acceptability, weight-crossover and per-concept schematic PNGs and returns `results.json` figure entries. See SKILL.md, Concept Figures.
