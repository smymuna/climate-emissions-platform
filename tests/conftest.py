from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from emissions.records import Record
from emissions.sources.base import Download

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_download(name: str, content_type: str = "application/json") -> Download:
    return Download(f"file://{name}", (FIXTURES / name).read_bytes(), content_type)


def rec(
    value: float | None,
    *,
    year: int = 2022,
    country: str = "DE",
    indicator: str = "X",
    source: str = "eurostat",
    unit: str = "Mt CO2e",
    metric: str | None = "emissions",
    sector: str | None = "TOTAL_EXCL_LULUCF",
    gas: str | None = "GHG",
) -> Record:
    return Record(source, country, indicator, year, value, unit, metric, sector, gas)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A migrated, empty database. Integration tests are skipped without one."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run integration tests")
    from emissions.cli import migrate
    from emissions.config import Settings
    from emissions.db.repository import make_engine

    eng = make_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mart, core, ingest CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    migrate(Settings(database_url=url))
    yield eng
    eng.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> Engine:
    """Empty fact and run tables before each test; reference data stays."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE core.emission, core.population, ingest.rejected_record, "
                "ingest.landing_file, ingest.run RESTART IDENTITY CASCADE"
            )
        )
    return engine
