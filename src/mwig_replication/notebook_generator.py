"""
Generator notebooka diagnostycznego dla replikacji rewizji.

Notebook jest parametryzowany — wczytuje konkretny Parquet z replikacji
i pokazuje porównanie z faktycznym składem oraz listą rezerwową.
"""

from __future__ import annotations
import json
from pathlib import Path


def _make_cell(cell_type: str, source: list[str]) -> dict:
    """Tworzy strukturę komórki w formacie .ipynb."""
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def generate_notebook(
    revision_date: str,
    parquet_path: Path,
    notebook_path: Path,
) -> None:
    """Generuje .ipynb dla danej rewizji.

    Args:
        revision_date: data rewizji (YYYY-MM-DD)
        parquet_path: ścieżka do replication_*.parquet
        notebook_path: gdzie zapisać .ipynb
    """
    # Ścieżka relatywna względem notebooka — łatwiej modyfikować
    parquet_rel = parquet_path.name

    cells = []

    # 1. Tytuł i setup
    cells.append(_make_cell("markdown", [
        f"# Replikacja rankingu mWIG40 — rewizja {revision_date}\n",
        "\n",
        "Notebook diagnostyczny porównujący predykcję rankingu z faktycznym składem indeksu.\n",
        "\n",
        "**Sukces / porażka** — patrz na metryki w sekcji 2.\n",
    ]))

    cells.append(_make_cell("code", [
        "import pandas as pd\n",
        "from pathlib import Path\n",
        "\n",
        "# Wczytaj wyniki replikacji\n",
        f"df = pd.read_parquet('{parquet_rel}')\n",
        "\n",
        "# Wczytaj faktyczne składy + listę rezerwową — adres zależny od layoutu projektu\n",
        "from mwig_replication import config, data_loader\n",
        f"rd = data_loader.load_revision('{revision_date}')\n",
        "\n",
        "actual_mwig40 = rd.actual_mwig40\n",
        "actual_reserve = rd.actual_mwig40_reserve\n",
        "\n",
        f"print(f'Replikacja: {{len(df)}} spółek')\n",
        f"print(f'Faktyczny mWIG40: {{len(actual_mwig40)}} spółek')\n",
        f"print(f'Lista rezerwowa: {{len(actual_reserve)}} spółek')\n",
    ]))

    # 2. Metryki
    cells.append(_make_cell("markdown", [
        "## 2. Metryki sukcesu / porażki\n",
    ]))

    cells.append(_make_cell("code", [
        "from mwig_replication import validation\n",
        "\n",
        "metrics = validation.validate_mwig40(df, actual_mwig40, actual_reserve)\n",
        "rmse = validation.positional_rmse(metrics)\n",
        "\n",
        "print('=' * 50)\n",
        f"print(f'REPLIKACJA {revision_date}')\n",
        "print('=' * 50)\n",
        "print(f'Recall:    {metrics.recall:.2%}  ({metrics.n_correct}/{metrics.n_actual})')\n",
        "print(f'Precision: {metrics.precision:.2%}  ({metrics.n_correct}/{metrics.n_predicted})')\n",
        "print(f'F1:        {metrics.f1:.2%}')\n",
        "if rmse is not None:\n",
        "    print(f'RMSE pozycyjne: {rmse:.2f} miejsc')\n",
        "print()\n",
        "print(f'False positives (przewidzieliśmy, nie weszli): {len(metrics.false_positives)}')\n",
        "print(f'False negatives (weszli, nie przewidzieliśmy):  {len(metrics.false_negatives)}')\n",
        "\n",
        "# Werdykt\n",
        "if metrics.recall >= 0.975:\n",
        "    print('\\n✓ SUKCES (cel ambitny: ≥97.5% recall)')\n",
        "elif metrics.recall >= 0.875:\n",
        "    print('\\n~ MINIMUM VIABLE (recall ≥87.5%)')\n",
        "else:\n",
        "    print('\\n✗ PORAŻKA (recall <87.5%)')\n",
    ]))

    # 3. Tabela porównania
    cells.append(_make_cell("markdown", [
        "## 3. Tabela porównania mWIG40 — predykcja vs faktyczność\n",
        "\n",
        "Wszystkie 40 faktycznych członków indeksu z naszą pozycją rankingową.\n",
        "Spółki z `predicted_mwig40 = False` to false negatives (nie przewidzieliśmy ich).\n",
    ]))

    cells.append(_make_cell("code", [
        "with pd.option_context('display.max_rows', 100):\n",
        "    display(metrics.actual_member_positions)\n",
    ]))

    # 4. False positives
    cells.append(_make_cell("markdown", [
        "## 4. False positives — przewidzieliśmy, nie weszli\n",
    ]))

    cells.append(_make_cell("code", [
        "if metrics.false_positives.empty:\n",
        "    print('Brak false positives — perfekcyjna precyzja')\n",
        "else:\n",
        "    display(metrics.false_positives)\n",
    ]))

    # 5. False negatives
    cells.append(_make_cell("markdown", [
        "## 5. False negatives — weszli, nie przewidzieliśmy\n",
        "\n",
        "Najważniejsza tabela do diagnostyki. Kolumny `passed_basic`, `passed_mwo`,\n",
        "`passed_quartile` pokazują który filtr odrzucił spółkę. Jeśli wszystkie\n",
        "są True ale i tak nie przewidzieliśmy — to znaczy że nasz ranking dał\n",
        "spółce zbyt niską pozycję.\n",
    ]))

    cells.append(_make_cell("code", [
        "if metrics.false_negatives.empty:\n",
        "    print('Brak false negatives — perfekcyjny recall')\n",
        "else:\n",
        "    display(metrics.false_negatives)\n",
    ]))

    # 6. Lista rezerwowa
    cells.append(_make_cell("markdown", [
        "## 6. Lista rezerwowa\n",
        "\n",
        "Lista rezerwowa to 5 spółek z pozycji 41-45 wg rzeczywistego rankingu GPW Benchmark.\n",
        "Sprawdzamy gdzie my je umieściliśmy.\n",
    ]))

    cells.append(_make_cell("code", [
        "print(f'Liczba spółek z listy rezerwowej w naszej predykcji mWIG40: '\n",
        "      f'{len(metrics.reserves_we_predicted)}')\n",
        "print()\n",
        "if not metrics.reserves_we_predicted.empty:\n",
        "    print('Z listy rezerwowej, my przewidzieliśmy w mWIG40:')\n",
        "    display(metrics.reserves_we_predicted)\n",
        "    print()\n",
        "if not metrics.reserves_we_did_not.empty:\n",
        "    print('Z listy rezerwowej, my NIE przewidzieliśmy w mWIG40:')\n",
        "    display(metrics.reserves_we_did_not)\n",
    ]))

    # 7. Dodatkowe diagnostyki
    cells.append(_make_cell("markdown", [
        "## 7. Dodatkowe diagnostyki\n",
        "\n",
        "Statystyki uniwersum spółek po filtrach.\n",
    ]))

    cells.append(_make_cell("code", [
        "print('Łącznie spółek w WIG:', len(df))\n",
        "print()\n",
        "print('Po poszczególnych filtrach:')\n",
        "print(f'  passed_basic:    {df[\"passed_basic\"].sum()}')\n",
        "print(f'  passed_mwo:      {df[\"passed_mwo\"].sum()}')\n",
        "print(f'  passed_quartile: {df[\"passed_quartile\"].sum()}')\n",
        "print(f'  W rankingu (po wszystkich): {df[\"ranking_position\"].notna().sum()}')\n",
        "print()\n",
        "if (~df['has_ohlcv']).any():\n",
        "    print('Spółki bez danych OHLCV:')\n",
        "    display(df[~df['has_ohlcv']][['isin', 'ticker_gpw', 'stooq_ticker']])\n",
        "    print()\n",
        "if (~df['has_ticker_map']).any():\n",
        "    print('Spółki bez mapowania ticker:')\n",
        "    display(df[~df['has_ticker_map']][['isin', 'ticker_gpw']])\n",
        "    print()\n",
        "print('Powody odrzucenia w filtrze bazowym:')\n",
        "display(df[df['basic_failure_reason'] != ''].groupby('basic_failure_reason').size().to_frame('count'))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 8. Pełne dane\n",
        "\n",
        "Tabela `df` ma wszystkie kolumny diagnostyczne — możesz przeglądać dowolne fragmenty.\n",
    ]))

    cells.append(_make_cell("code", [
        "df.columns.tolist()\n",
    ]))

    # Zbuduj notebook
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    notebook_path.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


