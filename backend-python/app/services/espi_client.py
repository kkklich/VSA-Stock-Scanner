"""GPW ESPI client — fetches MAR Art. 19 insider transaction reports for Polish stocks.

Yahoo Finance provides zero insider transaction rows for GPW tickers. Polish
companies publish insider notifications under Art. 19 of the Market Abuse
Regulation (MAR) as ESPI current reports on the Warsaw Stock Exchange (gpw.pl).

This module queries the official GPW ESPI search endpoint (`ajaxindex.php`),
filters for MAR Art. 19 notifications (excluding Art. 69 major-shareholder
threshold reports), and parses the report text (`espi-ebi-report?geru_id=...`)
for the publication date, manager role, trade direction (buy/sell), volume,
price, and direct source URL.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.models import InsiderTransactionItem
from app.services.cache import TTLCache
from app.services.mar_notification_parser import parse_mar_pdf

logger = logging.getLogger(__name__)

_GPW_BASE_URL = "https://www.gpw.pl"
_GPW_AJAX_URL = f"{_GPW_BASE_URL}/ajaxindex.php"
# Verified issuer mirrors, used only for the identical attachment named by GPW.
_ISSUER_REPORT_INDEXES = {
    "cyber_folks": "https://investors.cyberfolks.pl/raporty/",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.gpw.pl/komunikaty",
}

# Match MAR Art. 19 titles & exclude Art. 69 (threshold crossing)
_MAR19_PATTERNS = (
    re.compile(r"art\.?\s*19\b", re.IGNORECASE),
    re.compile(r"obowi[aą]zki\s+zarz[aą]dcze", re.IGNORECASE),
    re.compile(r"os[oó]b\s+zarz[aą]dzaj[aą]cych", re.IGNORECASE),
    re.compile(r"transakcj[a-ząćęłńóśźż]+\s+na\s+(?:akcjach|instrumentach)", re.IGNORECASE),
    re.compile(r"nabyci[eu]\s+akcji\s+przez\s+(?:cz[łl]onka|prezesa|osob[eę])", re.IGNORECASE),
    re.compile(r"zbyci[eu]\s+akcji\s+przez\s+(?:cz[łl]onka|prezesa|osob[eę])", re.IGNORECASE),
)

_ART69_PATTERNS = (
    re.compile(r"art\.?\s*69\b", re.IGNORECASE),
    re.compile(r"art\.?\s*70\b", re.IGNORECASE),
    re.compile(r"og[oó]lnej\s+liczby\s+g[łl]os[oó]w", re.IGNORECASE),
)

_GERU_ID_RE = re.compile(r"geru_id=(\d+)")
_DATE_DMY_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_DATE_YMD_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

_ROLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"wiceprezes[a-z]*\s+zarz[aą]du", re.IGNORECASE), "Wiceprezes Zarządu"),
    (re.compile(r"\bprezes[a-z]*\s+zarz[aą]du", re.IGNORECASE), "Prezes Zarządu"),
    (re.compile(r"cz[łl]on(?:ek|ka|kiem|kowi)\s+zarz[aą]du", re.IGNORECASE), "Członek Zarządu"),
    (
        re.compile(r"przewodnicz[aą]c[a-z]*\s+rady\s+nadzorczej", re.IGNORECASE),
        "Przewodniczący Rady Nadzorczej",
    ),
    (
        re.compile(r"cz[łl]on(?:ek|ka|kiem|kowi)\s+rady\s+nadzorczej", re.IGNORECASE),
        "Członek Rady Nadzorczej",
    ),
    (re.compile(r"prokurent[a-z]*", re.IGNORECASE), "Prokurent"),
    (
        re.compile(r"dyrektor[a-z]*\s+zarz[aą]dzaj[aą]c[a-z]*", re.IGNORECASE),
        "Dyrektor Zarządzający",
    ),
    (
        re.compile(r"fundacj[a-z]+\s+rodzinn[a-z]+", re.IGNORECASE),
        "Fundacja Rodzinna (podmiot powiązany)",
    ),
    (
        re.compile(r"(?:osob[a-ząćęłńóśźż]+|podmiot[a-z]*)\s+blisko\s+zwi[aą]zan", re.IGNORECASE),
        "Osoba blisko związana",
    ),
)

_SHARES_RE = re.compile(
    r"(?:liczba|wolumen|naby[łl][ao]?|zby[łl][ao]?|kupno|sprzeda[żz]|obejmuj[aą]c[a-z]*)\s*"
    r"(?:[łl][aą]cznie\s*)?(?:akcji\s*)?[:=-]?\s*"
    r"(\d{1,3}(?:[\s\xa0.]\d{3})+|\d+)\s*(?:sztuk|szt\.?|akcji)",
    re.IGNORECASE,
)

_PRICE_PLN_RE = re.compile(
    r"(?:po\s+cenie|cena(?:\s+jednostkowa|\s+średnia)?(?:\s+wynios[łl]a|\s+akcji)?)\s*[:=-]?\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:PLN|z[łl])",
    re.IGNORECASE,
)


def is_mar19_title(title: str) -> bool:
    """Return True if an ESPI report title indicates a MAR Art. 19 insider notice."""
    if not title:
        return False
    if any(p.search(title) for p in _ART69_PATTERNS):
        return False
    return any(p.search(title) for p in _MAR19_PATTERNS)


def parse_espi_direction(text: str, attachments_text: str = "") -> tuple[str, bool]:
    """Classify an ESPI MAR 19 report text into (transaction_type, is_open_market)."""
    combined = f"{text} {attachments_text}".lower()

    for keywords, kind in (
        (("darowizn", "gift"), "gift"),
        (("skup akcji własnych", "buy-back", "buyback"), "buyback"),
        (("warrant", "opcji", "opcja", "option"), "option"),
    ):
        if any(word in combined for word in keywords):
            return kind, False

    # Non-open-market indicators (incentive plans, options, free grants, gifts)
    if any(
        w in combined
        for w in (
            "program motywacyjny",
            "programu motywacyjnego",
            "darowizn",
            "nieodpłatn",
            "warrant",
            "opcji menedżerskich",
            "skup akcji własnych",
            "buy-back",
            "buyback",
        )
    ):
        return ("grant", False)

    has_buy = any(
        re.search(pat, combined)
        for pat in (
            r"\bnabyci[aemou]\b",
            r"\bnaby[łl][ao]?\b",
            r"\bkupn[ao]\b",
            r"\bzakup[u]?\b",
            r"\bpurchase\b",
            r"\bacquisition\b",
        )
    )
    has_sell = any(
        re.search(pat, combined)
        for pat in (
            r"\bzbyci[aemou]\b",
            r"\bzby[łl][ao]?\b",
            r"\bsprzeda[żz][yą]?\b",
            r"\bsale\b",
            r"\bdisposal\b",
        )
    )

    if has_buy and not has_sell:
        return ("buy", True)
    if has_sell and not has_buy:
        return ("sell", True)
    # A notice may cover both directions. Never guess from word order.
    return ("other", False)


def extract_role(text: str) -> str:
    """Extract the insider's role from Polish ESPI report text."""
    for pattern, label in _ROLE_PATTERNS:
        if pattern.search(text):
            return label
    return "Osoba zarządzająca (MAR art. 19)"


