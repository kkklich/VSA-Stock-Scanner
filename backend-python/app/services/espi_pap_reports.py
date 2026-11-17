"""Find the PAP MediaRoom copy of an ESPI report already identified on GPW."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import NamedTuple
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from app.services.cache import TTLCache

PAP_ORIGIN = "pap-mediaroom.pl"
_ARCHIVE_URL = f"https://{PAP_ORIGIN}/zrodlo/ESPI"
_REPORT_TITLE = re.compile(r"^.+?\s+\((\d+)/(\d{4})\)\s+(.+)$", re.S)
_LIST_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4}),")


class PapReport(NamedTuple):
    published: date
    title: str
    url: str


class PapReportCopy(NamedTuple):
    attachments: tuple[str, ...]
    text: str


def _title_key(title: str) -> str:
    return " ".join(re.findall(r"\w+", title.casefold()))


def _pap_url(href: str, path_prefix: str) -> str | None:
    url = urljoin(_ARCHIVE_URL, href)
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.netloc == PAP_ORIGIN and parts.path.startswith(
        path_prefix
    ):
        return url
    return None


def parse_pap_archive(html: str) -> tuple[list[PapReport], int]:
    soup = BeautifulSoup(html, "html.parser")
    reports = []
    for row in soup.select("li.news > .newsWrapper"):
        if not row.select_one('.source a[href="/zrodlo/ESPI"]'):
            continue
        link = row.select_one(":scope > a[href]")
        title = row.select_one(".title")
        published = row.select_one(".moreInfo .date")
        if not (link and title and published):
            continue
        url = _pap_url(str(link["href"]), "/")
        match = _LIST_DATE.match(published.get_text(strip=True))
        if url and match:
            try:
                day = date(int(match[3]), int(match[2]), int(match[1]))
            except ValueError:
                continue
            reports.append(PapReport(day, title.get_text(" ", strip=True), url))
    pager = soup.select(".pagination a[href]")
    pages = [
        number
        for link in pager
        for number in parse_qs(urlsplit(str(link["href"])).query).get("page", [])
        if number.isascii() and number.isdecimal()
    ]
    return reports, max(map(int, pages), default=0)


def _parse_pap_report(html: str, isin: str, number: str) -> PapReportCopy | None:
    article = BeautifulSoup(html, "html.parser").select_one("article.node--view-mode-full")
    if article is None:
        return None
    tags = [link.get_text(strip=True) for link in article.select(".tags a")]
    if number not in tags or not any(isin in tag.split("-") for tag in tags):
        return None
    attachments = tuple(dict.fromkeys(
        url
        for link in article.select(".attachments a[href]")
        if (url := _pap_url(str(link["href"]), "/sites/default/files/attachments/"))
        and urlsplit(url).path.casefold().endswith(".pdf")
    ))
    if not attachments:
        return None
    return PapReportCopy(attachments, article.get_text(" ", strip=True))


# Archive pages are shared by stock requests and the scheduled market refresh.
_archive_pages: TTLCache[tuple[list[PapReport], int]] = TTLCache(max_entries=512)
_report_copies: TTLCache[PapReportCopy] = TTLCache(max_entries=1024)


async def find_pap_report(
    stub: dict, get_html: Callable[[str], Awaitable[str | None]]
) -> PapReportCopy | None:
    isin, number = stub.get("isin"), stub.get("report_number")
    if not isin or not number:
        return None
    day = stub["publication_date"]
    key = f"{isin}:{number}:{day}:{stub['title']}"
    cached = _report_copies.get(key)
    if cached is not None:
        return cached

    async def archive(page: int) -> tuple[list[PapReport], int]:
        key = str(page)
        cached = _archive_pages.get(key)
        if cached is not None:
            return cached
        html = await get_html(f"{_ARCHIVE_URL}?page={page}")
        parsed = parse_pap_archive(html or "")
        if parsed[0]:
            _archive_pages.set(key, parsed, 900)
        return parsed

    first, last_page = await archive(0)
    if not first or day > first[0].published:
        return None
    # Find the first page whose oldest report is on or before the target day.
    low, high = 0, last_page
    while low < high:
        middle = (low + high) // 2
        reports, _ = await archive(middle)
        if not reports:
            return None
        if reports[-1].published > day:
            low = middle + 1
        else:
            high = middle

    title_key = _title_key(stub["title"])
    for page in range(low, last_page + 1):
        reports, _ = await archive(page)
        if not reports or reports[0].published < day:
            break
        for report in reports:
            if report.published != day or not (match := _REPORT_TITLE.match(report.title)):
                continue
            if f"{int(match[1])}/{match[2]}" != number or _title_key(match[3]) != title_key:
                continue
            html = await get_html(report.url)
            if match_report := _parse_pap_report(html or "", isin, number):
                _report_copies.set(key, match_report, 3600)
                return match_report
        if reports[-1].published < day:
            break
    return None
