#!/usr/scripts/env python3
"""
GPW Benchmark — Ekstrakcja zmian z regulaminów
================================================

Pobiera wszystkie wersje "Regulaminu Rodziny Indeksów Giełdowych" oraz
"Regulaminu ustalania liczby akcji w wolnym obrocie" obowiązujące w okresie
2021-03 → 2025-09 i ekstrahuje sekcje opisujące zmiany merytoryczne.

Cel: zidentyfikować "metodologiczne breakpointy" — momenty w których zasady
rankingu/kwalifikacji się zmieniały.

Uruchomienie:
    pip install pdfplumber requests
    python regulation_changelog_extractor.py

Output:
    - data/regulations/*.pdf   — pobrane PDFy
    - output/regulation_changelog.md  — wyciąg zmian per wersja
    - output/regulation_summary.md    — podsumowanie merytorycznych zmian

Autor: Maciej + Claude (projekt predykatów mWIG40)
"""

import re
import time
import logging
from pathlib import Path
from datetime import date
from dataclasses import dataclass, field

import requests
import pdfplumber

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

BASE = "https://www.gpwbenchmark.pl/pub/BENCHMARK/files/indeksy-gieldowe-regulacje/pl"

# Wszystkie wersje regulaminu Rodziny Indeksów Giełdowych obowiązujące
# w okresie naszego badania (2021-03 → 2025-09)
# Format: (filename, valid_from, valid_to, description)
REGULATIONS_INDEKSY = [
    # Pre-2021 wersja — niedostępna w archiwum jako osobny PDF
    # (obowiązywała przed 20.12.2021)

    ("Regulamin_Rodziny_Indeksow_Gieldowych_7.12.21.pdf", "2021-12-20", "2022-03-20",
     "Wersja z 7.12.2021"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_21.03.22.pdf", "2022-03-21", "2022-03-31",
     "Wersja z 21.03.2022 (krótka)"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_1.04.22.pdf", "2022-04-01", "2023-01-31",
     "Wersja z 1.04.2022"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_1.02.23.pdf", "2023-02-01", "2023-06-18",
     "Wersja z 1.02.2023"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_19.06.2023.pdf", "2023-06-19", "2023-09-03",
     "Wersja z 19.06.2023"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_4.09.2023.pdf", "2023-09-04", "2024-03-14",
     "Wersja z 4.09.2023"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_15.03.2024.pdf", "2024-03-15", "2024-04-11",
     "Wersja z 15.03.2024"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_12.04.2024.pdf", "2024-04-12", "2024-06-20",
     "Wersja z 12.04.2024"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_21.06.2024.pdf", "2024-06-21", "2024-06-27",
     "Wersja z 21.06.2024 (krótka)"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_28.06.2024.pdf", "2024-06-28", "2024-08-18",
     "Wersja z 28.06.2024"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_19.08.2024.pdf", "2024-08-19", "2024-12-31",
     "Wersja z 19.08.2024"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_1.01.2025.pdf", "2025-01-01", "2025-01-30",
     "Wersja z 1.01.2025"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_31.01.2025.pdf", "2025-01-31", "2025-06-22",
     "Wersja z 31.01.2025"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_23.06.2025.pdf", "2025-06-23", "2025-06-29",
     "Wersja z 23.06.2025 (krótka)"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_30.06.2025.pdf", "2025-06-30", "2025-08-31",
     "Wersja z 30.06.2025"),

    ("Regulamin_Rodziny_Indeksow_Gieldowych_1.09.2025.pdf", "2025-09-01", "2025-10-22",
     "Wersja z 1.09.2025"),
]

# Regulamin ustalania liczby akcji w wolnym obrocie
REGULATIONS_FF = [
    # Pre-2023 wersja — w archiwum opisana jako "obowiązywał od 1.12.2019 do 16.02.2023"
    # ale link nie był widoczny w wyniku wyszukiwania. Dodajemy z założeniem nazwy.

    ("Regulamin_ustalania_liczby_akcji_wolnym_obrocie_17.02.2023.pdf",
     "2023-02-17", "2025-03-04",
     "Wersja z 17.02.2023"),

    # Wersja po 4.03.2025 — niezidentyfikowana z dokładną nazwą pliku
]

