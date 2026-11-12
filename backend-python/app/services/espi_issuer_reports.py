"""Match a GPW notice to the same disclosure on the issuer's investor site."""

from __future__ import annotations

import re
from datetime import date
from itertools import pairwise
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

_REPORT_HEADING = re.compile(r"Raport\s+bieżący\s+(\d+)/(\d{4})", re.I)
_REPORT_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MAR19 = re.compile(r"\bart\.?\s*19\b", re.I)


def _report_number(text: str) -> str | None:
    match = _REPORT_HEADING.fullmatch(text)
    return f"{int(match[1])}/{match[2]}" if match else None


def parse_issuer_report_candidates(
    index_html: str, index_url: str
) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Index cyber_Folks archive detail pages and their associated PDF links."""
    soup = BeautifulSoup(index_html, "html.parser")
    origin = urlsplit(index_url).netloc
    reports: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for row in soup.select(".reports__result"):
        heading = row.select_one("a.reports__result-title[href]")
        if heading is None:
            continue
        number = _report_number(heading.get_text(" ", strip=True))
        if number is None:
            continue
        detail_url = urljoin(index_url, str(heading["href"]))
        detail = urlsplit(detail_url)
        if detail.scheme != "https" or detail.netloc != origin:
            continue
        pdfs: dict[str, None] = {}
        for link in row.select(".reports__result-files a[href]"):
            pdf_url = urljoin(index_url, str(link["href"]))
            pdf = urlsplit(pdf_url)
            if pdf.scheme == "https" and pdf.netloc == origin and pdf.path.lower().endswith(".pdf"):
                pdfs[pdf_url] = None
        if pdfs:
            candidate = (detail_url, tuple(pdfs))
            candidates = reports.setdefault(number, [])
            if candidate not in candidates:
                candidates.append(candidate)
    return reports


def issuer_report_matches(detail_html: str, stub: dict) -> bool:
    """Confirm the report number, publication date, and MAR disclosure."""
    soup = BeautifulSoup(detail_html, "html.parser")
    main = soup.find("main")
    if main is None:
        return False
    heading = main.find("h2", string=_REPORT_HEADING)
    if heading is None or _report_number(heading.get_text(" ", strip=True)) != stub.get(
        "report_number"
    ):
        return False
    published = heading.find_next("p")
    match = _REPORT_DATE.match(published.get_text(" ", strip=True)) if published else None
    if match is None:
        return False
    try:
        published_on = date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        return False
    if published_on != stub["publication_date"]:
        return False

    # Some 2025 issuer pages display an unrelated subject while the report
    # number, date, and Article 19 legal basis agree with the GPW disclosure.
    fields = [node.get_text(" ", strip=True) for node in main.select("p, h3, h4, h5, h6")]
    nonempty_fields = [field for field in fields if field]
    title = " ".join(stub["title"].casefold().split())
    for label, value in pairwise(nonempty_fields):
        label = label.rstrip(":").strip().casefold()
        if label == "temat" and " ".join(value.casefold().split()) == title:
            return True
        if label == "podstawa prawna" and _MAR19.search(value):
            return True
    return False
