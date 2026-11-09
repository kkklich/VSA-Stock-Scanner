"""Read Polish ESPI/MAR insider trades without running the API or a database.

From the repository root::

    backend-python/.venv/Scripts/python.exe backend-python/scripts/espi_insiders.py \
        --ticker CDR --html insiderzy.html --open

Local notification PDF (the attachment, not just the ESPI report cover)::

    python -m scripts.espi_insiders --pdf powiadomienie.pdf --published 2026-11-05

The live mode searches recent GPW reports, not the issuer's complete history.
Unknown quantities remain unknown in both individual rows and person totals.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import webbrowser
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

# Also allow a direct invocation from the repository root, on Windows or Unix.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import InsiderTransactionItem
from app.services.espi_client import EspiClient
from app.services.mar_notification_parser import parse_mar_pdf

COMPANIES_PATH = Path(__file__).resolve().parents[1] / "app/data/gpw-companies.json"
KINDS = {
    "buy": "Zakup",
    "sell": "Sprzedaż",
    "gift": "Darowizna",
    "grant": "Przyznanie",
    "option": "Opcje",
    "buyback": "Skup własny",
    "other": "Inna / nieustalona",
}
DETAIL_HEADERS = (
    "Data transakcji",
    "Publikacja",
    "Osoba / podmiot",
    "Funkcja",
    "Rodzaj",
    "Liczba akcji",
    "Cena za akcję",
    "Waluta",
    "Wartość",
)
SUMMARY_HEADERS = (
    "Osoba / podmiot",
    "Waluta",
    "Kupione akcje",
    "Sprzedane akcje",
    "Bilans akcji",
    "Wartość zakupów",
    "Wartość sprzedaży",
)


@dataclass
class InsiderTotals:
    name: str
    currency: str
    buy_shares: int | None = 0
    sell_shares: int | None = 0
    buy_value: Decimal | None = Decimal(0)
    sell_value: Decimal | None = Decimal(0)

    @property
    def net_shares(self) -> int | None:
        if self.buy_shares is None or self.sell_shares is None:
            return None
        return self.buy_shares - self.sell_shares


def transaction_value(tx: InsiderTransactionItem) -> Decimal | None:
    if tx.value is not None:
        return Decimal(str(tx.value))
    if tx.shares is not None and tx.price is not None:
        return Decimal(tx.shares) * Decimal(str(tx.price))
    return None


def summarize_transactions(items: list[InsiderTransactionItem]) -> list[InsiderTotals]:
    """Sum buy/sell only, keeping currencies and unidentified people separate.

    A missing quantity makes that side's total unknown, never a misleading zero.
    Non-market purchases/sales are included; gifts/grants/options are not.
    """
    groups: dict[tuple[str, str], InsiderTotals] = {}
    for tx in items:
        name = " ".join((tx.insider_name or "").split())
        if not name or tx.transaction_type not in ("buy", "sell"):
            continue
        currency = (tx.currency or "nieznana").upper()
        key = (name.casefold(), currency)
        group = groups.setdefault(key, InsiderTotals(name=name, currency=currency))
        side = tx.transaction_type
        known_shares = getattr(group, f"{side}_shares")
        setattr(
            group,
            f"{side}_shares",
            None if known_shares is None or tx.shares is None else known_shares + tx.shares,
        )
        known_value, value = getattr(group, f"{side}_value"), transaction_value(tx)
        setattr(
            group,
            f"{side}_value",
            None if known_value is None or value is None else known_value + value,
        )
    return sorted(groups.values(), key=lambda row: (row.name.casefold(), row.currency))


def number(value: int | float | Decimal | None, decimals: int = 0) -> str:
    if value is None:
        return "brak danych"
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def detail_rows(items: list[InsiderTransactionItem]) -> list[list[str]]:
    return [
        [
            tx.trade_date.isoformat() if tx.trade_date else "brak danych",
            tx.publication_date.isoformat(),
            tx.insider_name or "brak danych",
            tx.role or "brak danych",
            KINDS.get(tx.transaction_type, "Inna / nieustalona"),
            number(tx.shares),
            number(tx.price, 4),
            tx.currency or "brak danych",
            number(transaction_value(tx), 2),
        ]
        for tx in items
    ]


def summary_rows(items: list[InsiderTransactionItem]) -> list[list[str]]:
    return [
        [
            row.name,
            row.currency,
            number(row.buy_shares),
            number(row.sell_shares),
            number(row.net_shares),
            number(row.buy_value, 2),
            number(row.sell_value, 2),
        ]
        for row in summarize_transactions(items)
    ]


def text_table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    clean = [[" ".join(value.split()) for value in row] for row in [list(headers), *rows]]
    widths = [max(len(row[i]) for row in clean) for i in range(len(headers))]
    lines = [
        " | ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))
        for row in clean
    ]
    lines.insert(1, "-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def _safe_link(url: str | None) -> str:
    if not url or urlsplit(url).scheme not in ("https", "http", "file"):
        return "brak danych"
    return f'<a href="{escape(url, quote=True)}">Raport źródłowy</a>'


def render_html(
    title: str,
    items: list[InsiderTransactionItem],
    warnings: list[str],
    scope: str,
) -> str:
    def table(
        headers: tuple[str, ...],
        rows: list[list[str]],
        sources: list[str | None] | None = None,
    ) -> str:
        head = "".join(f"<th>{escape(cell)}</th>" for cell in headers)
        body = "".join(
            "<tr>"
            + "".join(f"<td>{escape(cell)}</td>" for cell in row)
            + (f"<td>{_safe_link(sources[i])}</td>" if sources is not None else "")
            + "</tr>"
            for i, row in enumerate(rows)
        )
        return (
            f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}'
            "</tbody></table></div>"
        )

    details = table(
        (*DETAIL_HEADERS, "Źródło"),
        detail_rows(items),
        [tx.source_url for tx in items],
    )
    notes = "".join(f"<li>{escape(note)}</li>" for note in warnings)
    empty = "<p>Nie uzyskano rekordów. Sprawdź zakres oraz uwagi poniżej.</p>" if not items else ""
    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1500px;margin:36px auto;padding:0 24px;
color:#172b45;background:#f5f7fa}}h1{{font-size:28px}}h2{{margin-top:32px;font-size:21px}}
.scroll{{overflow-x:auto;background:white;border:1px solid #dce2eb;border-radius:8px}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;text-align:left;
border-bottom:1px solid #e5e9f0;white-space:nowrap}}th{{background:#eaf0f7}}
a{{color:#155bb0}}.notes{{background:#fff7df;padding:16px 24px;border-radius:8px}}
</style></head><body><h1>{escape(title)}</h1><p>{escape(scope)}</p>{empty}
<h2>Transakcje</h2>{details}<h2>Zakupy i sprzedaż według osoby</h2>
{table(SUMMARY_HEADERS, summary_rows(items))}
<p>Bilans = kupione − sprzedane akcje w odczytanych rekordach. Nie jest stanem posiadania.
Darowizny, przyznania akcji i opcje nie wchodzą do bilansu. Waluty są liczone osobno.
Brak danych oznacza, że odczyt nie pozwala ustalić danej wartości.</p>
<div class="notes"><strong>Uwagi do odczytu</strong><ul>{notes}</ul></div>
</body></html>"""


