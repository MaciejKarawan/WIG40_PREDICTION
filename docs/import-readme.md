# mWIG40 Index Inclusion Prediction

Research code for reconstructing GPW index rankings and studying changes in the mWIG40 composition. The repository name retains the original local project name; the target index is mWIG40.

## Contents

- `mwig_replication/`: ranking, eligibility filters, buffer rules, replication and prediction.
- `bin/`: data ingestion, validation, exploratory analyses and backtests.
- `notebooks/`: notebooks with execution outputs removed during import.
- `reports/`: methodology, research history and limitations.
- `data/`: selected reference/input files. Large OHLCV caches, downloaded PDFs, generated outputs and backups remain local.

## Research status

Exploratory results are not evidence of a validated trading strategy. The later reality check identified look-ahead contamination in an earlier long-lead backtest. Read `reports/sygnal_reality_check.md` and `reports/research_log.md` alongside earlier reports. External data and some paths referring to sibling projects must be configured before reproducing experiments.

## Environment

Python with NumPy, pandas, SciPy, matplotlib, seaborn, statsmodels, Plotly, requests, pdfplumber, pyarrow and nbformat. Versions are not frozen in this import. Inspect individual script arguments before running; data downloaders access external services.

This import preserves research code and documents. Python syntax was checked; experiments and numerical results were not rerun.
