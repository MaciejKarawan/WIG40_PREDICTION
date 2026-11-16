# File classification

- `src/`: importable computational/helper code.
- `scripts/`: explicit research/plot entry points, run with `python -m scripts.NAME` from the repository root.
- `data/`: supplied inputs and reference data; generated inputs are ignored.
- `results/`: retained reference tables/figures and ignored generated run results.
- `reports/`: report documents; `docs/`: environment, workflow and migration records.
- `archive/`: distinct historical or incomplete variants, when present; these are not active entry points.
- `tests/`: small migration/regression checks, not statistical experiments.

The WIG40 pipeline retains `output/` as its generated-artifact contract. Long experiments and historical outputs were not regenerated during organization. Archived files keep their original content, including old import/path assumptions, and are not promised to run under the current layout.