def write_csv(path: Path, items: list[InsiderTransactionItem]) -> None:
    """Excel-friendly Polish CSV, with raw numeric precision and source links."""

    def cell(value: object) -> object:
        if value is None:
            return ""
        if isinstance(value, (float, Decimal)):
            return str(value).replace(".", ",")
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow((*DETAIL_HEADERS, "Źródło"))
        for tx in items:
            writer.writerow(
                [
                    cell(value)
                    for value in (
                        tx.trade_date.isoformat() if tx.trade_date else None,
                        tx.publication_date.isoformat(),
                        tx.insider_name,
                        tx.role,
                        KINDS.get(tx.transaction_type, "Inna / nieustalona"),
                        tx.shares,
                        tx.price,
                        tx.currency,
                        transaction_value(tx),
                        tx.source_url,
                    )
                ]
            )


def resolve_company(ticker: str, company_name: str | None = None) -> tuple[str, str]:
    ticker = ticker.strip().upper()
    for suffix in (".WA", ".PL"):
        ticker = ticker.removesuffix(suffix)
    if not ticker or not ticker.isalnum():
        raise ValueError("Podaj ticker polskiej spółki, np. CDR, PKO lub CBF.")
    if company_name:
        return ticker, company_name.strip()
    companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    for company in companies:
        if company["ticker"].upper() == ticker:
            return ticker, company["name"]
    raise ValueError(f'Nie znam spółki {ticker}. Dodaj --company "Pełna nazwa spółki".')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Odczyt transakcji insiderów z ESPI / MAR (GPW).")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticker", help="Ticker GPW, np. CDR, PKO, CBF; pobiera raporty z gpw.pl.")
    source.add_argument("--pdf", type=Path, help="Lokalny PDF z powiadomieniem MAR art. 19.")
    parser.add_argument("--company", help="Nazwa emitenta do wyszukania (z --ticker).")
    parser.add_argument(
        "--published",
        type=date.fromisoformat,
        help="Data publikacji ESPI YYYY-MM-DD; wymagana z --pdf.",
    )
    parser.add_argument("--insider", help="Pokaż tylko osoby/podmioty zawierające podany tekst.")
    parser.add_argument(
        "--from",
        dest="from_date",
        type=date.fromisoformat,
        help="Data transakcji od YYYY-MM-DD (włącznie).",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=date.fromisoformat,
        help="Data transakcji do YYYY-MM-DD (włącznie).",
    )
    parser.add_argument("--limit", type=int, default=50, help="Limit wyszukanych raportów (1–500).")
    parser.add_argument(
        "--reports", type=int, default=15, help="Maksymalna liczba pobranych raportów MAR (1–100)."
    )
    parser.add_argument("--csv", type=Path, help="Zapis transakcji do pliku CSV dla Excela.")
    parser.add_argument("--html", type=Path, help="Zapis czytelnego raportu HTML.")
    parser.add_argument("--open", action="store_true", help="Otwórz raport --html w przeglądarce.")
    return parser


