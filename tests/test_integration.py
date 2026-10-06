"""End to end against a real PostgreSQL: pipeline -> tables -> views -> API.

Sources are served from captured fixtures, so the test is offline and deterministic.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from emissions.api.app import create_app
from emissions.config import Settings
from emissions.landing import LocalLandingStore
from emissions.pipeline import RunResult, run_source
from emissions.sources.base import Download, SourceError
from emissions.sources.eurostat import EurostatAdapter
from emissions.sources.owid import OwidAdapter
from emissions.sources.worldbank import WorldBankAdapter
from tests.conftest import fixture_download

pytestmark = pytest.mark.integration
TODAY = date(2026, 10, 5)


class OfflineEurostat(EurostatAdapter):
    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        return [fixture_download("eurostat_env_air_gge_de_el.json")]


class OfflineWorldBank(WorldBankAdapter):
    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        return [
            fixture_download("worldbank_ghg_page1.json"),
            fixture_download("worldbank_ghg_page2.json"),
        ]


class OfflineOwid(OwidAdapter):
    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        return [fixture_download("owid_co2_sample.csv", "text/csv")]


def ingest_all(engine: Engine, tmp_path: Path) -> list[RunResult]:
    with httpx.Client() as http:
        return [
            run_source(
                a, engine=engine, http=http, landing=LocalLandingStore(tmp_path), today=TODAY
            )
            for a in (OfflineEurostat(), OfflineWorldBank(), OfflineOwid())
        ]


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def test_pipeline_loads_all_sources(clean_db: Engine, tmp_path: Path) -> None:
    results = ingest_all(clean_db, tmp_path)
    assert all(r.stats.inserted > 0 for r in results)
    # Greece arrives as EL (Eurostat) and GRC (World Bank, OWID); all end up as GR.
    n = scalar(clean_db, "SELECT count(DISTINCT source) FROM core.emission WHERE country='GR'")
    assert n == 3
    # Aggregates (EMU, OWID's World / EU-27) are never loaded.
    assert (
        scalar(
            clean_db,
            "SELECT count(*) FROM core.emission WHERE country NOT IN "
            "(SELECT iso2 FROM core.country)",
        )
        == 0
    )
    # Units are normalised: Eurostat kt -> Mt.
    de = scalar(
        clean_db,
        "SELECT value_mt_co2e FROM core.emission WHERE source='eurostat' "
        "AND country='DE' AND sector='TOTAL_EXCL_LULUCF' AND gas='GHG' "
        "AND year=2022",
    )
    assert float(de) == pytest.approx(749.26642)  # type: ignore[arg-type]
    runs = scalar(clean_db, "SELECT count(*) FROM ingest.run WHERE status='succeeded'")
    assert runs == 3
    assert scalar(clean_db, "SELECT count(*) FROM ingest.landing_file") == 4


def test_rerun_is_idempotent_and_detects_changes(clean_db: Engine, tmp_path: Path) -> None:
    first = ingest_all(clean_db, tmp_path)
    second = ingest_all(clean_db, tmp_path)
    for a, b in zip(first, second, strict=True):
        assert b.stats.inserted == 0
        assert b.stats.updated == 0
        assert b.stats.unchanged == a.stats.inserted

    with clean_db.begin() as conn:  # simulate a revision at the source
        conn.execute(
            text(
                "UPDATE core.emission SET value_mt_co2e = 1 WHERE source='owid' "
                "AND country='DE' AND year=2022 AND gas='GHG'"
            )
        )
    with httpx.Client() as http:
        third = run_source(
            OfflineOwid(),
            engine=clean_db,
            http=http,
            landing=LocalLandingStore(tmp_path),
            today=TODAY,
        )
    assert third.stats.updated == 1
    assert third.stats.inserted == 0


def test_failed_run_is_recorded(clean_db: Engine, tmp_path: Path) -> None:
    class Broken(OwidAdapter):
        def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
            raise SourceError("upstream down")

    with httpx.Client() as http, pytest.raises(SourceError):
        run_source(
            Broken(), engine=clean_db, http=http, landing=LocalLandingStore(tmp_path), today=TODAY
        )
    with clean_db.connect() as conn:
        status, error = conn.execute(text("SELECT status, error FROM ingest.run")).one()
    assert status == "failed"
    assert "upstream down" in error
    assert scalar(clean_db, "SELECT count(*) FROM core.emission") == 0


@pytest.fixture
def api(clean_db: Engine, tmp_path: Path) -> TestClient:
    ingest_all(clean_db, tmp_path)
    return TestClient(create_app(Settings(), engine=clean_db))


def test_api_reference_endpoints(api: TestClient) -> None:
    with api:
        countries = api.get("/v1/countries").json()
        assert {"iso2": "GR", "iso3": "GRC", "name": "Greece", "is_eu27": True} in countries
        assert [s["code"] for s in api.get("/v1/sources").json()] == [
            "eurostat",
            "worldbank",
            "owid",
        ]
        assert api.get("/readyz").json() == {"status": "ready"}


def test_api_preferred_source_is_chosen_per_series(api: TestClient) -> None:
    with api:
        body = api.get("/v1/countries/DEU/indicators").json()
    series = {p["year"]: p for p in body["series"]}
    # Eurostat outranks the others and has DE data, so the whole series comes from it,
    # even for 1990, where only OWID (in this fixture) has a value. Mixing sources
    # year by year would create artificial jumps.
    assert {p["emissions_source"] for p in series.values()} == {"eurostat"}
    assert 1990 not in series
    assert series[2022]["total_ghg_mt"] == pytest.approx(749.27, abs=0.01)
    # The World Bank fixture has no population series, so OWID's is used.
    assert series[2022]["population_source"] == "owid"
    assert series[2022]["ghg_per_capita_t"] == pytest.approx(749.26642e6 / 84086227, abs=0.01)
    assert series[2023]["change_vs_prev_year_pct"] == pytest.approx(
        round(100 * (series[2023]["total_ghg_mt"] / series[2022]["total_ghg_mt"] - 1), 1)
    )


def test_api_sector_breakdown_shares(api: TestClient) -> None:
    with api:
        body = api.get("/v1/countries/de/sectors", params={"year": 2022}).json()
    sectors = {s["sector"]: s for s in body["sectors"]}
    assert "TOTAL_EXCL_LULUCF" not in sectors
    assert sectors["LULUCF"]["share_pct"] is None
    shares = sum(s["share_pct"] for s in sectors.values() if s["share_pct"] is not None)
    assert shares == pytest.approx(100, abs=0.6)  # rounding of each share


def test_api_reconciliation(api: TestClient) -> None:
    with api:
        rows = api.get("/v1/reconciliation", params={"year": 2022}).json()
    de = next(r for r in rows if r["country"] == "DE")
    assert de["n_sources"] == 3
    assert de["eurostat_mt"] == pytest.approx(749.27, abs=0.01)
    assert de["owid_mt"] == pytest.approx(706.251)
    assert de["spread_pct"] == pytest.approx(
        round(100 * (758.3872 - 706.251) / ((749.26642 + 758.3872 + 706.251) / 3), 1), abs=0.1
    )


def test_api_emissions_filters_and_paging(api: TestClient) -> None:
    with api:
        r = api.get(
            "/v1/emissions",
            params={"country": "GR", "source": "worldbank", "limit": 2, "offset": 1},
        )
        body = r.json()
        assert body["total"] == 4
        assert [d["year"] for d in body["data"]] == [2022, 2023]
        assert api.get("/v1/emissions", params={"sector": "NOPE"}).status_code == 404
        assert api.get("/v1/emissions", params={"source": "nasa"}).status_code == 404
        bad = api.get("/v1/emissions", params={"from_year": 2024, "to_year": 2020})
        assert bad.status_code == 422
        assert bad.headers["content-type"] == "application/problem+json"
        assert api.get("/v1/countries/XX/indicators").status_code == 404
        assert api.get("/v1/countries/DE/sectors", params={"year": 1995}).status_code == 404


def test_api_runs_expose_quality_report(api: TestClient) -> None:
    with api:
        runs = api.get("/v1/runs", params={"source": "owid"}).json()
    assert len(runs) == 1
    q = runs[0]["quality"]
    assert q["steps"][0]["step"] == "missing_values"
    assert q["dropped"]["out_of_scope_country"] > 0  # World, EU-27, Kosovo
