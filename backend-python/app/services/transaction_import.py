"""Convert reviewed JSON executions into the existing atomic portfolio import."""

from uuid import NAMESPACE_URL, uuid5

from app.markets import quote_currency
from app.models.portfolio import ImportTransactions
from app.services.portfolio import PortfolioError
from app.services.portfolio_instruments import find_portfolio_instrument
from app.services.xtb_import import ParsedImport


def prepare_transactions(payload: ImportTransactions, companies) -> ParsedImport:
    rows, references = [], set()
    for index, entry in enumerate(payload.transactions, start=1):
        if entry.date != payload.report_date:
            raise PortfolioError("import_report_date_mismatch", 422)
        company = find_portfolio_instrument(entry.ticker, companies)
        if company is None:
            raise PortfolioError("unknown_ticker", 422)
        if quote_currency(company) != entry.currency:
            raise PortfolioError("currency_mismatch", 422)
        # Order IDs alone are only sufficient for a single execution per order.
        # Partial fills must carry the broker's stable execution ID on every fill.
        reference = (
            f"xtb:json:{payload.broker_account_id}:{entry.order_id}:"
            f"{entry.execution_id or 'single'}"
        )
        if reference in references:
            raise PortfolioError("import_ambiguous_execution", 422)
        references.add(reference)
        trade = entry.model_dump(mode="json", exclude={"order_id", "execution_id"})
        trade.update(id=str(uuid5(NAMESPACE_URL, reference)), source="xtb", sourceId=reference)
        rows.append(
            {
                "sheet": "JSON",
                "row": index,
                "status": "ready",
                "transaction": trade,
                "orderId": entry.order_id,
                "executionId": entry.execution_id,
            }
        )
    return ParsedImport(rows, 0, [], broker_account_id=payload.broker_account_id)