async def load_transactions(
    args: argparse.Namespace,
) -> tuple[str, list[InsiderTransactionItem], list[str], str]:
    if args.pdf:
        if args.pdf.stat().st_size > 10_000_000:
            raise ValueError("PDF jest zbyt duży (maksymalnie 10 MB).")
        stub = {
            "publication_date": args.published,
            "url": args.pdf.resolve().as_uri(),
            "title": args.pdf.name,
        }
        items = parse_mar_pdf(args.pdf.read_bytes(), stub)
        warnings = (
            []
            if items
            else [
                "Nie odczytano transakcji akcji z PDF. Sprawdź, czy to powiadomienie MAR, "
                "czy zawiera tekst oraz datę transakcji. Skany wymagają OCR."
            ]
        )
        return f"Insiderzy GPW — {args.pdf.name}", items, warnings, "Źródło: lokalny PDF MAR."
    ticker, company = resolve_company(args.ticker, args.company)
    print(f"Pobieranie raportów ESPI: {company} ({ticker})…", file=sys.stderr)
    client = EspiClient()
    items = await client.get_company_insider_transactions(
        company,
        ticker,
        limit=args.limit,
        report_limit=args.reports,
    )
    scope = (
        f"Źródło: gpw.pl. Wyszukiwanie do {args.limit} ostatnich raportów emitenta; "
        f"odczyt do {args.reports} raportów MAR. To nie jest pełna historia transakcji."
    )
    return f"Insiderzy GPW — {company} ({ticker})", items, list(client.warnings), scope