# Słowa kluczowe sygnalizujące merytoryczne zmiany
# (vs. kosmetyczne/redakcyjne/zmiany w innych indeksach)
MATERIAL_KEYWORDS = [
    # Filtry kwalifikacyjne
    r"wolny[mc]?\s+obro[ct]",  # wolny obrót / wolnym obrocie
    r"\bMWO\b",
    r"miesi[ęe]czny\s+wska[źz]nik\s+obrotu",
    r"\bDWO\b",
    r"kwartyl",
    r"dual[\s-]?listed",
    r"dual[\s-]?listing",
    r"\bLista\s+Alert",
    r"Strefa\s+Niskiej\s+P[łl]ynno[śs]ci",

    # Mechanika rankingu
    r"ranking",
    r"sT\(",  # składnik turnover
    r"sC\(",  # składnik capitalization
    r"udzia[łl]\s+w\s+obrotach",
    r"udzia[łl]\s+w\s+kapitalizacji",
    r"0[,\.]4",  # waga 0.4 dla obrotów (mogła się zmieniać?)
    r"0[,\.]6",  # waga 0.6 dla FF
    r"warto[śs][cć]\s+akcji\s+w\s+wolnym",

    # Bufor i progi
    r"bufor",
    r"strefa\s+po[śs]rednia",
    r"pozycj[ai]\s+\d{2,3}",  # pozycje rankingowe (np. "pozycja 50", "pozycja 70")
    r"50\.\s*pozycj",  # 50. pozycja
    r"70\.\s*pozycj",
    r"45\.\s*pozycj",
    r"80\.\s*pozycj",

    # Limity udziału
    r"limit\s+\d+%",
    r"10\s*%",
    r"15\s*%",
    r"udzia[łl]\s+jednej\s+sp[oó]łki",

    # Wezwania
    r"wezwani[ae]",
    r"100%\s+akcji",
    r"squeeze[\s-]?out",
    r"przymusowy\s+wykup",

    # Indeksy w naszym scope
    r"\bmWIG40\b",
    r"\bWIG20\b",
    r"\bsWIG80\b",
    r"\bWIG30\b",

    # Specyficzne mechanizmy
    r"szybk[ai][ej]?\s+[śs]cie[żz]k",  # "szybka ścieżka" (fast-track)
    r"fast[\s-]?track",
    r"debiut",
    r"dope[łl]nieni",
    r"uzupe[łl]nieni",
]

# Sekcje regulaminu które typowo zawierają opis zmian
CHANGELOG_SECTION_MARKERS = [
    "Załącznik",
    "Historia zmian",
    "Wykaz zmian",
    "Zmiany w stosunku",
    "Zmiany wprowadzone",
    "Lista zmian",
]

REG_DIR = Path("./data/regulations")
OUTPUT_DIR = Path("./output")

DOWNLOAD_DELAY_SEC = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DOWNLOAD
# ---------------------------------------------------------------------------

def download_pdf(filename: str, dest: Path, session: requests.Session) -> bool:
    """Pobiera regulamin jeśli nie istnieje lokalnie."""
    if dest.exists() and dest.stat().st_size > 0:
        log.debug(f"  Już istnieje: {dest.name}")
        return True

    url = f"{BASE}/{filename}"

    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/pdf"):
            dest.write_bytes(resp.content)
            log.info(f"  Pobrano: {dest.name} ({len(resp.content) / 1024:.0f} KB)")
            return True
        else:
            log.warning(f"  Brak/błąd dla {dest.name}: HTTP {resp.status_code}, type={resp.headers.get('content-type')}")
            return False
    except requests.RequestException as e:
        log.error(f"  Błąd pobierania {url}: {e}")
        return False