def extract_shares_and_price(text: str) -> tuple[int | None, float | None]:
    """Extract share count and price per share when stated in the ESPI body."""
    shares: int | None = None
    price: float | None = None

    m_sh = _SHARES_RE.search(text)
    if m_sh:
        raw_s = re.sub(r"[\s\xa0.]", "", m_sh.group(1))
        try:
            val = int(raw_s)
            if 0 < val < 1_000_000_000:
                shares = val
        except ValueError:
            pass

    m_pr = _PRICE_PLN_RE.search(text)
    if m_pr:
        raw_p = m_pr.group(1).replace(",", ".")
        try:
            pval = float(raw_p)
            if pval > 0:
                price = round(pval, 4)
        except ValueError:
            pass

    return shares, price


def parse_espi_list_html(html: str, target_company_hint: str = "") -> list[dict]:
    """Parse GPW ajaxindex.php HTML list into candidate MAR 19 report stubs."""
    if not html or not html.strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    hint_lower = target_company_hint.strip().lower()

    for li in soup.find_all("li"):
        date_span = li.find("span", class_="date")
        name_strong = li.find("strong", class_="name")
        title_p = li.find("p")
        link_a = li.find("a", href=_GERU_ID_RE)

        if not link_a:
            continue

        href = str(link_a.get("href") or "")
        m_id = _GERU_ID_RE.search(href)
        if not m_id:
            continue
        geru_id = m_id.group(1)

        company_text = name_strong.get_text(strip=True) if name_strong else ""
        if hint_lower and hint_lower not in company_text.lower():
            continue

        title_text = title_p.get_text(strip=True) if title_p else ""
        if not is_mar19_title(title_text):
            continue

        pub_date = None
        if date_span:
            m_d = _DATE_DMY_RE.search(date_span.get_text())
            if m_d:
                try:
                    pub_date = date(int(m_d.group(3)), int(m_d.group(2)), int(m_d.group(1)))
                except ValueError:
                    pass
        if pub_date is None:
            continue

        results.append(
            {
                "geru_id": geru_id,
                "publication_date": pub_date,
                "title": title_text,
                "company": company_text,
                "url": urljoin(_GPW_BASE_URL, href),
            }
        )
    return results


