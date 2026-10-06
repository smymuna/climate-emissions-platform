"""Writes to PostgreSQL: reference data sync, run bookkeeping and fact loading."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from emissions.landing import LandedFile
from emissions.records import QualityReport, Record
from emissions.reference import COUNTRIES, SECTORS, SOURCES

MAX_REJECTIONS_STORED = 10_000


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def sync_reference_data(conn: Connection) -> None:
    """Upsert countries, sectors and sources from ``emissions.reference``. Idempotent."""
    conn.execute(
        text("""
            INSERT INTO core.country (iso2, iso3, name, eurostat_code, is_eu27)
            VALUES (:iso2, :iso3, :name, :eurostat, :is_eu27)
            ON CONFLICT (iso2) DO UPDATE SET
                iso3 = EXCLUDED.iso3, name = EXCLUDED.name,
                eurostat_code = EXCLUDED.eurostat_code, is_eu27 = EXCLUDED.is_eu27
        """),
        [
            {
                "iso2": c.iso2,
                "iso3": c.iso3,
                "name": c.name,
                "eurostat": c.eurostat,
                "is_eu27": c.is_eu27,
            }
            for c in COUNTRIES
        ],
    )
    conn.execute(
        text("""
            INSERT INTO core.sector (code, name, description, sort_order)
            VALUES (:code, :name, :description, :sort_order)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name, description = EXCLUDED.description,
                sort_order = EXCLUDED.sort_order
        """),
        [
            {"code": s.code, "name": s.name, "description": s.description, "sort_order": i}
            for i, s in enumerate(SECTORS)
        ],
    )
    # Priorities are unique; defer the check by clearing them first so they can be swapped.
    conn.execute(text("UPDATE core.source SET priority = -priority"))
    conn.execute(
        text("""
            INSERT INTO core.source (code, name, url, licence, priority)
            VALUES (:code, :name, :url, :licence, :priority)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name, url = EXCLUDED.url,
                licence = EXCLUDED.licence, priority = EXCLUDED.priority
        """),
        [
            {
                "code": s.code,
                "name": s.name,
                "url": s.url,
                "licence": s.licence,
                "priority": s.priority,
            }
            for s in SOURCES
        ],
    )


def start_run(engine: Engine, source: str) -> int:
    """Create the run row in its own transaction, so a failed load is still recorded."""
    with engine.begin() as conn:
        run_id: int = conn.execute(
            text("INSERT INTO ingest.run (source) VALUES (:source) RETURNING id"),
            {"source": source},
        ).scalar_one()
    return run_id


def fail_run(engine: Engine, run_id: int, error: str, report: QualityReport | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE ingest.run
                SET status = 'failed', finished_at = now(), error = :error,
                    quality = CAST(:quality AS jsonb)
                WHERE id = :id
            """),
            {
                "id": run_id,
                "error": error[:4000],
                "quality": json.dumps(report.summary()) if report else None,
            },
        )


@dataclass(frozen=True, slots=True)
class LoadStats:
    inserted: int
    updated: int
    unchanged: int