def generate_prediction_notebook(
    revision_date: str,
    parquet_path: Path,
    notebook_path: Path,
    previous_revision: str,
) -> None:
    """Generuje .ipynb dla predykcji rewizji (bez ground truth).

    Args:
        revision_date: data rewizji (YYYY-MM-DD)
        parquet_path: ścieżka do prediction_*.parquet
        notebook_path: gdzie zapisać .ipynb
        previous_revision: data poprzedniej rewizji (dla deltacji)
    """
    parquet_rel = parquet_path.name
    cells = []

    cells.append(_make_cell("markdown", [
        f"# Predykcja składu mWIG40 — rewizja {revision_date}\n",
        "\n",
        f"Notebook diagnostyczny dla predykcji. **Brak ground truth** — porównujemy z "
        f"poprzednią rewizją ({previous_revision}) i kandydatami z biznesradar.\n",
        "\n",
        f"Źródła danych:\n",
        f"- universe: scrape biznesradar WIG\n",
        f"- FF shares: derived z biznesradar weight_pct + reference ticker (KGH/KGHM)\n",
        f"- OHLCV: stooq (`output/{revision_date[:7].replace('-','_')}_revision/wig{revision_date[:7].replace('-','_')}_ohlcv.parquet`)\n",
        f"- previous mWIG40/WIG20: `output/wig_history/index_portfolios.parquet`\n",
    ]))

    cells.append(_make_cell("code", [
        "import pandas as pd\n",
        "from pathlib import Path\n",
        "\n",
        f"df = pd.read_parquet('{parquet_rel}')\n",
        "\n",
        "portfolios = pd.read_parquet('../wig_history/index_portfolios.parquet')\n",
        "portfolios['revision_date'] = pd.to_datetime(portfolios['revision_date']).dt.strftime('%Y-%m-%d')\n",
        f"prev_mwig40 = portfolios[(portfolios['index_name']=='mWIG40') & (portfolios['revision_date']=='{previous_revision}')]\n",
        f"prev_wig20  = portfolios[(portfolios['index_name']=='WIG20')  & (portfolios['revision_date']=='{previous_revision}')]\n",
        "\n",
        f"print(f'Predykcja: {{len(df)}} spółek w uniwersum')\n",
        f"print(f'Previous mWIG40 ({previous_revision}): {{len(prev_mwig40)}}, previous WIG20: {{len(prev_wig20)}}')\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 1. Funnel pipeline\n",
    ]))
    cells.append(_make_cell("code", [
        "print('Filtry:')\n",
        "print(f'  passed_basic:    {df[\"passed_basic\"].sum()}/{len(df)}')\n",
        "print(f'  + passed_mwo:    {(df[\"passed_basic\"] & df[\"passed_mwo\"]).sum()}')\n",
        "print(f'  + passed_quartile: {(df[\"passed_basic\"] & df[\"passed_mwo\"] & df[\"passed_quartile\"]).sum()}')\n",
        "print(f'  W rankingu (pozycja): {df[\"ranking_position\"].notna().sum()}')\n",
        "print()\n",
        "print('Powody odrzucenia (basic):')\n",
        "display(df[df['basic_failure_reason'] != ''].groupby('basic_failure_reason').size().to_frame('count'))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 2. Predicted mWIG40 (40 spółek)\n",
    ]))
    cells.append(_make_cell("code", [
        "pred_mwig40 = df[df['predicted_mwig40']].sort_values('ranking_position')\n",
        "display(pred_mwig40[['ticker_gpw','isin','ranking_position','ranking_score','sT','sC',\n",
        "                     'was_in_mwig40_before','fill_up_added','capped_down']].reset_index(drop=True))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 3. Predicted WIG20 (kontekst kaskady)\n",
    ]))
    cells.append(_make_cell("code", [
        "pred_wig20 = df[df['predicted_wig20']].sort_values('ranking_position')\n",
        "display(pred_wig20[['ticker_gpw','isin','ranking_position','ranking_score','sT','sC',\n",
        "                    'was_in_wig20_before','fill_up_wig20_added']].reset_index(drop=True))\n",
    ]))

    cells.append(_make_cell("markdown", [
        f"## 4. Delta vs {previous_revision}\n",
    ]))
    cells.append(_make_cell("code", [
        "prev_mwig40_isins = set(prev_mwig40['isin'])\n",
        "pred_mwig40_isins = set(pred_mwig40['isin'])\n",
        "\n",
        "entrants = pred_mwig40[~pred_mwig40['isin'].isin(prev_mwig40_isins)]\n",
        "exits_isin = prev_mwig40_isins - pred_mwig40_isins\n",
        "exits = prev_mwig40[prev_mwig40['isin'].isin(exits_isin)].copy()\n",
        "\n",
        "# Gdzie poszli ci, którzy wyszli? Awans (WIG20) czy spadek (sWIG80 / odpadli)?\n",
        "exits = exits.merge(\n",
        "    df[['isin','ranking_position','predicted_wig20','predicted_mwig40','initial_index','passed_basic','passed_mwo','passed_quartile']],\n",
        "    on='isin', how='left'\n",
        ")\n",
        "exits['destination'] = 'odpadli'\n",
        "exits.loc[exits['predicted_wig20'].fillna(False), 'destination'] = 'WIG20 (awans)'\n",
        "exits.loc[(exits['initial_index']=='sWIG80') & ~exits['predicted_wig20'].fillna(False), 'destination'] = 'sWIG80'\n",
        "\n",
        f"print(f'WCHODZĄ ({{len(entrants)}}):')\n",
        "display(entrants[['ticker_gpw','isin','ranking_position','ranking_score','fill_up_added']].reset_index(drop=True))\n",
        f"print(f'\\nWYCHODZĄ ({{len(exits)}}):')\n",
        "display(exits[['ticker','isin','ranking_position','destination']].reset_index(drop=True))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 5. Spółki przy progu (kandydaci na zmianę w kolejnej rewizji)\n",
        "\n",
        "Pozycje 35-50 — strefa wrażliwa. Drobne ruchy cen/wolumenów mogą zmienić skład.\n",
    ]))
    cells.append(_make_cell("code", [
        "near_threshold = df[df['ranking_position'].between(35, 55)].sort_values('ranking_position')\n",
        "display(near_threshold[['ticker_gpw','isin','ranking_position','ranking_score','sT','sC',\n",
        "                        'predicted_mwig40','was_in_mwig40_before']].reset_index(drop=True))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 6. MWO diagnostyka (ci, których MWO odrzucił)\n",
    ]))
    cells.append(_make_cell("code", [
        "mwo_failed = df[df['passed_basic'] & ~df['passed_mwo']].sort_values('mwo_n_months_above_threshold', ascending=False)\n",
        "display(mwo_failed[['ticker_gpw','isin','mwo_n_months_above_threshold','mwo_n_months_above_threshold_last6',\n",
        "                    'passed_mwo_rule1','passed_mwo_rule2','weight_pct_biznesradar']].reset_index(drop=True))\n",
    ]))

    cells.append(_make_cell("markdown", [
        "## 7. Pełna tabela diagnostyczna\n",
    ]))
    cells.append(_make_cell("code", [
        "df.columns.tolist()\n",
    ]))

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
