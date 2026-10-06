from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import OperationalError

from emissions import __version__
from emissions.api.schemas import (
    CountryIndicators,
    CountryOut,
    EmissionOut,
    Gas,
    IndicatorOut,
    Page,
    ReconciliationOut,
    RunOut,
    SectorBreakdown,
    SectorOut,
    SectorShareOut,
    SourceOut,
)
from emissions.config import Settings
from emissions.db.repository import make_engine
from emissions.reference import BY_ISO2, BY_ISO3, SECTOR_CODES, SOURCE_CODES, Country


def get_conn(request: Request) -> Iterator[Connection]:
    engine: Engine = request.app.state.engine
    with engine.connect() as conn:
        yield conn


Conn = Annotated[Connection, Depends(get_conn)]
Year = Annotated[int | None, Query(ge=1990, le=2100)]


def resolve_country(code: str) -> Country:
    """Accept ISO alpha-2 or alpha-3, any case. Eurostat's EL/UK are accepted too."""
    c = code.upper()
    country = BY_ISO2.get(c) or BY_ISO3.get(c) or {"EL": BY_ISO2["GR"], "UK": BY_ISO2["GB"]}.get(c)
    if country is None:
        raise HTTPException(404, f"unknown country {code!r}; see /v1/countries")
    return country


CountryCode = Annotated[str, Path(description="ISO 3166 alpha-2 or alpha-3, e.g. DE or DEU")]


