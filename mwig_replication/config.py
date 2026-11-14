"""
Konfiguracja modułu replikacji rankingu mWIG40.

Zawiera:
- Ścieżki do plików input
- Parametry per-rewizja (REVISIONS dict)
- Stałe metodologiczne (wagi rankingu, parametry filtrów)
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# ŚCIEŻKI
# ---------------------------------------------------------------------------

# Korzeń projektu — wykrywany dynamicznie (2 poziomy w górę od tego pliku)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Input
INDEX_PORTFOLIOS_PATH = PROJECT_ROOT / "output" / "wig_history" / "index_portfolios.parquet"
RESERVE_LISTS_PATH    = PROJECT_ROOT / "output" / "wig_history" / "reserve_lists.parquet"
TICKER_MAP_PATH       = PROJECT_ROOT / "output" / "maps" / "ticker_isin_stooq_map.csv"

# OHLCV — per-rewizyjne, ścieżka determinowana przez rewizję
def ohlcv_path_for_revision(revision_date: str) -> Path:
    """Zwraca ścieżkę do Parquet OHLCV dla danej rewizji.
    Konwencja: revision_date jak '2025-03-21' → 'output/2025_03_revision/wig2025_03_ohlcv.parquet'.
    """
    yyyy_mm = revision_date.replace("-", "_")[:7]  # '2025_03'
    return PROJECT_ROOT / "output" / f"{yyyy_mm}_revision" / f"wig{yyyy_mm}_ohlcv.parquet"


# Output — wszystko ląduje w katalogu rewizji
def output_dir_for_revision(revision_date: str) -> Path:
    """Katalog output dla danej rewizji."""
    yyyy_mm = revision_date.replace("-", "_")[:7]
    return PROJECT_ROOT / "output" / f"{yyyy_mm}_revision"


# ---------------------------------------------------------------------------
# STAŁE METODOLOGICZNE (niezmienne w całym okresie 2021-2025)
# ---------------------------------------------------------------------------

RANKING_WEIGHT_TURNOVER = 0.4      # waga sT
RANKING_WEIGHT_FF_CAP   = 0.6      # waga sC

# Filtr ostatniego kwartyla
LAST_QUARTILE_FRACTION = 0.25      # odrzucamy dolne 25%

# Filtr "1 mln EUR" — jeśli nie wpisano kursu, filtr pomijamy
EUR_THRESHOLD_MILLIONS = 1.0

# Liczba miesięcy MWO
MWO_LOOKBACK_MONTHS = 12
MWO_RULE1_REQUIRED  = 8   # 8 z 12
MWO_RULE2_REQUIRED  = 4   # 4 z ostatnich 6
MWO_RULE2_LOOKBACK  = 6

# Liczba spółek docelowo w mWIG40
MWIG40_SIZE = 40

# ---------------------------------------------------------------------------
# PROGI BUFORA per (epoka, typ rewizji)
# ---------------------------------------------------------------------------
# Epoka 4 = od 31.01.2025 (nowa metodyka GPW Benchmark).
# Roczna (marzec): szerokie bufory, swoboda wymiany składu.
# Kwartalna (czerwiec/wrzesień/grudzień): wąskie bufory, ograniczenie rotacji.

THRESHOLDS_EPOCH_4_ANNUAL = {
    "entry_threshold_wig20":        15,
    "maintenance_threshold_wig20":  25,
    "entry_threshold_mwig40":       50,
    "maintenance_threshold_mwig40": 70,
    "entry_threshold_swig80":       90,
    "maintenance_threshold_swig80": 100,
}

THRESHOLDS_EPOCH_4_QUARTERLY = {
    "entry_threshold_wig20":        10,
    "maintenance_threshold_wig20":  30,
    "entry_threshold_mwig40":       45,
    "maintenance_threshold_mwig40": 80,
    # sWIG80 — wartości kwartalne do uzupełnienia gdy będą potrzebne.
    "entry_threshold_swig80":       None,
    "maintenance_threshold_swig80": None,
}


# ---------------------------------------------------------------------------
# REWIZJE — parametry per-rewizja
# ---------------------------------------------------------------------------

REVISIONS = {
    "2025-03-21": {
        # Daty
        "ranking_date":      "2025-02-21",
        "previous_revision": "2024-12-20",

        # Charakter
        "type":  "annual",        # annual | quarterly
        "epoch": 4,

        # Progi bufora
        **THRESHOLDS_EPOCH_4_ANNUAL,

        # MWO
        "mwo_threshold_pct": 0.0100,   # 0,0100% — w jednostce DWO

        # Fast-track
        "fast_track_threshold_pct": 2.5,

        # Reguły dodatkowe
        "wezwania_rule_active": True,

        # Kurs EUR/PLN (do wpisania ręcznie przez Maciej)
        "eur_pln_rate": None,
    },

    "2026-03-20": {
        # Daty
        "ranking_date":      "2026-02-20",   # 3. piątek lutego (metodyka GPW Benchmark)
        "previous_revision": "2025-12-19",

        # Charakter
        "type":  "annual",
        "epoch": 4,

        # Progi bufora
        **THRESHOLDS_EPOCH_4_ANNUAL,

        # MWO
        "mwo_threshold_pct": 0.0100,

        # Fast-track
        "fast_track_threshold_pct": 2.5,

        # Reguły dodatkowe
        "wezwania_rule_active": True,

        # Kurs EUR/PLN — pomijamy filtr 1 mln EUR
        "eur_pln_rate": None,
    },

    "2026-06-19": {
        # Daty
        "ranking_date":      "2026-05-22",   # planowany dzień rankingu (do potwierdzenia)
        "previous_revision": "2026-03-20",

        # Charakter
        "type":  "quarterly",
        "epoch": 4,

        # Progi bufora (kwartalne)
        **THRESHOLDS_EPOCH_4_QUARTERLY,

        # MWO
        "mwo_threshold_pct": 0.0100,

        # Fast-track
        "fast_track_threshold_pct": 2.5,

        # Reguły dodatkowe
        "wezwania_rule_active": True,

        # Kurs EUR/PLN — pomijamy filtr 1 mln EUR
        "eur_pln_rate": None,
    },
}


def get_revision_params(revision_date: str) -> dict:
    """Pobiera parametry rewizji. Crashuje z czytelnym błędem jeśli brak."""
    if revision_date not in REVISIONS:
        available = ", ".join(REVISIONS.keys())
        raise ValueError(
            f"Brak parametrów dla rewizji '{revision_date}'. "
            f"Dostępne: {available}"
        )
    return REVISIONS[revision_date]
