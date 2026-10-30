"""Historical evidence survives revisions; acquisition is never backdated."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Integer, MetaData, create_engine, event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.models import (
    CompanyCashflowRow,
    CompanyFundamentalsRow,
    CompanyQuarterlyRow,
    FinancialObservationRow,
    LongTermSnapshotRow,
)
from app.db.repository import InMemoryQuoteRepository, PostgresQuoteRepository
from app.models import CashflowPeriod, FinancialMetrics, QuarterlyReport
from app.models.stocks import FundamentalDetails


@pytest.mark.parametrize("backend", ["memory", "sql"])
async def test_extended_metrics_and_statement_evidence_survive_storage(backend, sql_repo):
    repo = InMemoryQuoteRepository() if backend == "memory" else sql_repo[0]
    metrics = FinancialMetrics(fundamental_details=FundamentalDetails(
        return_on_invested_capital=.15, interest_coverage=3,
        latest_period_end="2026-06-30", annual_period_end="2025-12-31",
    ))
    await repo.upsert_fundamentals("test", metrics)
    await repo.upsert_quarterly("test", [QuarterlyReport(period_end="2026-06-30", eps=1.25)])
    await repo.upsert_quarterly("test", [QuarterlyReport(period_end="2026-06-30", eps=1.5)])
    await repo.upsert_cashflow("test", [CashflowPeriod(
        period_end="2026-06-30", period_type="quarterly", operating_cash_flow=120,
    )])
    restored = (await repo.get_fundamentals("test")).metrics
    assert restored.fundamental_details == metrics.fundamental_details
    inputs = (await repo.get_long_term_inputs(["TEST"]))["test"]
    assert inputs["metrics"].fundamental_details == metrics.fundamental_details
    assert inputs["statements"]["quarterly"]["payload"]["reports"][0]["eps"] == 1.5
    assert inputs["statements"]["cashflow"]["payload"]["periods"][0]["operatingCashFlow"] == 120
    assert inputs["statements"]["quarterly"]["observed_at"].tzinfo is not None
    history = await repo.get_financial_history("test")
    archived = next(r for r in history if r["kind"] == "fundamentals")
    assert archived["payload"]["fundamentalDetails"]["returnOnInvestedCapital"] == .15
    assert archived["payload"]["fundamentalDetails"]["latestPeriodEnd"] == "2026-06-30"


class _AsyncSessionAdapter:
    """Run actual storage SQL/transactions on SQLite without an async driver."""

    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.session.close()

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield

    async def execute(self, statement, parameters=None):
        return self.session.execute(statement, parameters)


@pytest.fixture
def sql_repo():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function(
            "greatest", -1,
            lambda *values: max((v for v in values if v is not None), default=None),
        )

    for model in (
        CompanyFundamentalsRow, CompanyQuarterlyRow, CompanyCashflowRow,
        FinancialObservationRow, LongTermSnapshotRow,
    ):
        table = model.__table__
        if model in (CompanyQuarterlyRow, CompanyCashflowRow):
            # SQLite requires the literal INTEGER type for generated primary
            # keys; PostgreSQL uses BIGSERIAL. Adapt this test schema only.
            table = table.to_metadata(MetaData())
            table.c.id.type = Integer()
        table.create(engine)
    yield PostgresQuoteRepository(lambda: _AsyncSessionAdapter(engine)), engine
    engine.dispose()


def _item(score=72):
    return {
        "ticker": "TEST", "market": "gpw", "asOf": "2026-10-21",
        "score": score, "qualityScore": 80, "valueScore": None, "momentumScore": 60,
        "inputs": {"peRatio": None, "financialCurrency": "USD"},
        "fundamentalsObservedAt": "2026-10-20T08:00:00+00:00",
        "cohort": {"sector": "Banks", "size": 25},
    }


async def test_non_finite_upstream_observation_is_valid_json(sql_repo):
    repo, _ = sql_repo
    await repo.upsert_fundamentals(
        "test", FinancialMetrics(pe_ratio=float("nan"), eps=float("inf"))
    )
    payload = (await repo.get_financial_history("test"))[0]["payload"]
    assert payload["peRatio"] is None
    assert payload["eps"] is None
    assert "financialCurrency" in payload
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("backend", ["memory", "sql"])
async def test_snapshots_are_immutable_revisions_with_full_inputs(backend, sql_repo):
    repo = InMemoryQuoteRepository() if backend == "memory" else sql_repo[0]
    now = datetime(2026, 10, 22, 10, tzinfo=UTC)
    item = _item()
    assert not await repo.has_long_term_snapshots()
    await repo.append_long_term_snapshots([item], now, "qvm-v1")
    item["inputs"]["financialCurrency"] = "PLN"
    await repo.append_long_term_snapshots([_item(75)], now, "qvm-v2")
    history = await repo.get_long_term_history("test")
    assert [row["score"] for row in history] == [75, 72]
    assert [row["modelVersion"] for row in history] == ["qvm-v2", "qvm-v1"]
    assert history[1]["inputs"] == {"peRatio": None, "financialCurrency": "USD"}
    assert history[1]["cohort"] == {"sector": "Banks", "size": 25}
    assert history[1]["recordedAt"] == now.isoformat()
    history[1]["inputs"]["financialCurrency"] = "EUR"
    assert (await repo.get_long_term_history("TEST"))[1]["inputs"]["financialCurrency"] == "USD"
    assert len(await repo.get_long_term_history("test", limit=1)) == 1
    assert await repo.get_long_term_history("other") == []
    assert await repo.get_long_term_history("test", limit=0) == []
    assert await repo.has_long_term_snapshots()


@pytest.mark.parametrize("backend", ["memory", "sql"])
async def test_financial_revisions_keep_raw_nulls_and_real_observation_time(backend, sql_repo):
    repo = InMemoryQuoteRepository() if backend == "memory" else sql_repo[0]
    before = datetime.now(UTC)
    assert not await repo.has_financial_observations()
    first = FinancialMetrics(
        updated_at="2000-01-01T00:00:00+00:00", market_cap=100, financial_currency="USD",
        last_report_date="2025-12-31",
    )
    await repo.upsert_fundamentals("test", first)
    await repo.upsert_fundamentals("test", FinancialMetrics(market_cap=200))
    history = await repo.get_financial_history("TEST")
    assert [r["payload"]["marketCap"] for r in history] == [200, 100]
    assert history[0]["payload"]["financialCurrency"] is None
    assert history[0]["payload"]["lastReportDate"] is None
    assert history[1]["payload"]["financialCurrency"] == "USD"
    assert history[1]["payload"]["updatedAt"] == first.updated_at
    assert all(
        before <= datetime.fromisoformat(r["observedAt"]) <= datetime.now(UTC) for r in history
    )
    assert all(r["source"] == "yahoo" and r["kind"] == "fundamentals" for r in history)
    inputs = await repo.get_long_term_inputs(["TEST", "other"])
    assert list(inputs) == ["test"]
    assert inputs["test"]["metrics"].market_cap == 200
    assert inputs["test"]["observed_at"] >= before
    assert inputs["test"]["observed_at"].utcoffset() == timedelta(0)
    assert await repo.has_financial_observations()
    history[0]["payload"]["marketCap"] = -1
    assert (await repo.get_financial_history("test", 1))[0]["payload"]["marketCap"] == 200


async def test_statement_revisions_keep_period_and_currency_without_backdating():
    repo = InMemoryQuoteRepository()
    await repo.upsert_fundamentals("test", FinancialMetrics(financial_currency="EUR"))
    before = datetime.now(UTC)
    await repo.upsert_quarterly("test", [QuarterlyReport(period_end="2020-03-31", net_income=10)])
    await repo.upsert_quarterly("test", [QuarterlyReport(period_end="2020-03-31", net_income=20)])
    await repo.upsert_cashflow("test", [CashflowPeriod(
        period_end="2020-03-31", period_type="quarterly", capex=5, currency="EUR",
    )])
    history = await repo.get_financial_history("test")
    assert history[0]["payload"]["periods"][0]["currency"] == "EUR"
    assert history[0]["payload"]["periods"][0]["operatingCashFlow"] is None
    assert [r["payload"]["reports"][0]["netIncome"] for r in history[1:3]] == [20, 10]
    assert history[1]["payload"]["financialCurrency"] == "EUR"
    assert datetime.fromisoformat(history[2]["observedAt"]) >= before
    await repo.upsert_quarterly("unknown", [QuarterlyReport(period_end="2020-03-31")])
    assert (await repo.get_financial_history("unknown"))[0]["payload"]["financialCurrency"] is None


async def test_history_failure_rolls_back_latest_financial_update(sql_repo):
    repo, engine = sql_repo
    await repo.upsert_fundamentals("test", FinancialMetrics(market_cap=100))

    def reject_observation(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("INSERT INTO financial_observations"):
            raise RuntimeError("Observation could not be saved")

    event.listen(engine, "before_cursor_execute", reject_observation)
    try:
        with pytest.raises(RuntimeError, match="Observation"):
            await repo.upsert_fundamentals("test", FinancialMetrics(market_cap=200))
    finally:
        event.remove(engine, "before_cursor_execute", reject_observation)
    assert (await repo.get_long_term_inputs(["test"]))["test"]["metrics"].market_cap == 100
    assert len(await repo.get_financial_history("test")) == 1


class _CaptureSession:
    def __init__(self):
        self.statements = []
        self.transaction = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    @asynccontextmanager
    async def begin(self):
        self.transaction = True
        try:
            yield
        finally:
            self.transaction = False

    async def execute(self, statement):
        assert self.transaction
        self.statements.append(statement)
        return self

    def scalar_one_or_none(self):
        return "USD"


@pytest.mark.parametrize("kind", ["quarterly", "cashflow"])
async def test_statement_observation_is_plain_insert_in_latest_rows_transaction(kind):
    session = _CaptureSession()
    repo = PostgresQuoteRepository(lambda: session)
    if kind == "quarterly":
        await repo.upsert_quarterly("test", [QuarterlyReport(period_end="2020-03-31")])
    else:
        await repo.upsert_cashflow("test", [CashflowPeriod(
            period_end="2020-03-31", period_type="quarterly", currency="USD",
        )])
    history = session.statements[-1]
    compiled = history.compile(dialect=postgresql.dialect())
    assert history.table.name == "financial_observations"
    assert "ON CONFLICT" not in str(compiled)
    assert "UPDATE" not in str(compiled)
    assert compiled.params["kind"] == kind
    assert compiled.params["observed_at"].year >= 2026
    assert compiled.params["payload"]


async def test_naive_recording_time_rejected_and_no_partial_batch(sql_repo):
    repo, engine = sql_repo
    with pytest.raises(ValueError, match="timezone-aware"):
        await repo.append_long_term_snapshots([_item()], datetime(2026, 10, 22), "v1")
    with Session(engine) as session:
        assert session.execute(select(LongTermSnapshotRow)).all() == []


@pytest.mark.parametrize("backend", ["memory", "sql"])
async def test_snapshot_existence_is_scoped_to_requested_market(backend, sql_repo):
    repo = InMemoryQuoteRepository() if backend == "memory" else sql_repo[0]
    assert not await repo.has_long_term_snapshots()
    await repo.append_long_term_snapshots([_item()], datetime.now(UTC), "qvm-v1")
    assert await repo.has_long_term_snapshots()
    assert await repo.has_long_term_snapshots("gpw")
    assert not await repo.has_long_term_snapshots("us")


@pytest.mark.parametrize("backend", ["memory", "sql"])
async def test_archive_coverage_requires_each_available_kind_for_each_ticker(backend, sql_repo):
    repo = InMemoryQuoteRepository() if backend == "memory" else sql_repo[0]
    engine = sql_repo[1]
    # Simulate periods already stored before the archive feature was installed.
    if backend == "memory":
        repo._quarterly["old.us"] = [QuarterlyReport(period_end="2025-12-31")]
        repo._cashflow["old.us"] = [CashflowPeriod(
            period_end="2025-12-31", period_type="annual",
        )]
    else:
        with Session(engine) as session, session.begin():
            session.add(CompanyQuarterlyRow(id=1, ticker="old.us", period_end=date(2025, 12, 31)))
            session.add(CompanyCashflowRow(
                id=1, ticker="old.us", period_end=date(2025, 12, 31), period_type="annual",
            ))

    # On-demand metrics for one company must not initialise the entire archive.
    await repo.upsert_fundamentals("complete", FinancialMetrics(market_cap=100))
    assert await repo.has_financial_observations()
    wanted = ["complete", "OLD.US", "absent", "old.us"]
    assert await repo.get_missing_financial_observation_tickers(wanted) == {"old.us", "absent"}
    # Repeated metrics observations do not count as quarterly/cashflow coverage.
    for _ in range(3):
        await repo.upsert_fundamentals("old.us", FinancialMetrics(market_cap=100))

    def archive(kind):
        if backend == "memory":
            repo._record_financial_observation("old.us", kind, {}, datetime.now(UTC))
        else:
            with Session(engine) as session, session.begin():
                session.add(FinancialObservationRow(
                    ticker="old.us", kind=kind, source="yahoo",
                    observed_at=datetime.now(UTC), payload={},
                ))

    assert await repo.get_missing_financial_observation_tickers(wanted) == {"old.us", "absent"}
    archive("quarterly")
    assert await repo.get_missing_financial_observation_tickers(wanted) == {"old.us", "absent"}
    archive("cashflow")
    assert await repo.get_missing_financial_observation_tickers(wanted) == {"absent"}
    # No optional statements available: a metrics archive alone is sufficient.
    assert await repo.get_missing_financial_observation_tickers(["complete"]) == set()
    assert await repo.get_missing_financial_observation_tickers([]) == set()


async def test_archive_coverage_uses_one_bulk_query_without_reading_payloads(sql_repo):
    repo, engine = sql_repo
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert await repo.get_missing_financial_observation_tickers(["one", "two"]) == {
            "one", "two",
        }
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert "payload" not in statements[0]


def test_migration_creates_same_history_schema_as_models_and_no_backfill(monkeypatch):
    path = Path(__file__).parents[1] / "alembic/versions/009_long_term_history.py"
    spec = spec_from_file_location("long_term_history_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
            module.upgrade()
            inspector = inspect(connection)
            for model in (FinancialObservationRow, LongTermSnapshotRow):
                table = model.__table__
                assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.c.keys())
                assert {i["name"] for i in inspector.get_indexes(table.name)} == {
                    index.name for index in table.indexes
                }
                assert connection.execute(select(table)).all() == []
            module.downgrade()
            assert inspect(connection).get_table_names() == []
    finally:
        engine.dispose()


def test_fundamental_migration_preserves_legacy_rows_without_inventing_evidence(monkeypatch):
    from sqlalchemy import text

    path = Path(__file__).parents[1] / "alembic/versions/012_fundamental_details.py"
    spec = spec_from_file_location("fundamental_details_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE company_fundamentals (ticker VARCHAR(20))"))
            connection.execute(text("INSERT INTO company_fundamentals (ticker) VALUES ('legacy')"))
            monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
            module.upgrade()
            row = connection.execute(text(
                "SELECT ticker, fundamental_details FROM company_fundamentals"
            )).one()
            assert tuple(row) == ("legacy", None)
            module.downgrade()
            assert {c["name"] for c in inspect(connection).get_columns("company_fundamentals")} == {
                "ticker",
            }
    finally:
        engine.dispose()
