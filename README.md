# mWIG40 Prediction

Install Python 3.11+ and `python -m pip install -e .`. Research on mWIG40 index composition, historical replication and prediction.

- `src/mwig_replication/`: active ranking, filtering, replication and prediction package.
- `scripts/`: ingestion, validation, EDA and backtest entry points (`python -m scripts.<name>` from the root).
- `data/`: input/reference snapshots; `notebooks/`: analysis notebooks.
- `reports/`: research reports; `docs/`: project progress and data dependency map.
- `archive/alternative_replication/`: distinct former Bin variants, preserved verbatim, not part of the active package.
- `results/`: output policy. The established pipeline still writes to ignored `output/` to preserve existing calculations and file contracts.

See [data preparation](docs/data-pipeline.md), [report reading order](reports/README.md) and [migration map](docs/file-migration.json).
The former bin/ commands now live in scripts/. The package is installed from src/; repository-relative data paths are preserved. Set MWIG_BENCH_DIR for the benchmark input instead of depending on another local project.

Exploratory research is not a validated trading strategy. Later reality checks revised earlier conclusions. No numerical experiments or data downloads are triggered by installation or package import. Dependency versions are declared but not frozen to the unknown historical environment.

## Migration checks

After installation: `python -m unittest discover -s tests -v`. These small checks do not run the full research experiments.