def download_all(session: requests.Session) -> list[tuple[Path, str, str, str]]:
    """
    Pobiera wszystkie wersje regulaminów.
    Zwraca listę: (path, valid_from, valid_to, description)
    """
    REG_DIR.mkdir(parents=True, exist_ok=True)

    targets = []
    all_regs = [("indeksy", r) for r in REGULATIONS_INDEKSY] + \
               [("ff", r) for r in REGULATIONS_FF]

    for category, (filename, valid_from, valid_to, desc) in all_regs:
        dest = REG_DIR / filename
        if download_pdf(filename, dest, session):
            targets.append((dest, valid_from, valid_to, f"[{category}] {desc}"))
        else:
            log.warning(f"  Pominięto: {filename}")

        if not dest.exists():
            time.sleep(DOWNLOAD_DELAY_SEC)

    log.info(f"Pobrano {len(targets)} regulaminów")
    return targets


# ---------------------------------------------------------------------------
# EXTRACTION
# ---------------------------------------------------------------------------

@dataclass
class ChangelogEntry:
    pdf_path: Path
    valid_from: str
    valid_to: str
    description: str
    full_text_pages: int = 0          # liczba stron PDF
    changelog_section: str = ""        # wyciągnięta sekcja zmian
    material_changes: list[str] = field(default_factory=list)  # zdania zawierające material keywords
    keyword_hits: dict[str, int] = field(default_factory=dict)  # słowo -> liczba wystąpień


def extract_changelog_section(text: str) -> str:
    """
    Próbuje wyciągnąć sekcję 'Załącznik / Historia zmian' z końca regulaminu.

    Zazwyczaj jest na końcu, w tabeli z kolumnami: Punkt | Treść zmiany | Data wejścia w życie.
    Strategia: znajdź pierwszy marker, weź wszystko od niego do końca.
    """
    # Szukaj markerów po kolei
    earliest_pos = len(text)
    found_marker = None

    for marker in CHANGELOG_SECTION_MARKERS:
        # Szukaj case-insensitive
        for match in re.finditer(re.escape(marker), text, re.IGNORECASE):
            # Bierzemy markery które są w drugiej połowie dokumentu (tam zwykle jest changelog)
            if match.start() > len(text) * 0.5 and match.start() < earliest_pos:
                earliest_pos = match.start()
                found_marker = marker
                break

    if found_marker:
        return text[earliest_pos:]
    return ""


def find_material_changes(text: str) -> tuple[list[str], dict[str, int]]:
    """
    Znajduje zdania zawierające słowa kluczowe sygnalizujące merytoryczne zmiany.

    Returns:
        (lista_zdan, dict_keyword_to_count)
    """
    # Podział na zdania (heurystyczny — kropka + spacja + duża litera)
    # Polska gramatyka: kropka po cyfrze może oznaczać liczebnik porządkowy, więc ostrożnie
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZŻŹĆŁŚĄĘŃÓ])', text)

    material_sentences = []
    keyword_counts = {}

    for sentence in sentences:
        # Pomijamy bardzo krótkie ("OK.", "Tak.")
        if len(sentence.strip()) < 30:
            continue
        # Pomijamy bardzo długie (>500 znaków) — to zwykle artefakty parsowania PDF
        if len(sentence) > 500:
            continue

        sentence_lower = sentence.lower()
        matched_keywords = []

        for keyword in MATERIAL_KEYWORDS:
            if re.search(keyword, sentence_lower, re.IGNORECASE):
                matched_keywords.append(keyword)
                keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

        if matched_keywords:
            # Dodajemy zdanie z listą trafionych słów kluczowych
            cleaned = re.sub(r'\s+', ' ', sentence.strip())
            material_sentences.append(f"  [{', '.join(matched_keywords[:3])}] {cleaned}")

    return material_sentences, keyword_counts