def load(
    conn: Connection,
    *,
    run_id: int,
    records: Sequence[Record],
    landed: Sequence[LandedFile],
    report: QualityReport,
    records_parsed: int,
) -> LoadStats:
    """Load one run's clean records and bookkeeping in the caller's transaction."""
    _store_landing_files(conn, run_id, landed)
    _store_rejections(conn, run_id, report)

    emissions = [r for r in records if r.metric == "emissions"]
    population = [r for r in records if r.metric == "population"]
    years = sorted({r.year for r in records})
    if years:
        conn.execute(
            text("INSERT INTO core.reporting_period (year) VALUES (:y) ON CONFLICT DO NOTHING"),
            [{"y": y} for y in years],
        )

    e = _merge(
        conn,
        temp_table="tmp_emission",
        temp_ddl="source text, country char(2), sector text, gas text, year smallint, "
        "value_mt_co2e numeric(14, 6)",
        columns=("source", "country", "sector", "gas", "year", "value_mt_co2e"),
        rows=[(r.source, r.country, r.sector, r.gas, r.year, r.value) for r in emissions],
        merge_sql="""
            INSERT INTO core.emission AS t
                (source, country, sector, gas, year, value_mt_co2e, run_id)
            SELECT source, country, sector, gas, year, value_mt_co2e, :run_id FROM tmp_emission
            ON CONFLICT (source, country, sector, gas, year) DO UPDATE
            SET value_mt_co2e = EXCLUDED.value_mt_co2e, run_id = EXCLUDED.run_id,
                updated_at = now()
            WHERE t.value_mt_co2e IS DISTINCT FROM EXCLUDED.value_mt_co2e
            RETURNING (xmax = 0) AS inserted
        """,
        run_id=run_id,
    )
    p = _merge(
        conn,
        temp_table="tmp_population",
        temp_ddl="source text, country char(2), year smallint, persons bigint",
        columns=("source", "country", "year", "persons"),
        rows=[(r.source, r.country, r.year, round(r.value or 0)) for r in population],
        merge_sql="""
            INSERT INTO core.population AS t (source, country, year, persons, run_id)
            SELECT source, country, year, persons, :run_id FROM tmp_population
            ON CONFLICT (source, country, year) DO UPDATE
            SET persons = EXCLUDED.persons, run_id = EXCLUDED.run_id, updated_at = now()
            WHERE t.persons IS DISTINCT FROM EXCLUDED.persons
            RETURNING (xmax = 0) AS inserted
        """,
        run_id=run_id,
    )
    stats = LoadStats(
        inserted=e.inserted + p.inserted,
        updated=e.updated + p.updated,
        unchanged=e.unchanged + p.unchanged,
    )
    conn.execute(
        text("""
            UPDATE ingest.run SET
                status = 'succeeded', finished_at = now(),
                records_parsed = :parsed, records_valid = :valid,
                records_rejected = :rejected, rows_inserted = :ins, rows_updated = :upd,
                rows_unchanged = :unch, quality = CAST(:quality AS jsonb)
            WHERE id = :id
        """),
        {
            "id": run_id,
            "parsed": records_parsed,
            "valid": len(records),
            "rejected": len(report.rejections),
            "ins": stats.inserted,
            "upd": stats.updated,
            "unch": stats.unchanged,
            "quality": json.dumps(report.summary()),
        },
    )
    return stats


def _merge(
    conn: Connection,
    *,
    temp_table: str,
    temp_ddl: str,
    columns: Sequence[str],
    rows: Sequence[tuple[Any, ...]],
    merge_sql: str,
    run_id: int,
) -> LoadStats:
    """COPY rows into a temp table, then upsert in one statement.

    COPY is far faster than row-by-row INSERTs, and a single set-based upsert lets
    PostgreSQL report what changed: ``xmax = 0`` is true for freshly inserted rows;
    rows that already had the same value are skipped by the WHERE clause and not returned.
    """
    if not rows:
        return LoadStats(0, 0, 0)
    conn.execute(text(f"CREATE TEMP TABLE {temp_table} ({temp_ddl}) ON COMMIT DROP"))
    raw = conn.connection.driver_connection
    assert raw is not None
    with (
        raw.cursor() as cur,
        cur.copy(f"COPY {temp_table} ({', '.join(columns)}) FROM STDIN") as cp,
    ):
        for row in rows:
            cp.write_row(row)
    returned = conn.execute(text(merge_sql), {"run_id": run_id}).scalars().all()
    inserted = sum(1 for r in returned if r)
    updated = len(returned) - inserted
    return LoadStats(inserted, updated, len(rows) - inserted - updated)


def _store_landing_files(conn: Connection, run_id: int, landed: Sequence[LandedFile]) -> None:
    if not landed:
        return
    conn.execute(
        text("""
            INSERT INTO ingest.landing_file (run_id, url, path, sha256, size_bytes, fetched_at)
            VALUES (:run_id, :url, :path, :sha256, :size, :fetched_at)
        """),
        [
            {
                "run_id": run_id,
                "url": f.url,
                "path": str(f.path),
                "sha256": f.sha256,
                "size": f.size_bytes,
                "fetched_at": f.fetched_at,
            }
            for f in landed
        ],
    )


def _store_rejections(conn: Connection, run_id: int, report: QualityReport) -> None:
    rows = report.rejections[:MAX_REJECTIONS_STORED]
    if len(report.rejections) > MAX_REJECTIONS_STORED:
        report.warn(f"only the first {MAX_REJECTIONS_STORED} rejected records were stored")
    if not rows:
        return
    conn.execute(
        text("""
            INSERT INTO ingest.rejected_record (run_id, step, reason, record)
            VALUES (:run_id, :step, :reason, CAST(:record AS jsonb))
        """),
        [
            {
                "run_id": run_id,
                "step": r.step,
                "reason": r.reason,
                "record": json.dumps(r.record.as_dict()),
            }
            for r in rows
        ],
    )