def parse_espi_report_html(html: str, stub: dict) -> InsiderTransactionItem:
    """Parse a single GPW ESPI report HTML into an InsiderTransactionItem."""
    soup = BeautifulSoup(html or "", "html.parser")
    soup = soup.select_one(".report-data, .report-content") or soup

    # Extract main report body and attachment filenames
    body_parts: list[str] = [stub.get("title", "")]
    attachments_parts: list[str] = []

    for a in soup.find_all("a"):
        href = str(a.get("href") or "")
        if ".pdf" in href.lower():
            attachments_parts.append(a.get_text(strip=True))
            attachments_parts.append(href)

    for tr in soup.find_all("tr"):
        txt = tr.get_text(separator=" ", strip=True)
        if any(
            k in txt.lower()
            for k in ("treść raportu", "podstawa prawna", "art. 19", "nabyci", "zbyci", "sprzeda")
        ):
            body_parts.append(txt)

    body_parts.append(soup.get_text(separator=" ", strip=True))
    full_body = " ".join(body_parts)
    attachments_str = " ".join(attachments_parts)

    # Preparation date is not publication date; keep the timestamp from the list.
    pub_date: date = stub["publication_date"]
    from app.services.mar_notification_parser import extract_trade_date

    trade_date = extract_trade_date(full_body)
    name_match = re.search(
        r"(?:Osoba pełniąca obowiązki zarządcze|Nazwa/Nazwisko)\s*:\s*([^:]+?)"
        r"(?=\s*[-–]|\s+Rodzaj transakcji|\s+Stanowisko)",
        full_body,
        re.I,
    )

    tx_type, is_open = parse_espi_direction(full_body, attachments_str)
    role = extract_role(full_body)
    shares, price = extract_shares_and_price(full_body)
    value = round(shares * price, 2) if (shares and price) else None

    return InsiderTransactionItem(
        trade_date=trade_date,
        publication_date=pub_date,
        insider_name=name_match.group(1).strip() if name_match else None,
        role=role,
        transaction_type=tx_type,
        is_open_market=is_open,
        shares=shares,
        price=price,
        currency="PLN",
        value=value,
        source="espi",
        source_url=stub.get("url"),
        notes=stub.get("title"),
    )