def process_regulation(pdf_path: Path, valid_from: str, valid_to: str, description: str) -> ChangelogEntry:
    """Wyciąga changelog i istotne zmiany z pojedynczego PDFa regulaminu."""
    log.info(f"Przetwarzam: {pdf_path.name}")

    entry = ChangelogEntry(
        pdf_path=pdf_path,
        valid_from=valid_from,
        valid_to=valid_to,
        description=description,
    )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            entry.full_text_pages = len(pdf.pages)
            full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

        if not full_text.strip():
            log.warning(f"  Pusty tekst w {pdf_path.name}")
            return entry

        # Wyciągnij sekcję zmian
        entry.changelog_section = extract_changelog_section(full_text)

        # Znajdź zdania merytoryczne — szukamy w sekcji changelog jeśli jest,
        # bo tam są opisy zmian. Jeśli nie ma — szukamy w całym tekście (mniej precyzyjnie).
        target_text = entry.changelog_section if entry.changelog_section else full_text

        entry.material_changes, entry.keyword_hits = find_material_changes(target_text)

        log.info(
            f"  {entry.full_text_pages} stron, "
            f"changelog: {len(entry.changelog_section)} znaków, "
            f"zmian merytorycznych: {len(entry.material_changes)}"
        )

    except Exception as e:
        log.error(f"  BŁĄD: {e}")

    return entry


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