def main(argv: list[str] | None = None) -> int:
    # Keep Polish output usable in older Windows consoles as well.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.pdf and not args.published:
        parser.error("Przy --pdf podaj --published YYYY-MM-DD (datę publikacji raportu ESPI).")
    if args.pdf and args.company or args.ticker and args.published:
        parser.error("--company wymaga --ticker, a --published wymaga --pdf.")
    if not 1 <= args.limit <= 500 or not 1 <= args.reports <= 100:
        parser.error("--limit musi wynosić 1–500, a --reports 1–100.")
    if args.from_date and args.to_date and args.from_date > args.to_date:
        parser.error("Data --from nie może być późniejsza niż --to.")
    if args.open and not args.html:
        parser.error("--open wymaga --html z nazwą pliku.")
    if args.csv and args.html and args.csv.resolve() == args.html.resolve():
        parser.error("Pliki --csv i --html muszą mieć różne nazwy.")
    if args.pdf and any(
        path and path.resolve() == args.pdf.resolve() for path in (args.csv, args.html)
    ):
        parser.error("Plik wynikowy nie może nadpisać źródłowego PDF-a.")
    try:
        title, items, warnings, scope = asyncio.run(load_transactions(args))
        load_failed = not items and bool(warnings)
        if args.insider:
            needle = args.insider.casefold()
            items = [tx for tx in items if needle in (tx.insider_name or "").casefold()]
            scope += f" Filtr osoby/podmiotu: {args.insider}."
        if args.from_date or args.to_date:
            undated = sum(tx.trade_date is None for tx in items)
            items = [
                tx
                for tx in items
                if tx.trade_date is not None
                and (not args.from_date or tx.trade_date >= args.from_date)
                and (not args.to_date or tx.trade_date <= args.to_date)
            ]
            scope += (
                f" Daty transakcji: {args.from_date or 'bez początku'} — "
                f"{args.to_date or 'bez końca'}."
            )
            if undated:
                warnings.append(
                    f"Filtr dat pominął {undated} rekordów bez ustalonej daty transakcji."
                )
        items.sort(key=lambda tx: (tx.publication_date, tx.trade_date or date.min), reverse=True)
        if any(tx.shares is None or tx.price is None for tx in items):
            warnings.append(
                "Część rekordów nie ma liczby akcji lub ceny. Nie uzupełniono ich zerami."
            )
        if any(not tx.insider_name for tx in items):
            warnings.append(
                "Rekordy bez rozpoznanej osoby są w tabeli, ale nie w podsumowaniu osób."
            )
        warnings.append(
            "Bilans dotyczy tylko odczytanych zakupów i sprzedaży; nie oznacza stanu posiadania. "
            "Korekty i ponownie opublikowane powiadomienia należy sprawdzić w źródłowych raportach."
        )
        print(f"\n{title}\n{scope}\n")
        if items:
            print(text_table(DETAIL_HEADERS, detail_rows(items)))
            print("\nZakupy i sprzedaż według osoby (waluty osobno):")
            print(text_table(SUMMARY_HEADERS, summary_rows(items)))
            sources = dict.fromkeys(tx.source_url for tx in items if tx.source_url)
            print("\nŹródła:\n" + "\n".join(sources))
        else:
            print(
                "Nie uzyskano rekordów dla tych ustawień. "
                "Nie jest to potwierdzenie braku transakcji."
            )
        print("\nUwagi:\n" + "\n".join(f"- {note}" for note in warnings))
        if args.csv:
            write_csv(args.csv, items)
            print(f"\nCSV: {args.csv.resolve()}")
        if args.html:
            args.html.write_text(render_html(title, items, warnings, scope), encoding="utf-8")
            print(f"\nRaport HTML: {args.html.resolve()}")
            if args.open:
                webbrowser.open(args.html.resolve().as_uri())
        return 1 if load_failed else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
