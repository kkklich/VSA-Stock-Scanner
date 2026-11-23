"""Durable additions to the shared stock catalogue."""

from sqlalchemy import select

from app.db.models import CompanyRow, CustomCompanyRow, DailyQuoteRow
from app.models import GpwCompany


class CustomCompanyRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list(self) -> list[GpwCompany]:
        async with self._session_factory() as session:
            rows = await session.execute(select(CustomCompanyRow))
            return [GpwCompany.model_validate(row.data) for row in rows.scalars()]

    async def add(self, company: GpwCompany, user_id: int, quotes) -> None:
        # Metadata and initial prices either all persist or all roll back.
        async with self._session_factory() as session, session.begin():
            session.add(CustomCompanyRow(
                ticker=company.ticker, data=company.model_dump(mode="json"), created_by=user_id,
            ))
            await session.merge(CompanyRow(
                ticker=company.ticker, name=company.name, sector=company.sector,
            ))
            existing = set((await session.execute(
                select(DailyQuoteRow.date).where(DailyQuoteRow.ticker == company.ticker)
            )).scalars())
            for quote in quotes:
                if quote.date not in existing:
                    session.add(DailyQuoteRow(ticker=company.ticker, **quote.model_dump()))
                    existing.add(quote.date)
