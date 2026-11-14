#!/usr/bin/env python3
"""
Analiza przejść do mWIG40 na bazie historycznych portfeli GPW Benchmark.

Wejście:
    - output/index_portfolios.parquet
    - output/reserve_lists.parquet

Wyjście:
    - raport Markdown z podsumowaniem przejść do mWIG40

Uruchomienie:
    python analyze_mwig40_transitions.py
    python analyze_mwig40_transitions.py --report output/mwig40_transition_report.md
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

DEFAULT_PORTFOLIOS = Path("output/index_portfolios.parquet")
DEFAULT_RESERVES = Path("output/reserve_lists.parquet")
DEFAULT_REPORT = Path("output/mwig40_transition_report.md")

PREVIOUS_BUCKET_ORDER = [
    "sWIG80 -> mWIG40",
    "WIG20 -> mWIG40",
    "WIG outside sWIG80 -> mWIG40",
    "IPO/outside WIG -> mWIG40",
]

CATEGORY_ORDER = [
    "sWIG80 -> mWIG40",
    "WIG20 -> mWIG40",
    "Re-entry -> mWIG40",
    "WIG outside sWIG80 -> mWIG40",
    "IPO/outside WIG -> mWIG40",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analiza przejść do mWIG40")
    parser.add_argument(
        "--portfolios",
        type=Path,
        default=DEFAULT_PORTFOLIOS,
        help="Ścieżka do output/index_portfolios.parquet",
    )
    parser.add_argument(
        "--reserves",
        type=Path,
        default=DEFAULT_RESERVES,
        help="Ścieżka do output/reserve_lists.parquet",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Ścieżka wyjściowa dla raportu Markdown",
    )
    return parser.parse_args()


def load_inputs(portfolios_path: Path, reserves_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not portfolios_path.exists():
        raise FileNotFoundError(f"Brak pliku portfeli: {portfolios_path}")
    if not reserves_path.exists():
        raise FileNotFoundError(f"Brak pliku list rezerwowych: {reserves_path}")

    portfolios = pd.read_parquet(portfolios_path)
    reserves = pd.read_parquet(reserves_path)

    portfolios["revision_date"] = pd.to_datetime(portfolios["revision_date"])
    portfolios["ranking_date"] = pd.to_datetime(portfolios["ranking_date"], errors="coerce")
    reserves["revision_date"] = pd.to_datetime(reserves["revision_date"])

    return portfolios, reserves


def _pct(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "0.0%"
    return f"{(100.0 * numerator / denominator):.1f}%"


def _format_bool(value: bool) -> str:
    return "yes" if bool(value) else "no"


def _format_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, bool):
        return _format_bool(value)
    if isinstance(value, float):
        return f"{value:.1f}" if value.is_integer() else f"{value:.4f}"
    return str(value)


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"

    headers = [str(col) for col in df.columns]
    rows = [[_format_value(value) for value in row] for row in df.itertuples(index=False, name=None)]
    widths = [len(header) for header in headers]

    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    header_line = "| " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)) + " |"
    separator_line = "| " + " | ".join("-" * widths[idx] for idx in range(len(headers))) + " |"
    row_lines = [
        "| " + " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator_line, *row_lines])


def build_transition_events(portfolios: pd.DataFrame, reserves: pd.DataFrame) -> pd.DataFrame:
    index_sets = {
        (revision_date, index_name): set(group["isin"])
        for (revision_date, index_name), group in portfolios.groupby(["revision_date", "index_name"])
    }
    reserve_sets = {
        (revision_date, index_name): set(group["isin"])
        for (revision_date, index_name), group in reserves.groupby(["revision_date", "index_name"])
    }
    reserve_rank = {
        (row.revision_date, row.index_name, row.isin): int(row.lp)
        for row in reserves.itertuples(index=False)
    }
    current_ticker = {
        (row.revision_date, row.isin): row.ticker
        for row in portfolios.drop_duplicates(["revision_date", "isin"]).itertuples(index=False)
    }
    first_seen = portfolios.groupby("isin")["revision_date"].min().to_dict()
    revision_dates = sorted(portfolios["revision_date"].unique())

    events: list[dict[str, object]] = []
    for pos in range(1, len(revision_dates)):
        previous_date = revision_dates[pos - 1]
        current_date = revision_dates[pos]

        previous_mwig40 = index_sets.get((previous_date, "mWIG40"), set())
        current_mwig40 = index_sets.get((current_date, "mWIG40"), set())
        new_entries = sorted(current_mwig40 - previous_mwig40)

        for isin in new_entries:
            in_previous_wig20 = isin in index_sets.get((previous_date, "WIG20"), set())
            in_previous_swig80 = isin in index_sets.get((previous_date, "sWIG80"), set())
            in_previous_wig = isin in index_sets.get((previous_date, "WIG"), set())
            was_ever_in_mwig40_before = any(
                isin in index_sets.get((historical_date, "mWIG40"), set())
                for historical_date in revision_dates[: pos - 1]
            )
            in_previous_mwig40_reserve = isin in reserve_sets.get((previous_date, "mWIG40"), set())

            if in_previous_wig20:
                previous_bucket = "WIG20 -> mWIG40"
            elif in_previous_swig80:
                previous_bucket = "sWIG80 -> mWIG40"
            elif in_previous_wig:
                previous_bucket = "WIG outside sWIG80 -> mWIG40"
            else:
                previous_bucket = "IPO/outside WIG -> mWIG40"

            if in_previous_wig20:
                category = "WIG20 -> mWIG40"
            elif was_ever_in_mwig40_before:
                category = "Re-entry -> mWIG40"
            elif in_previous_swig80:
                category = "sWIG80 -> mWIG40"
            elif in_previous_wig:
                category = "WIG outside sWIG80 -> mWIG40"
            else:
                category = "IPO/outside WIG -> mWIG40"

            events.append(
                {
                    "revision_date": pd.Timestamp(current_date).date().isoformat(),
                    "previous_revision_date": pd.Timestamp(previous_date).date().isoformat(),
                    "isin": isin,
                    "ticker": current_ticker.get((current_date, isin), isin),
                    "previous_bucket": previous_bucket,
                    "category": category,
                    "was_ever_in_mwig40_before": was_ever_in_mwig40_before,
                    "in_previous_mwig40_reserve": in_previous_mwig40_reserve,
                    "previous_mwig40_reserve_rank": reserve_rank.get((previous_date, "mWIG40", isin)),
                    "first_seen_in_dataset": pd.Timestamp(first_seen[isin]).date().isoformat(),
                }
            )

    events_df = pd.DataFrame(events)
    if events_df.empty:
        raise ValueError("Nie znaleziono żadnych wejść do mWIG40.")
    return events_df


def build_count_share_table(events: pd.DataFrame, column: str, order: list[str]) -> pd.DataFrame:
    counts = events[column].value_counts().reindex(order, fill_value=0)
    total = int(counts.sum())
    return pd.DataFrame(
        {
            "Transition": counts.index,
            "Count": counts.values,
            "Share": [_pct(int(value), total) for value in counts.values],
        }
    )


def build_revision_matrix(events: pd.DataFrame) -> pd.DataFrame:
    matrix = pd.crosstab(events["revision_date"], events["previous_bucket"])
    matrix = matrix.reindex(columns=PREVIOUS_BUCKET_ORDER, fill_value=0).reset_index()
    matrix.columns = ["Revision date", *PREVIOUS_BUCKET_ORDER]
    return matrix


def build_reserve_coverage_tables(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    total = len(events)
    previous_reserve_count = int(events["in_previous_mwig40_reserve"].sum())

    overall = pd.DataFrame(
        [
            {
                "Metric": "Entered mWIG40 from previous mWIG40 reserve list",
                "Count": previous_reserve_count,
                "Share": _pct(previous_reserve_count, total),
            }
        ]
    )

    grouped = (
        events.groupby("previous_bucket", dropna=False)["in_previous_mwig40_reserve"]
        .agg(["sum", "count"])
        .reindex(PREVIOUS_BUCKET_ORDER, fill_value=0)
        .reset_index()
    )
    grouped["Share"] = grouped.apply(lambda row: _pct(int(row["sum"]), int(row["count"])), axis=1)
    grouped = grouped.rename(
        columns={
            "previous_bucket": "Previous bucket",
            "sum": "Reserve hits",
            "count": "Total entries",
        }
    )[["Previous bucket", "Reserve hits", "Total entries", "Share"]]

    return overall, grouped


def build_report(
    portfolios_path: Path,
    reserves_path: Path,
    report_path: Path,
    portfolios: pd.DataFrame,
    reserves: pd.DataFrame,
    events: pd.DataFrame,
) -> str:
    total_events = len(events)
    unique_companies = events["isin"].nunique()
    ex_reentries = events.loc[events["category"] != "Re-entry -> mWIG40"]

    previous_bucket_table = build_count_share_table(events, "previous_bucket", PREVIOUS_BUCKET_ORDER)
    category_table = build_count_share_table(events, "category", CATEGORY_ORDER)
    ex_reentries_table = build_count_share_table(ex_reentries, "previous_bucket", PREVIOUS_BUCKET_ORDER)
    revision_matrix = build_revision_matrix(events)
    reserve_overall, reserve_by_bucket = build_reserve_coverage_tables(events)

    event_log = events[
        [
            "revision_date",
            "previous_revision_date",
            "ticker",
            "isin",
            "previous_bucket",
            "category",
            "was_ever_in_mwig40_before",
            "in_previous_mwig40_reserve",
            "previous_mwig40_reserve_rank",
            "first_seen_in_dataset",
        ]
    ].rename(
        columns={
            "revision_date": "Revision date",
            "previous_revision_date": "Previous revision",
            "ticker": "Ticker",
            "isin": "ISIN",
            "previous_bucket": "Previous bucket",
            "category": "Category",
            "was_ever_in_mwig40_before": "Was ever in mWIG40 before",
            "in_previous_mwig40_reserve": "In previous mWIG40 reserve",
            "previous_mwig40_reserve_rank": "Previous reserve rank",
            "first_seen_in_dataset": "First seen in dataset",
        }
    ).sort_values(["Revision date", "Ticker", "ISIN"])

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Raport: przejścia do mWIG40",
        "",
        f"Wygenerowano: `{generated_at}`",
        "",
        "## Źródła danych",
        "",
        f"- Portfele: `{portfolios_path}`",
        f"- Listy rezerwowe: `{reserves_path}`",
        f"- Raport: `{report_path}`",
        "",
        "## Zakres analizy",
        "",
        f"- Rewizje w portfelach: `{portfolios['revision_date'].min().date()}` -> `{portfolios['revision_date'].max().date()}`",
        f"- Liczba rewizji: `{portfolios['revision_date'].nunique()}`",
        f"- Eventy wejścia do `mWIG40`: `{total_events}`",
        f"- Unikalne spółki, które weszły do `mWIG40`: `{unique_companies}`",
        "",
        "## Wynik główny: skąd przychodziły nowe wejścia do mWIG40",
        "",
        "Macierz poniżej klasyfikuje każdą spółkę według jej statusu w bezpośrednio poprzedniej rewizji.",
        "",
        dataframe_to_markdown(previous_bucket_table),
        "",
        "## Wariant z wydzieleniem re-entry",
        "",
        "W tej wersji `Re-entry -> mWIG40` ma pierwszeństwo przed klasyfikacją jako `sWIG80 -> mWIG40`, jeśli spółka była już kiedyś wcześniej w `mWIG40`.",
        "",
        dataframe_to_markdown(category_table),
        "",
        "## Czysty awans po wyłączeniu re-entry",
        "",
        f"Po wyłączeniu `Re-entry -> mWIG40` zostaje `{len(ex_reentries)}` eventów wejścia.",
        "",
        dataframe_to_markdown(ex_reentries_table),
        "",
        "## Pokrycie przez listę rezerwową mWIG40",
        "",
        dataframe_to_markdown(reserve_overall),
        "",
        dataframe_to_markdown(reserve_by_bucket),
        "",
        "## Macierz przejść w czasie",
        "",
        dataframe_to_markdown(revision_matrix),
        "",
        "## Dziennik eventów wejścia do mWIG40",
        "",
        dataframe_to_markdown(event_log),
        "",
        "## Metodologia",
        "",
        "- Event wejścia jest definiowany jako `mWIG40(T) - mWIG40(T-1)` między kolejnymi rewizjami.",
        "- `Previous bucket` oznacza wyłącznie status spółki w bezpośrednio poprzedniej rewizji.",
        "- `Re-entry -> mWIG40` oznacza, że spółka nie była w `mWIG40` w `T-1`, ale była tam w jakiejkolwiek wcześniejszej rewizji.",
        "- `IPO/outside WIG -> mWIG40` oznacza brak obecności w `WIG` w poprzedniej rewizji.",
        "- `In previous mWIG40 reserve` sprawdza obecność na liście rezerwowej `mWIG40` z poprzedniej rewizji.",
    ]

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    portfolios, reserves = load_inputs(args.portfolios, args.reserves)
    events = build_transition_events(portfolios, reserves)
    report = build_report(args.portfolios, args.reserves, args.report, portfolios, reserves, events)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print(f"Zapisano raport: {args.report}")
    print(f"Eventy wejścia do mWIG40: {len(events)}")


if __name__ == "__main__":
    main()
