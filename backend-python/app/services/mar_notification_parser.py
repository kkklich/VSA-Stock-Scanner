"""Read individual MAR notifications, retaining trade and publication dates separately.

The standard form repeats section 4 for each date/direction/venue. Its execution
rows are summed once; the aggregate row is only a fallback, never an extra trade.
Scans without a text layer remain unknown rather than inventing trade details.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

from pypdf import PdfReader

from app.models import InsiderTransactionItem

logger = logging.getLogger(__name__)

_NUMBER = r"\d+(?:[ \xa0.]\d{3})*(?:[.,]\d+)?"
_MONEY_VOLUME = re.compile(rf"({_NUMBER})\s*(PLN|EUR|USD|GBP|zł)\s+({_NUMBER})", re.IGNORECASE)
_DATE = re.compile(
    r"\b(\d{4})\s*[-./]\s*(\d{2})\s*[-./]\s*(\d{2})\b"
    r"|\b(\d{2})\s*[-./]\s*(\d{2})\s*[-./]\s*(\d{4})\b"
)


def extract_trade_date(text: str) -> date | None:
    match = re.search(r"dat[ayę]\s+transakcji\s*[:\-]?\s*(.{0,90})", text, re.I)
    if not match:
        return None
    dates = set()
    for value in _DATE.finditer(match.group(1)):
        y, m, d = value.group(1, 2, 3) if value.group(1) else value.group(6, 5, 4)
        try:
            dates.add(date(int(y), int(m), int(d)))
        except ValueError:
            return None
    return next(iter(dates)) if len(dates) == 1 else None


def _decimal(raw: str) -> Decimal:
    raw = re.sub(r"[\s\xa0]", "", raw)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    return Decimal(raw)


def _field(text: str, label: str, end: str) -> str | None:
    match = re.search(rf"(?:{label})\s*[:\-]?\s*(.*?)(?={end}|$)", text, re.I | re.S)
    if not match:
        return None
    return match.group(1).strip() or None


def _executions(text: str) -> tuple[int | None, float | None, str | None, float | None]:
    rows = []
    for match in _MONEY_VOLUME.finditer(text):
        try:
            price, volume = _decimal(match[1]), _decimal(match[3])
        except InvalidOperation:
            continue
        if price >= 0 and 0 < volume < 1_000_000_000 and volume == int(volume):
            rows.append((price, int(volume), match[2].upper().replace("ZŁ", "PLN")))
    if not rows or len({row[2] for row in rows}) != 1:
        return None, None, None, None
    shares = sum(row[1] for row in rows)
    value = sum((row[0] * row[1] for row in rows), Decimal(0))
    return shares, round(float(value / shares), 4), rows[0][2], round(float(value), 2)


def parse_mar_text(text: str, stub: dict) -> list[InsiderTransactionItem]:
    """Parse text extracted from one or several standard Polish MAR forms."""
    from app.services.espi_client import extract_role, parse_espi_direction

    items = []
    # Preserve line boundaries for extraction, normalise only horizontal whitespace.
    text = re.sub(r"[^\S\n]+", " ", text)
    notices = re.split(r"(?=1\s+Dane osoby)", text, flags=re.I)
    for notice in notices:
        name = _field(notice, r"Nazwa\s*/\s*Nazwisko", r"\s*2\s+Pow[oó]d")
        if name:
            name = re.sub(r"\s+", " ", name)
        status = _field(
            notice,
            r"Stanowisko\s*/\s*status",
            r"\s*b\)\s*(?:Pierwotne|Powiadomienie)|\s*3\s+Dane emitenta",
        )
        if status and re.search(r"blisko zwi[aą]zan", status, re.I):
            role = "Osoba blisko związana"
        else:
            role = extract_role(status or notice)
        for block in re.finditer(
            r"Rodzaj transakcji\s*(.*?)(?=Rodzaj transakcji|$)", notice, re.I | re.S
        ):
            details = block.group(1)
            direction = _field(details, r"^", r"\s*c\)\s*Cena|Cena i wolumen")
            tx_type, is_open = parse_espi_direction(direction or "")
            # Pledges, options and gifts are not cash purchases.
            if re.search(r"zastaw|zabezpiecz", direction or "", re.I):
                tx_type, is_open = "other", False
            venue = _field(details, r"Miejsce transakcji", r"\n\s*\*|\n\s*Strona")
            if venue and re.search(r"poza|OTC", venue, re.I):
                is_open = False
            trade_date = extract_trade_date(re.sub(r"\s+", " ", details))
            # No reliable date means this form cannot be represented as a dated trade.
            if trade_date is None:
                continue
            executions = _field(details, r"Cena i wolumen", r"\s*d\)|Informacje zbiorcze")
            shares, price, currency, value = _executions(executions or "")
            if shares is None:
                aggregate = _field(details, r"Informacje zbiorcze", r"\s*e\)|Data transakcji") or ""
                shares, price, currency, value = _executions(aggregate)
                # Common form layout: aggregate volume, followed by average price.
                if shares is None:
                    aggregate = re.sub(r"Łączny wolumen|Cena|[-–]", " ", aggregate, flags=re.I)
                    match = re.search(
                        rf"({_NUMBER})\s+({_NUMBER})\s*(PLN|EUR|USD|GBP)", aggregate, re.I
                    )
                    if match:
                        shares, price, currency, value = _executions(
                            f"{match[2]} {match[3]} {match[1]}"
                        )
            items.append(
                InsiderTransactionItem(
                    trade_date=trade_date,
                    publication_date=stub["publication_date"],
                    insider_name=name,
                    role=role,
                    transaction_type=tx_type,
                    is_open_market=is_open,
                    shares=shares,
                    price=price,
                    currency=currency or "PLN",
                    value=value,
                    source="espi",
                    source_url=stub.get("url"),
                    notes=stub.get("title"),
                )
            )
    return items


def parse_mar_pdf(content: bytes, stub: dict) -> list[InsiderTransactionItem]:
    try:
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) > 50:
            return []
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return parse_mar_text(text, stub)
    except Exception:
        logger.warning("Could not read MAR attachment for %s", stub.get("url"), exc_info=True)
        return []
