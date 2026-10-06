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
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from app.models import InsiderTransactionItem

logger = logging.getLogger(__name__)

_GPW_BASE_URL = "https://www.gpw.pl"
_GPW_AJAX_URL = f"{_GPW_BASE_URL}/ajaxindex.php"
_GPW_REPORT_URL = f"{_GPW_BASE_URL}/espi-ebi-report"

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
    (re.compile(r"prezes[a-z]*\s+zarz[aą]du", re.IGNORECASE), "Prezes Zarządu"),
    (re.compile(r"wiceprezes[a-z]*\s+zarz[aą]du", re.IGNORECASE), "Wiceprezes Zarządu"),
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
    if has_buy and has_sell:
        # Both words appear — check which appears in the specific context of the notification
        buy_pos = combined.find("nabyci")
        if buy_pos < 0:
            buy_pos = combined.find("kupn")
        sell_pos = combined.find("zbyci")
        if sell_pos < 0:
            sell_pos = combined.find("sprzeda")
        if buy_pos >= 0 and (sell_pos < 0 or buy_pos < sell_pos):
            return ("buy", True)
        if sell_pos >= 0:
            return ("sell", True)

    return ("other", True)


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

        pub_date = date.today()
        if date_span:
            m_d = _DATE_DMY_RE.search(date_span.get_text())
            if m_d:
                try:
                    pub_date = date(int(m_d.group(3)), int(m_d.group(2)), int(m_d.group(1)))
                except ValueError:
                    pass

        results.append(
            {
                "geru_id": geru_id,
                "publication_date": pub_date,
                "title": title_text,
                "company": company_text,
                "url": f"{_GPW_REPORT_URL}?geru_id={geru_id}",
            }
        )
    return results


def parse_espi_report_html(html: str, stub: dict) -> InsiderTransactionItem:
    """Parse a single GPW ESPI report HTML into an InsiderTransactionItem."""
    soup = BeautifulSoup(html or "", "html.parser")

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

    # Check if publication date is refined in Data sporządzenia
    pub_date: date = stub.get("publication_date", date.today())
    for td in soup.find_all("td"):
        if "data sporządzenia" in td.get_text(strip=True).lower():
            nxt = td.find_next_sibling("td")
            if nxt:
                m_ymd = _DATE_YMD_RE.search(nxt.get_text(strip=True))
                if m_ymd:
                    try:
                        pub_date = date(
                            int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
                        )
                    except ValueError:
                        pass
            break

    tx_type, is_open = parse_espi_direction(full_body, attachments_str)
    role = extract_role(full_body)
    shares, price = extract_shares_and_price(full_body)
    value = round(shares * price, 2) if (shares and price) else None

    return InsiderTransactionItem(
        trade_date=pub_date,
        publication_date=pub_date,
        insider_name=None,
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
                items.append(parse_espi_report_html(report_html or "", stub))
            return items

    async def _post_form(self, url: str, data: dict) -> str | None:
        try:
            async with httpx.AsyncClient(verify=False, timeout=12.0, headers=_HEADERS) as client:
                resp = await client.post(url, data=data)
                if resp.status_code == 200 and len(resp.text) > 50:
                    return resp.text
        except Exception as exc:
            logger.debug("httpx POST to GPW failed (%s), trying curl fallback.", exc)

        return await asyncio.to_thread(self._curl_post_sync, url, data)

    async def _get_url(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(verify=False, timeout=12.0, headers=_HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.text) > 50:
                    return resp.text
        except Exception as exc:
            logger.debug("httpx GET to GPW failed (%s), trying curl fallback.", exc)

        return await asyncio.to_thread(self._curl_get_sync, url)

    @staticmethod
    def _curl_post_sync(url: str, data: dict) -> str | None:
        import subprocess

        encoded = urlencode(data, doseq=True)
        cmd = [
            "curl.exe",
            "-s",
            "-X",
            "POST",
            url,
            "-d",
            encoded,
            "-H",
            "X-Requested-With: XMLHttpRequest",
            "-H",
            "Referer: https://www.gpw.pl/komunikaty",
            "-A",
            _HEADERS["User-Agent"],
        ]
        try:
            out = subprocess.check_output(cmd, timeout=12)
            return out.decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.debug("curl POST to GPW failed: %s", exc)
            return None

    @staticmethod
    def _curl_get_sync(url: str) -> str | None:
        import subprocess

        cmd = [
            "curl.exe",
            "-s",
            "-L",
            url,
            "-H",
            "Referer: https://www.gpw.pl/komunikaty",
            "-A",
            _HEADERS["User-Agent"],
        ]
        try:
            out = subprocess.check_output(cmd, timeout=12)
            return out.decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.debug("curl GET to GPW failed: %s", exc)
            return None
