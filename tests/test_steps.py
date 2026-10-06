from __future__ import annotations

import math

import pytest

from emissions.quality.steps import (
    CheckPlausibility,
    CheckSectorTotals,
    Deduplicate,
    DetectUnitErrors,
    DropMissingValues,
    NormaliseUnits,
    ResolveCountry,
    ResolveIndicator,
    SumComponents,
    run_steps,
)
from emissions.records import QualityReport
from emissions.reference import TOTAL_COMPONENTS
from tests.conftest import rec


@pytest.fixture
def report() -> QualityReport:
    return QualityReport()


def test_drop_missing_values(report: QualityReport) -> None:
    out = DropMissingValues()([rec(1.0), rec(None), rec(math.nan), rec(math.inf)], report)
    assert [r.value for r in out] == [1.0]
    assert report.dropped["missing_value"] == 3


def test_resolve_country_drops_aggregates_as_out_of_scope(report: QualityReport) -> None:
    step = ResolveCountry({"DEU": "DE", "GRC": "GR"})
    out = step([rec(1, country="DEU"), rec(1, country="EMU"), rec(1, country="GRC")], report)
    assert [r.country for r in out] == ["DE", "GR"]
    assert report.dropped["out_of_scope_country"] == 1
    assert report.rejections == []  # aggregates are expected, not errors


def test_resolve_indicator_rejects_unknown_and_keeps_source_gas(report: QualityReport) -> None:
    step = ResolveIndicator({"CRF3": ("emissions", "AGRICULTURE", None)})
    out = step([rec(1, indicator="CRF3", gas="CO2"), rec(1, indicator="??")], report)
    assert (out[0].sector, out[0].gas) == ("AGRICULTURE", "CO2")
    assert [r.reason for r in report.rejections] == ["unknown_indicator:??"]


@pytest.mark.parametrize(
    ("value", "unit", "expected", "canonical"),
    [
        (749266.42, "THS_T", 749.26642, "Mt CO2e"),
        (5_000_000, "t", 5.0, "Mt CO2e"),
        (12.5, "Mt", 12.5, "Mt CO2e"),
        (83_000_000, "persons", 83_000_000, "persons"),
    ],
)
def test_normalise_units(
    report: QualityReport, value: float, unit: str, expected: float, canonical: str
) -> None:
    (out,) = NormaliseUnits()([rec(value, unit=unit)], report)
    assert out.value == pytest.approx(expected)
    assert out.unit == canonical


def test_normalise_units_rejects_unknown_unit(report: QualityReport) -> None:
    assert NormaliseUnits()([rec(1, unit="lbs")], report) == []
    assert report.rejections[0].reason == "unknown_unit:lbs"


def _series(values: dict[int, float], **kw: object) -> list:  # type: ignore[type-arg]
    return [rec(v, year=y, **kw) for y, v in values.items()]  # type: ignore[arg-type]


def test_unit_errors_catches_isolated_spikes_real_ireland_case(report: QualityReport) -> None:
    # Eurostat IE CRF1B CO2 (kt): two isolated ~1000x spikes in 1999 and 2001.
    ie = {
        1996: 0.01,
        1997: 0.02,
        1998: 0.02,
        1999: 38.29,
        2000: 0.04,
        2001: 56.09,
        2002: 0.04,
        2003: 0.04,
        2004: 0.05,
    }
    out = DetectUnitErrors()(_series(ie), report)
    assert sorted(r.record.year for r in report.rejections) == [1999, 2001]
    assert 2000 in {r.year for r in out}  # the normal year between the spikes survives


def test_unit_errors_ignores_noisy_small_series_real_luxembourg_case(
    report: QualityReport,
) -> None:
    # Eurostat LU CRF1A5 GHG (kt): moves 3 -> 63 -> 0.13 without any unit problem.
    lu = {
        1990: 3.14,
        1991: 3.15,
        1992: 26.9,
        1993: 23.76,
        1998: 34.24,
        1999: 63.33,
        2000: 12.26,
        2003: 3.28,
        2004: 0.13,
        2005: 0.13,
    }
    assert len(DetectUnitErrors()(_series(lu), report)) == len(lu)
    assert report.rejections == []


def test_unit_errors_ignores_level_shift_real_iceland_case(report: QualityReport) -> None:
    # Eurostat IS CRF3 CO2 (kt): methodology change in 1995, not an error.
    is_ = {
        1990: 0.02,
        1991: 0.01,
        1992: 0.03,
        1993: 0.02,
        1994: 0.01,
        1995: 2.44,
        1996: 2.65,
        1997: 2.56,
    }
    DetectUnitErrors()(_series(is_), report)
    assert report.rejections == []