class EspiClient:
    """Async client for searching and parsing GPW ESPI MAR Art. 19 reports."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._issuer_indexes: TTLCache[list[str]] = TTLCache(max_entries=20)

    async def get_company_insider_transactions(
        self,
        company_name: str,
        ticker: str,
        limit: int = 50,
    ) -> list[InsiderTransactionItem]:
        """Search GPW ESPI reports for a company and return parsed MAR 19 items."""
        # Use the first significant word of the company name as search query
        clean_name = re.sub(
            r"\b(?:S\.?A\.?|SPÓŁKA|AKCYJNA|GRUPA|POLSKA)\b",
            "",
            company_name,
            flags=re.IGNORECASE,
        ).strip()
        words = [w for w in re.split(r"[\s\-]+", clean_name) if len(w) >= 3]
        search_query = words[0] if words else ticker.upper()

        payload = {
            "action": "GPWEspiReportUnion",
            "start": "ajaxSearch",
            "page": "komunikaty",
            "format": "html",
            "lang": "PL",
            "letter": "",
            "offset": "0",
            "limit": str(limit),
            "categoryRaports[]": "ESPI",
            "typeRaports[]": "RB",
            "search-xs": "",
            "searchText": search_query,
            "date": "",
        }

        async with self._semaphore:
            list_html = await self._post_form(_GPW_AJAX_URL, payload)
            if not list_html:
                return []

            stubs = parse_espi_list_html(list_html, target_company_hint=search_query)
            if not stubs:
                return []

            items: list[InsiderTransactionItem] = []
            # Fetch up to 15 matched MAR 19 reports per company
            for stub in stubs[:15]:
                report_html = await self._get_url(stub["url"])
                if not report_html:
                    continue
                soup = BeautifulSoup(report_html, "html.parser")
                report = soup.select_one(".report-data, .report-content") or soup
                attachment_urls = dict.fromkeys(
                    urljoin(stub["url"], str(a.get("href")))
                    for a in report.find_all("a", href=True)
                    if ".pdf" in str(a.get("href")).lower()
                )
                detail_items: list[InsiderTransactionItem] = []
                for url in list(attachment_urls)[:10]:
                    # GPW serves reports and their attachments on its own domain.
                    if urlsplit(url).hostname != "www.gpw.pl":
                        continue
                    content = await self._get_pdf(url)
                    if not content:
                        content = await self._get_issuer_pdf(url, company_name)
                    if content:
                        detail_items.extend(await asyncio.to_thread(parse_mar_pdf, content, stub))
                # A report is a container, not an extra trade alongside its attachments.
                if detail_items:
                    items.extend(detail_items)
                else:
                    items.append(parse_espi_report_html(report_html, stub))
            return items

    async def _get_pdf(self, url: str) -> bytes | None:
        return await asyncio.to_thread(self._browser_request, "GET", url, None, True)

    async def _get_issuer_pdf(self, gpw_url: str, company_name: str) -> bytes | None:
        index_url = next(
            (
                url
                for name, url in _ISSUER_REPORT_INDEXES.items()
                if name in company_name.casefold()
            ),
            None,
        )
        if index_url is None:
            return None
        links = self._issuer_indexes.get(index_url)
        if links is None:
            html = await self._get_url(index_url)
            if not html:
                return None
            soup = BeautifulSoup(html, "html.parser")
            links = list(
                dict.fromkeys(
                    urljoin(index_url, str(a["href"]))
                    for a in soup.find_all("a", href=True)
                    if ".pdf" in str(a["href"]).lower()
                    and urlsplit(urljoin(index_url, str(a["href"]))).hostname
                    == urlsplit(index_url).hostname
                )
            )
            self._issuer_indexes.set(index_url, links, 3600)
        filename = unquote(urlsplit(gpw_url).path).rsplit("/", 1)[-1].split(",", 1)[0]
        key = re.sub(r"\W", "", filename).casefold()
        for link in links:
            if key in re.sub(r"\W", "", unquote(urlsplit(link).path)).casefold():
                return await self._get_pdf(link)
        return None

    async def _post_form(self, url: str, data: dict) -> str | None:
        try:
            async with httpx.AsyncClient(
                timeout=12.0, headers=_HEADERS, follow_redirects=True
            ) as client:
                resp = await client.post(url, data=data)
                if resp.status_code == 200 and len(resp.text) > 50:
                    return resp.text
        except Exception as exc:
            logger.debug("httpx POST to GPW failed (%s), trying curl fallback.", exc)

        return await asyncio.to_thread(self._curl_post_sync, url, data)

    async def _get_url(self, url: str) -> str | None:
        # GPW report pages reject the default TLS fingerprint even with HTTP 200.
        return await asyncio.to_thread(self._curl_get_sync, url)

    @staticmethod
    def _curl_post_sync(url: str, data: dict) -> str | None:
        return EspiClient._browser_request("POST", url, data)

    @staticmethod
    def _curl_get_sync(url: str) -> str | None:
        return EspiClient._browser_request("GET", url)

    @staticmethod
    def _browser_request(
        method: str, url: str, data: dict | None = None, binary: bool = False
    ) -> str | bytes | None:
        # Browser TLS also works on the Linux production image (no curl.exe).
        from curl_cffi import requests

        try:
            resp = requests.request(
                method, url, data=data, headers=_HEADERS, impersonate="chrome", timeout=15
            )
            if resp.status_code == 200:
                if binary:
                    if resp.content.startswith(b"%PDF-") and len(resp.content) <= 10_000_000:
                        return resp.content
                else:
                    text = resp.content.decode("utf-8", errors="replace")
                    if "<title>Request Rejected</title>" not in text:
                        return text
        except Exception as exc:
            logger.debug("Browser request to GPW failed: %s", exc)
        return None
