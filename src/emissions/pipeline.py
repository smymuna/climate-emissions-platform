"""Runs one source through every stage: extract -> land -> parse -> validate -> load."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import Engine

from emissions.db import repository
from emissions.landing import LocalLandingStore
from emissions.quality.steps import (
    CheckPlausibility,
    CheckSectorTotals,
    Deduplicate,
    DetectUnitErrors,
    DropMissingValues,
    NormaliseUnits,
    ResolveCountry,
    ResolveIndicator,
    Step,
    SumComponents,
    run_steps,
)
from emissions.records import QualityReport
from emissions.reference import FIRST_YEAR, TOTAL_COMPONENTS
from emissions.sources.base import SourceAdapter
from emissions.sources.eurostat import EurostatAdapter
from emissions.sources.owid import OwidAdapter
from emissions.sources.worldbank import WorldBankAdapter

log = logging.getLogger(__name__)

ADAPTERS: dict[str, SourceAdapter] = {
    a.code: a for a in (EurostatAdapter(), WorldBankAdapter(), OwidAdapter())
}


def build_steps(adapter: SourceAdapter, *, last_year: int) -> Sequence[Step]:
    """The validation and transformation stages. Order matters:

    1. drop gaps, 2. resolve codes to the platform's model (so later steps can reason
    about sectors), 3. normalise units, 4. reject impossible values, 5. detect unit
    errors per series, 6. remove duplicates on the source's own identity, 7. sum source
    categories that form one platform sector, 8. check sectors add up to the total.
    """
    return (
        DropMissingValues(),
        ResolveCountry(adapter.country_map),
        ResolveIndicator(adapter.indicator_map),
        NormaliseUnits(),
        CheckPlausibility(first_year=FIRST_YEAR, last_year=last_year),
        DetectUnitErrors(),
        Deduplicate(),
        SumComponents(applies_to=lambda r: r.sector == "OTHER"),
        CheckSectorTotals(TOTAL_COMPONENTS, total="TOTAL_EXCL_LULUCF"),
    )


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: int
    source: str
    parsed: int
    valid: int
    rejected: int
    stats: repository.LoadStats
    report: QualityReport


def run_source(
    adapter: SourceAdapter,
    *,
    engine: Engine,
    http: httpx.Client,
    landing: LocalLandingStore,
    today: date,
) -> RunResult:
    run_id = repository.start_run(engine, adapter.code)
    log.info("run %d: %s started", run_id, adapter.code)
    report: QualityReport | None = None
    try:
        downloads = adapter.extract(http, last_year=today.year)
        landed = [landing.save(adapter.code, d) for d in downloads]
        records = adapter.parse(downloads)
        report = QualityReport()
        clean = run_steps(build_steps(adapter, last_year=today.year), records, report)
        with engine.begin() as conn:
            stats = repository.load(
                conn,
                run_id=run_id,
                records=clean,
                landed=landed,
                report=report,
                records_parsed=len(records),
            )
    except Exception as exc:
        log.exception("run %d: %s failed", run_id, adapter.code)
        repository.fail_run(engine, run_id, f"{type(exc).__name__}: {exc}", report)
        raise
    log.info(
        "run %d: %s parsed=%d valid=%d rejected=%d inserted=%d updated=%d unchanged=%d",
        run_id,
        adapter.code,
        len(records),
        len(clean),
        len(report.rejections),
        stats.inserted,
        stats.updated,
        stats.unchanged,
    )
    return RunResult(
        run_id, adapter.code, len(records), len(clean), len(report.rejections), stats, report
    )
