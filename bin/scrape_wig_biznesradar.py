"""
Scraper bieżącego składu WIG z biznesradar.pl

Pobiera stronę https://www.biznesradar.pl/gielda/indeks:WIG (i analogicznie dla
innych indeksów) i parsuje tabelę składową na DataFrame z kolumnami:

  ticker_short  - kod biznesradar (np. KGH)
  ticker_long   - kod nazwy (np. KGHM)
  name          - pełna nazwa spółki
  time          - czas ostatniego notowania (string)
  price         - kurs zamknięcia (float)
  change_abs    - zmiana absolutna (float)
  change_pct    - zmiana procentowa (float)
  reference     - kurs odniesienia (float)
  open          - kurs otwarcia (float)
  low           - min dnia (float)
  high          - max dnia (float)
  volume        - wolumen (int)
  turnover      - obrót w PLN (int)
  weight_pct    - udział % w indeksie (float)

Uwagi:
- Format liczb pl-PL: spacja jako separator tysięcy, przecinek dziesiętny.
- Tabela jest server-rendered (nie JS), więc requests + BeautifulSoup wystarczy.
- Klasa CSS tabeli na biznesradar to zwykle "qTableFull" (do potwierdzenia
  empirycznie — parser jest tolerancyjny i bierze pierwszą tabelę z 13 kolumnami).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}


def _to_float(s: str) -> float | None:
    """Konwertuje pl-PL liczbę ('316,80', '(+3,73%)', '897 679') na float.
    Zwraca None gdy nie da się sparsować."""
    if s is None:
        return None
    s = s.strip().replace("\xa0", " ").replace(" ", "")
    s = s.replace("(", "").replace(")", "").replace("%", "")
    if s in {"", "-", "—"}:
        return None
    s = s.replace(",", ".")
    # usuń znak + na początku, zachowaj -
    if s.startswith("+"):
        s = s[1:]
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> int | None:
    f = _to_float(s)
    if f is None:
        return None
    return int(f)


# Mapowanie tickerów short -> long ekstraktowane z linku "TICKER_SHORT (TICKER_LONG)"
_TICKER_RE = re.compile(r"^\s*([A-Z0-9.\-]+)\s*(?:\(([A-Z0-9.\-]+)\))?\s*$")


def parse_index_components_html(html: str) -> pd.DataFrame:
    """Parsuje HTML strony biznesradar 'Komponenty indeksu X' do DataFrame."""
    soup = BeautifulSoup(html, "html.parser")

    # Znajdź tabelę komponentów: wybierz tabelę z największą liczbą wierszy
    # data (td z linkiem do /notowania/...) — to jest tabela składu indeksu.
    tables = soup.find_all("table")
    best, best_score = None, 0
    for tbl in tables:
        score = 0
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 11:
                continue
            a = tds[0].find("a", href=re.compile(r"/notowania/"))
            if a is not None:
                score += 1
        if score > best_score:
            best, best_score = tbl, score
    if best is None or best_score == 0:
        raise RuntimeError(
            "Nie znalazłem tabeli komponentów. Sprawdź czy URL/HTML jest prawidłowy."
        )
    target = best

    records = []
    for tr in target.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 11:
            continue

        # Profil: link "TICKER_SHORT (TICKER_LONG)" lub samo "TICKER_SHORT"
        profile_cell = tds[0]
        a = profile_cell.find("a")
        if a is None:
            continue
        ticker_text = a.get_text(strip=True)
        m = _TICKER_RE.match(ticker_text)
        if not m:
            continue
        ticker_short = m.group(1)
        ticker_long = m.group(2) or ticker_short
        name = a.get("title", "").strip() or ticker_long

        # Reszta kolumn (po Profil): Czas, Kurs, Zmiana, Zmiana%, Odn., Otw.,
        # Min, Max, Wolumen, Obrót, Udział
        # Jeśli kolumn jest więcej (np. ikony trendu), ignoruj nadmiar.
        rec = {
            "ticker_short": ticker_short,
            "ticker_long": ticker_long,
            "name": name,
            "time": tds[1].get_text(strip=True),
            "price": _to_float(tds[2].get_text()),
            "change_abs": _to_float(tds[3].get_text()),
            "change_pct": _to_float(tds[4].get_text()),
            "reference": _to_float(tds[5].get_text()),
            "open": _to_float(tds[6].get_text()),
            "low": _to_float(tds[7].get_text()),
            "high": _to_float(tds[8].get_text()),
            "volume": _to_int(tds[9].get_text()),
            "turnover": _to_int(tds[10].get_text()),
            "weight_pct": _to_float(tds[11].get_text()) if len(tds) > 11 else None,
        }
        records.append(rec)

    df = pd.DataFrame.from_records(records)
    return df


def fetch_index_components(
    index_code: str = "WIG",
    session: requests.Session | None = None,
    retries: int = 3,
    backoff: float = 2.0,
) -> pd.DataFrame:
    """Pobiera i parsuje skład indeksu z biznesradar.pl.

    index_code: np. 'WIG', 'mWIG40', 'sWIG80', 'WIG20', 'WIG30'.
    """
    url = f"https://www.biznesradar.pl/gielda/indeks:{index_code}"
    sess = session or requests.Session()

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = sess.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            df = parse_index_components_html(r.text)
            if df.empty:
                raise RuntimeError("Pusta tabela — parsowanie nie znalazło wierszy.")
            df.insert(0, "index_code", index_code)
            df.insert(0, "fetched_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            return df
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * attempt)
            else:
                raise
    assert last_err is not None
    raise last_err


def fetch_indices(
    codes: list[str] = ("WIG", "WIG20", "mWIG40", "sWIG80"),
    sleep_between: float = 1.5,
) -> dict[str, pd.DataFrame]:
    """Pobiera skład kilku indeksów po kolei (z przerwą, żeby nie hammerować)."""
    sess = requests.Session()
    out = {}
    for code in codes:
        df = fetch_index_components(code, session=sess)
        out[code] = df
        time.sleep(sleep_between)
    return out


def sanity_report(df: pd.DataFrame, index_code: str) -> dict:
    """Zwraca raport sanity dla pojedynczego indeksu."""
    n = len(df)
    weight_sum = float(df["weight_pct"].sum())
    missing_price = int(df["price"].isna().sum())
    missing_weight = int(df["weight_pct"].isna().sum())
    missing_turnover = int(df["turnover"].isna().sum())
    # Expected size hint (z definicji indeksów GPW Benchmark)
    expected = {"WIG20": 20, "WIG30": 30, "mWIG40": 40, "sWIG80": 80}.get(index_code)
    return {
        "index_code": index_code,
        "rows": n,
        "weight_sum_pct": round(weight_sum, 3),
        "expected_rows": expected,
        "rows_ok": (expected is None) or (n == expected),
        "missing_price": missing_price,
        "missing_weight": missing_weight,
        "missing_turnover": missing_turnover,
        # Suma powinna być ~100% (z drobną tolerancją na zaokrąglenia
        # i ewentualne capowanie). Sygnalizuje gdy spada poniżej 95%.
        "weight_sum_suspicious": weight_sum < 95.0 or weight_sum > 102.0,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--index",
        default="WIG",
        help="Kod indeksu lub lista po przecinku, np. 'WIG,mWIG40,sWIG80'. Default: WIG.",
    )
    p.add_argument(
        "--out-dir",
        default=None,
        help="Katalog wyjściowy. Zapisuje per-indeks: {index}_{YYYYMMDD_HHMM}.parquet",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Pojedyncza ścieżka wyjściowa (gdy podajesz jeden indeks).",
    )
    p.add_argument(
        "--from-html",
        default=None,
        help="Zamiast pobierać z sieci, sparsuj lokalny plik HTML (debug).",
    )
    args = p.parse_args(argv)

    codes = [c.strip() for c in args.index.split(",") if c.strip()]

    if args.from_html:
        if len(codes) != 1:
            raise SystemExit("--from-html wymaga pojedynczego --index")
        html = Path(args.from_html).read_text(encoding="utf-8")
        df = parse_index_components_html(html)
        df.insert(0, "index_code", codes[0])
        df.insert(0, "fetched_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        frames = {codes[0]: df}
    else:
        frames = fetch_indices(codes) if len(codes) > 1 else {codes[0]: fetch_index_components(codes[0])}

    for code, df in frames.items():
        rep = sanity_report(df, code)
        print(f"\n=== {code} ===  rows={rep['rows']}  Σweight={rep['weight_sum_pct']}%  "
              f"missing(price/weight/turnover)={rep['missing_price']}/{rep['missing_weight']}/{rep['missing_turnover']}")
        if rep.get("expected_rows") is not None and not rep["rows_ok"]:
            print(f"  ⚠️  oczekiwano {rep['expected_rows']} spółek, jest {rep['rows']}")
        if rep["weight_sum_suspicious"]:
            print(f"  ⚠️  Suma udziałów {rep['weight_sum_pct']}% poza zakresem 95-102% — sprawdź parsowanie")
        print(df.nlargest(5, "weight_pct")[["ticker_short", "name", "price", "turnover", "weight_pct"]].to_string(index=False))

    if args.out:
        if len(frames) != 1:
            raise SystemExit("--out wymaga pojedynczego --index. Użyj --out-dir dla wielu.")
        df = next(iter(frames.values()))
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix == ".parquet":
            df.to_parquet(out_path, index=False)
        elif out_path.suffix == ".csv":
            df.to_csv(out_path, index=False)
        else:
            raise SystemExit(f"Nieznane rozszerzenie: {out_path.suffix}")
        print(f"\nZapisano: {out_path}")

    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        for code, df in frames.items():
            path = out_dir / f"{code}_{stamp}.parquet"
            df.to_parquet(path, index=False)
            print(f"Zapisano: {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
