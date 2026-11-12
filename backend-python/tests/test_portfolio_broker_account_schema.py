"""XTB account links preserve leading zeros and are unique within an owner."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError

from app.models.portfolio import CreatePortfolio, UpdatePortfolio


def test_account_currency_migration_preserves_preexisting_links():
    path = Path(__file__).parents[1] / "alembic/versions/017_portfolio_broker_account_currency.py"
    spec = spec_from_file_location("portfolio_account_currency_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE portfolios (id TEXT PRIMARY KEY, broker_account_id VARCHAR(32))"
        )
        connection.exec_driver_sql("INSERT INTO portfolios VALUES ('legacy', '00123')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # App startup can add the column first.
            assert connection.exec_driver_sql("SELECT * FROM portfolios").one() == (
                "legacy", "00123", None,
            )
            migration.downgrade()
        assert connection.exec_driver_sql("SELECT * FROM portfolios").one() == ("legacy", "00123")
    engine.dispose()


def test_portfolio_account_command_preserves_identity_and_explicit_clear():
    details = {"name": "Brokerage", "broker": "XTB", "costMethod": "fifo"}
    created = CreatePortfolio(id=uuid4(), brokerAccountId=" 00123456 ", **details)
    assert created.broker_account_id == "00123456"

    omitted = UpdatePortfolio(version=1, **details)
    cleared = UpdatePortfolio(version=1, brokerAccountId=None, **details)
    assert "broker_account_id" not in omitted.model_fields_set
    assert "broker_account_id" in cleared.model_fields_set
    assert cleared.broker_account_id is None

    for invalid in ("", "１２３", "12a", "1234" * 9, 123):
        with pytest.raises(ValidationError):
            UpdatePortfolio(version=1, brokerAccountId=invalid, **details)
    with pytest.raises(ValidationError):
        UpdatePortfolio(version=1, brokerAccountId="00123456", **{**details, "broker": "Other"})


def test_account_link_migration_preserves_legacy_wallets_and_enforces_owner_uniqueness():
    path = Path(__file__).parents[1] / "alembic/versions/016_portfolio_broker_account.py"
    spec = spec_from_file_location("portfolio_broker_account_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE portfolios (id TEXT PRIMARY KEY, user_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO portfolios VALUES ('legacy', 1)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # Startup can have added the schema before Alembic runs.
            assert connection.exec_driver_sql("SELECT * FROM portfolios").one() == (
                "legacy",
                1,
                None,
            )

            connection.exec_driver_sql(
                "INSERT INTO portfolios VALUES "
                "('first', 1, '00123'), ('second', 2, '00123'), ('unlinked', 1, NULL)"
            )
            with pytest.raises(sa.exc.IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO portfolios VALUES ('duplicate', 1, '00123')"
                )

            migration.downgrade()
            assert [
                column["name"] for column in sa.inspect(connection).get_columns("portfolios")
            ] == [
                "id",
                "user_id",
            ]
    engine.dispose()