def _rows(conn: Connection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine or make_engine(settings.database_url)
        yield
        if engine is None:
            app.state.engine.dispose()

    app = FastAPI(
        title="Climate Emissions Platform",
        version=__version__,
        summary="Standardised greenhouse gas indicators for European countries, "
        "built from Eurostat, World Bank and Our World in Data.",
        lifespan=lifespan,
    )

    @app.exception_handler(HTTPException)
    async def _problem(_: Request, exc: HTTPException) -> JSONResponse:
        """RFC 9457 problem details instead of FastAPI's default {"detail": ...}."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "about:blank",
                "title": _TITLES.get(exc.status_code, "Error"),
                "status": exc.status_code,
                "detail": exc.detail,
            },
            media_type="application/problem+json",
        )

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["ops"])
    def readyz(request: Request) -> dict[str, str]:
        try:
            with request.app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM core.source LIMIT 1"))
        except OperationalError as exc:
            raise HTTPException(503, "database unavailable") from exc
        return {"status": "ready"}

    # --- reference data ---------------------------------------------------------------

    @app.get("/v1/countries", tags=["reference"])
    def countries(conn: Conn) -> list[CountryOut]:
        rows = _rows(conn, "SELECT iso2, iso3, name, is_eu27 FROM core.country ORDER BY name")
        return [CountryOut(**r) for r in rows]

    @app.get("/v1/sectors", tags=["reference"])
    def sectors(conn: Conn) -> list[SectorOut]:
        rows = _rows(conn, "SELECT code, name, description FROM core.sector ORDER BY sort_order")
        return [SectorOut(**r) for r in rows]

    @app.get("/v1/sources", tags=["reference"])
    def sources(conn: Conn) -> list[SourceOut]:
        rows = _rows(
            conn, "SELECT code, name, url, licence, priority FROM core.source ORDER BY priority"
        )
        return [SourceOut(**r) for r in rows]

    # --- facts ------------------------------------------------------------------------

    @app.get("/v1/emissions", tags=["emissions"])
    def emissions(
        conn: Conn,
        country: Annotated[str | None, Query(description="ISO alpha-2/alpha-3")] = None,
        sector: str = "TOTAL_EXCL_LULUCF",
        gas: Gas = "GHG",
        source: Annotated[
            str, Query(description="'preferred' (one source per series) or a source code")
        ] = "preferred",
        from_year: Year = None,
        to_year: Year = None,
        limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[EmissionOut]:
        """Emission values for one sector and gas, filtered by country, source and years."""
        if sector not in SECTOR_CODES:
            raise HTTPException(404, f"unknown sector {sector!r}; see /v1/sectors")
        if source != "preferred" and source not in SOURCE_CODES:
            raise HTTPException(404, f"unknown source {source!r}; see /v1/sources")
        if from_year and to_year and from_year > to_year:
            raise HTTPException(422, "from_year must not be after to_year")

        table = "mart.emission_preferred" if source == "preferred" else "core.emission"
        where = ["sector = :sector", "gas = :gas"]
        params: dict[str, Any] = {"sector": sector, "gas": gas}
        if country:
            where.append("country = :country")
            params["country"] = resolve_country(country).iso2
        if source != "preferred":
            where.append("source = :source")
            params["source"] = source
        if from_year:
            where.append("year >= :from_year")
            params["from_year"] = from_year
        if to_year:
            where.append("year <= :to_year")
            params["to_year"] = to_year
        cond = " AND ".join(where)  # only fixed fragments; values are bound parameters

        total = conn.execute(text(f"SELECT count(*) FROM {table} WHERE {cond}"), params)
        rows = _rows(
            conn,
            f"""SELECT country, sector, gas, year, value_mt_co2e, source FROM {table}
                WHERE {cond} ORDER BY country, year LIMIT :limit OFFSET :offset""",
            **params,
            limit=limit,
            offset=offset,
        )
        return Page[EmissionOut](
            data=[EmissionOut(**r) for r in rows],
            total=total.scalar_one(),
            limit=limit,
            offset=offset,
        )

    @app.get("/v1/countries/{code}/indicators", tags=["indicators"])
    def country_indicators(
        code: CountryCode, conn: Conn, from_year: Year = None, to_year: Year = None
    ) -> CountryIndicators:
        """Total GHG, per-capita emissions and change vs 1990 and vs the previous year."""
        c = resolve_country(code)
        rows = _rows(
            conn,
            """SELECT year, total_ghg_mt, emissions_source, population, population_source,
                      ghg_per_capita_t, change_vs_1990_pct, change_vs_prev_year_pct
               FROM mart.country_indicator
               WHERE country = :c AND year BETWEEN :f AND :t ORDER BY year""",
            c=c.iso2,
            f=from_year or 1990,
            t=to_year or 2100,
        )
        return CountryIndicators(
            country=CountryOut(iso2=c.iso2, iso3=c.iso3, name=c.name, is_eu27=c.is_eu27),
            series=[IndicatorOut(**r) for r in rows],
        )

    @app.get("/v1/countries/{code}/sectors", tags=["indicators"])
    def sector_breakdown(
        code: CountryCode,
        conn: Conn,
        year: Annotated[int, Query(ge=1990, le=2100)],
        gas: Gas = "GHG",
    ) -> SectorBreakdown:
        """Emissions by sector for one year, with each sector's share of the total."""
        c = resolve_country(code)
        rows = _rows(
            conn,
            """SELECT e.sector, s.name, e.value_mt_co2e, e.source, s.sort_order
               FROM mart.emission_preferred e JOIN core.sector s ON s.code = e.sector
               WHERE e.country = :c AND e.year = :y AND e.gas = :g
               ORDER BY s.sort_order""",
            c=c.iso2,
            y=year,
            g=gas,
        )
        if not rows:
            raise HTTPException(404, f"no sector data for {c.iso2} {gas} {year}")
        total = next((r["value_mt_co2e"] for r in rows if r["sector"] == "TOTAL_EXCL_LULUCF"), None)
        parts = [
            SectorShareOut(
                sector=r["sector"],
                name=r["name"],
                value_mt_co2e=r["value_mt_co2e"],
                share_pct=round(100 * r["value_mt_co2e"] / total, 1)
                if total and r["sector"] != "LULUCF"
                else None,
                source=r["source"],
            )
            for r in rows
            if r["sector"] != "TOTAL_EXCL_LULUCF"
        ]
        return SectorBreakdown(
            country=c.iso2, year=year, gas=gas, total_mt_co2e=total, sectors=parts
        )

    @app.get("/v1/reconciliation", tags=["data quality"])
    def reconciliation(
        conn: Conn,
        year: Annotated[int, Query(ge=1990, le=2100)],
        gas: Gas = "GHG",
        min_spread_pct: Annotated[float, Query(ge=0)] = 0.0,
    ) -> list[ReconciliationOut]:
        """Compare each source's national total; large spreads point to method differences."""
        rows = _rows(
            conn,
            """SELECT * FROM mart.source_reconciliation
               WHERE year = :y AND gas = :g AND coalesce(spread_pct, 0) >= :m
               ORDER BY spread_pct DESC NULLS LAST, country""",
            y=year,
            g=gas,
            m=min_spread_pct,
        )
        return [ReconciliationOut(**r) for r in rows]

    @app.get("/v1/runs", tags=["data quality"])
    def runs(
        conn: Conn,
        source: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
    ) -> list[RunOut]:
        """Ingestion history with row counts and the quality report of each run."""
        rows = _rows(
            conn,
            """SELECT * FROM ingest.run WHERE (CAST(:s AS text) IS NULL OR source = :s)
               ORDER BY id DESC LIMIT :limit""",
            s=source,
            limit=limit,
        )
        return [RunOut(**r) for r in rows]

    return app


_TITLES = {404: "Not found", 422: "Invalid request", 503: "Service unavailable"}
