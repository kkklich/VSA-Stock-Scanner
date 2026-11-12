"""Listed instruments available to portfolio ledgers outside the scanner universe."""

from app.markets import GERMANY
from app.models.stocks import GpwCompany
from app.services.gpw_company_service import GpwCompanyService

_PORTFOLIO_ONLY = {
    "nvd.de": GpwCompany(
        ticker="nvd.de",
        name="NVIDIA Corporation",
        market=GERMANY.id,
        exchange=GERMANY.exchange,
        currency=GERMANY.currency,
    ),
}


def find_portfolio_instrument(ticker: str, companies: GpwCompanyService) -> GpwCompany | None:
    return companies.find(ticker) or _PORTFOLIO_ONLY.get(ticker)


def list_portfolio_instruments(companies: GpwCompanyService) -> list[GpwCompany]:
    available = {company.ticker: company for company in companies.enabled_companies()}
    for ticker, company in _PORTFOLIO_ONLY.items():
        available.setdefault(ticker, company)
    return list(available.values())