def write_changelog_report(entries: list[ChangelogEntry], output_path: Path):
    """Pełny raport: wszystkie zmiany per wersja regulaminu."""
    lines = []
    lines.append("# Wyciąg zmian z regulaminów GPW Benchmark")
    lines.append("")
    lines.append(f"Liczba przetworzonych regulaminów: {len(entries)}")
    lines.append("")
    lines.append("Cel dokumentu: zidentyfikować zmiany merytoryczne w regulaminach")
    lines.append("Rodziny Indeksów Giełdowych oraz regulaminie ustalania liczby akcji")
    lines.append("w wolnym obrocie obowiązujące w okresie 2021-03 → 2025-09.")
    lines.append("")
    lines.append("Słowa kluczowe filtrowania: filtry kwalifikacyjne (MWO, DWO, kwartyl,")
    lines.append("dual-listing), mechanika rankingu (sT, sC, wagi 0.4/0.6), strefy bufora,")
    lines.append("limity udziału, wezwania na 100% akcji, fast-track, dopełnianie składu.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, entry in enumerate(entries, 1):
        lines.append(f"## {i}. {entry.pdf_path.name}")
        lines.append("")
        lines.append(f"**Obowiązywał**: {entry.valid_from} → {entry.valid_to}")
        lines.append("")
        lines.append(f"**Opis**: {entry.description}")
        lines.append("")
        lines.append(f"**Liczba stron**: {entry.full_text_pages}")
        lines.append("")
        lines.append(f"**Liczba zdań z merytorycznymi słowami kluczowymi**: {len(entry.material_changes)}")
        lines.append("")

        if entry.keyword_hits:
            lines.append("**Statystyki słów kluczowych** (top 10):")
            sorted_hits = sorted(entry.keyword_hits.items(), key=lambda x: -x[1])[:10]
            for keyword, count in sorted_hits:
                lines.append(f"- `{keyword}`: {count}")
            lines.append("")

        if entry.material_changes:
            lines.append("**Zdania merytoryczne z sekcji changelog**:")
            lines.append("")
            for sentence in entry.material_changes[:50]:  # max 50 per regulamin
                lines.append(sentence)
                lines.append("")
            if len(entry.material_changes) > 50:
                lines.append(f"... (i {len(entry.material_changes) - 50} kolejnych)")
                lines.append("")
        else:
            lines.append("_Brak zdań merytorycznych — możliwe że changelog nie został wykryty automatycznie._")
            lines.append("")

        lines.append("---")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Zapisano raport: {output_path}")


def write_summary_report(entries: list[ChangelogEntry], output_path: Path):
    """Skrót: które wersje regulaminu wprowadzały najwięcej zmian merytorycznych."""
    lines = []
    lines.append("# Podsumowanie zmian metodologicznych — GPW Benchmark 2021-2025")
    lines.append("")
    lines.append("Liczba zdań z merytorycznymi słowami kluczowymi w sekcji changelog")
    lines.append("każdego regulaminu (wskazuje na intensywność zmian merytorycznych).")
    lines.append("")
    lines.append("| Regulamin | Obowiązywał od | Stron | Zdań merytorycznych |")
    lines.append("|---|---|---:|---:|")

    for entry in entries:
        lines.append(
            f"| {entry.pdf_path.stem} | {entry.valid_from} | "
            f"{entry.full_text_pages} | {len(entry.material_changes)} |"
        )

    lines.append("")
    lines.append("## Mapowanie regulamin → rewizje w naszym datasecie")
    lines.append("")
    lines.append("| Rewizja | Aktywny regulamin |")
    lines.append("|---|---|")

    revisions = [
        "2021-03-19", "2021-06-18", "2021-09-17", "2021-12-17",
        "2022-03-18", "2022-06-17", "2022-09-16", "2022-12-16",
        "2023-03-17", "2023-06-16", "2023-09-15", "2023-12-15",
        "2024-03-15", "2024-06-21", "2024-09-20", "2024-12-20",
        "2025-03-21", "2025-06-20", "2025-09-19",
    ]

    for rev in revisions:
        active_reg = "?? (przed dostępną wersją)"
        for entry in entries:
            if entry.valid_from <= rev <= entry.valid_to:
                active_reg = entry.pdf_path.stem
                break
        lines.append(f"| {rev} | {active_reg} |")

    lines.append("")
    lines.append("## Sugerowany dalszy krok")
    lines.append("")
    lines.append("Otworzyć regulaminy z największą liczbą zdań merytorycznych i przeczytać")
    lines.append("ręcznie sekcję 'Załącznik' / 'Historia zmian' aby zidentyfikować konkretne")
    lines.append("zmiany merytoryczne (np. zmiana progów bufora, zmiana definicji MWO).")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Zapisano podsumowanie: {output_path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("KROK 1: Pobieranie regulaminów...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "GPW-Research-Bot/1.0 (academic research)",
    })
    targets = download_all(session)

    if not targets:
        log.error("Brak regulaminów do przetworzenia!")
        return

    log.info(f"\nKROK 2: Ekstrakcja zmian z {len(targets)} regulaminów...")
    entries = []
    for path, valid_from, valid_to, desc in targets:
        entry = process_regulation(path, valid_from, valid_to, desc)
        entries.append(entry)

    log.info(f"\nKROK 3: Generowanie raportów...")
    write_changelog_report(entries, OUTPUT_DIR / "regulation_changelog.md")
    write_summary_report(entries, OUTPUT_DIR / "regulation_summary.md")

    print("\n" + "=" * 70)
    print("PODSUMOWANIE")
    print("=" * 70)
    print(f"Przetworzono regulaminów:    {len(entries)}")
    print(f"Łącznie zdań merytorycznych: {sum(len(e.material_changes) for e in entries)}")
    print()
    print("Najwięcej zmian merytorycznych:")
    sorted_entries = sorted(entries, key=lambda e: -len(e.material_changes))[:5]
    for e in sorted_entries:
        print(f"  {e.pdf_path.stem:60s}  {len(e.material_changes):4d} zdań")

    print()
    print("Wyniki:")
    print(f"  {OUTPUT_DIR / 'regulation_changelog.md'}  — pełny raport")
    print(f"  {OUTPUT_DIR / 'regulation_summary.md'}    — podsumowanie")
    print()
    print("Następny krok: otworzyć raporty i przeczytać sekcje zmian")
    print("dla regulaminów z największą liczbą zdań merytorycznych.")


if __name__ == "__main__":
    main()
