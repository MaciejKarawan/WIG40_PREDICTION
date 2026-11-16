# Migration validation — 2026-11-16

Validated on Python 3.12 in an isolated environment with editable installation.

- matplotlib 3.11.2
- nbformat 5.11.1
- numpy 1.26.4
- pandas 3.0.6
- pdfplumber 0.11.10
- pyreadr 0.5.9
- scipy 1.17.1
- seaborn 0.13.2
- statsmodels 0.15.0

`python -m unittest discover -s tests -v` passes. All Python files compile. Original CSV, image, PDF and parquet contents remain present; identical copies were consolidated only where verified. Distinct archived implementations retain their source content. Computational function bodies in the Monte Carlo and PRNG generators were compared against their originals.

Full experiments, online data downloads and optional Chronos model execution were not run. Known missing historical helpers are documented in README. NumPy 1.26 is required by the legacy variance-reduction scalar conversion; its numerical implementation was retained.