def test_unit_errors_series_are_per_indicator(report: QualityReport) -> None:
    # Different indicators may differ by 1000x legitimately; they must not be compared.
    records = _series({2020: 0.001, 2021: 0.001, 2022: 0.001}, indicator="CRF1C")
    records += _series({2020: 1.0, 2021: 1.0, 2022: 1.0}, indicator="CRF6")
    assert len(DetectUnitErrors()(records, report)) == 6


def test_plausibility(report: QualityReport) -> None:
    step = CheckPlausibility(first_year=1990, last_year=2026)
    records = [
        rec(1, year=1989),
        rec(1, year=2027),
        rec(-5, sector="TRANSPORT"),
        rec(-40, sector="LULUCF"),
        rec(0, metric="population", sector=None, gas=None),
        rec(10),
    ]
    out = step(records, report)
    assert [(r.sector, r.value) for r in out] == [("LULUCF", -40), ("TOTAL_EXCL_LULUCF", 10)]
    assert sorted(r.reason for r in report.rejections) == [
        "negative_value",
        "year_in_future",
        "zero_population",
    ]
    assert report.dropped["before_first_year"] == 1


def test_deduplicate_collapses_exact_and_rejects_conflicts(report: QualityReport) -> None:
    records = [rec(5.0), rec(5.0), rec(7.0, year=2021), rec(8.0, year=2021), rec(1.0, year=2020)]
    out = Deduplicate()(records, report)
    assert sorted(r.year for r in out) == [2020, 2022]
    assert report.dropped["exact_duplicate"] == 1
    assert [r.reason for r in report.rejections] == ["conflicting_duplicate"] * 2


def test_deduplicate_uses_native_identity_not_target_sector(report: QualityReport) -> None:
    # CRF1A5, 1C and 6 all map to OTHER; they are different observations, not duplicates.
    records = [rec(1.0, indicator=i, sector="OTHER") for i in ("CRF1A5", "CRF1C", "CRF6")]
    assert len(Deduplicate()(records, report)) == 3
    assert report.rejections == []


def test_sum_components(report: QualityReport) -> None:
    records = [rec(v, indicator=i, sector="OTHER") for i, v in (("CRF1A5", 1.5), ("CRF6", 2.0))]
    records.append(rec(10.0, indicator="CRF3", sector="AGRICULTURE"))
    out = SumComponents(applies_to=lambda r: r.sector == "OTHER")(records, report)
    by_sector = {r.sector: r for r in out}
    assert by_sector["OTHER"].value == pytest.approx(3.5)
    assert by_sector["OTHER"].indicator == "sum:CRF1A5+CRF6"
    assert by_sector["AGRICULTURE"].value == 10.0


def test_sector_totals_warns_on_gap_real_sweden_case(report: QualityReport) -> None:
    # Eurostat SE GHG 2022: energy industries drop to 2.6 Mt while the total stays smooth.
    parts = {
        "ENERGY_INDUSTRIES": 2.5839,
        "MANUFACTURING": 5.84808,
        "TRANSPORT": 14.27813,
        "BUILDINGS_OTHER": 1.9392,
        "FUGITIVE": 0.07966,
        "INDUSTRIAL_PROCESSES": 6.86191,
        "AGRICULTURE": 6.41268,
        "WASTE": 1.10325,
    }
    records = [rec(v, sector=s) for s, v in parts.items()]
    records += [rec(45.16804, sector="TOTAL_EXCL_LULUCF"), rec(-43.1, sector="LULUCF")]
    out = CheckSectorTotals(TOTAL_COMPONENTS, total="TOTAL_EXCL_LULUCF")(records, report)
    assert len(out) == len(records)  # warns only, never drops
    assert len(report.warnings) == 1
    assert "-13.4%" in report.warnings[0]


def test_sector_totals_silent_when_consistent(report: QualityReport) -> None:
    records = [
        rec(2.0, sector="TRANSPORT"),
        rec(3.0, sector="WASTE"),
        rec(5.0, sector="TOTAL_EXCL_LULUCF"),
    ]
    CheckSectorTotals(TOTAL_COMPONENTS, total="TOTAL_EXCL_LULUCF")(records, report)
    assert report.warnings == []


def test_run_steps_records_counts_in_order(report: QualityReport) -> None:
    run_steps([DropMissingValues(), Deduplicate()], [rec(1), rec(None), rec(1)], report)
    assert report.counts == [
        {"step": "missing_values", "in": 3, "out": 2},
        {"step": "duplicates", "in": 2, "out": 1},
    ]
    summary = report.summary()
    assert summary["dropped"] == {"missing_value": 1, "exact_duplicate": 1}
