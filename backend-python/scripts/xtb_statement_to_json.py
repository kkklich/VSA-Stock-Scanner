"""Convert an encrypted XTB DailyStatement into single-transaction API requests.

Run from backend-python with the backend's Python environment::

    python -m scripts.xtb_statement_to_json statement.pdf \
        --portfolio-id <wallet-uuid> --version <current-wallet-version>

The requests form a sequential plan starting at the supplied wallet version.
Before sending each request, use the wallet's current version, including after
a retry. The transaction API retains the date and monetary fields. The file
import API additionally retains XTB source references and execution times.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path
from uuid import UUID

from app.config import settings
from app.models.portfolio import AddTransaction
from app.services.gpw_company_service import GpwCompanyService
from app.services.portfolio import PortfolioError
from app.services.xtb_daily_statement import parse_xtb_daily_statement
from app.services.xtb_import import MAX_FILE_BYTES


def statement_to_object(
    pdf_data: bytes,
    password: str,
    portfolio_id: UUID,
    version: int,
    companies: GpwCompanyService,
) -> dict:
    """Build JSON bodies validated against the project's AddTransaction model."""
    if version < 1:
        raise ValueError("The wallet version must be at least 1.")
    portfolio_id = UUID(str(portfolio_id))
    parsed = parse_xtb_daily_statement(pdf_data, password, companies)
    errors = [row for row in parsed.rows if row["status"] != "ready"]
    if errors:
        details = ", ".join(
            f"row {row['row']}: {row.get('code', 'invalid_transaction')}" for row in errors
        )
        raise ValueError(f"The report contains invalid transactions ({details}).")

    requests = []
    transaction_fields = AddTransaction.model_fields.keys() - {"version"}
    for index, row in enumerate(parsed.rows):
        transaction = row["transaction"]
        fields = {name: transaction[name] for name in transaction_fields}
        payload = AddTransaction.model_validate({**fields, "version": version + index})
        requests.append(
            {
                "method": "POST",
                "path": f"/api/portfolios/{portfolio_id}/transactions",
                "body": payload.model_dump(mode="json"),
                "sourceId": transaction["sourceId"],
                "executedAt": transaction["executedAt"],
            }
        )

    return {
        "brokerAccountId": parsed.broker_account_id,
        "brokerAccountCurrency": parsed.broker_account_currency,
        "ignoredSales": parsed.ignored,
        "warnings": parsed.warnings,
        "requests": requests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to the encrypted DailyStatement PDF")
    parser.add_argument("--portfolio-id", type=UUID, required=True, help="Destination wallet UUID")
    parser.add_argument("--version", type=int, required=True, help="Current wallet version")
    args = parser.parse_args()
    if args.version < 1:
        parser.error("--version must be at least 1")

    try:
        with args.pdf.open("rb") as pdf_file:
            pdf_data = pdf_file.read(MAX_FILE_BYTES + 1)
        if len(pdf_data) > MAX_FILE_BYTES:
            raise ValueError("The PDF exceeds the 5 MiB import limit.")
        password = settings.xtb_statement_password.get_secret_value()
        if not password:
            if not sys.stdin.isatty():
                raise ValueError(
                    "Set STOCKPILOT_XTB_STATEMENT_PASSWORD before running this script."
                )
            password = getpass.getpass("XTB PDF password: ")
        result = statement_to_object(
            pdf_data, password, args.portfolio_id, args.version, GpwCompanyService()
        )
    except PortfolioError as exc:
        print(f"PDF conversion failed: {exc.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"PDF conversion failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
