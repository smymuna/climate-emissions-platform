"""Reusable cleaning and validation steps.

Every step has the same shape: it takes a list of records and the run's quality report,
and returns the records that continue. Steps never silently change a value they are
unsure about; they reject the record and say why. Each source composes the same steps,
with source-specific mappings passed in as configuration.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from emissions.records import Metric, QualityReport, Record
from emissions.reference import MAY_BE_NEGATIVE


class Step(Protocol):
    name: str

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]: ...


def run_steps(steps: Sequence[Step], records: list[Record], report: QualityReport) -> list[Record]:
    for step in steps:
        n_in = len(records)
        records = step(records, report)
        report.record_step(step.name, n_in, len(records))
    return records


# --- missing values -----------------------------------------------------------------------


class DropMissingValues:
    """Drops records without a usable number (None, NaN, inf).

    Sources mark gaps differently (Eurostat status "m", World Bank ``null``, an empty
    CSV cell in OWID). Parsers turn all of them into ``None``, so one rule handles them.
    """

    name = "missing_values"

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        kept = []
        for r in records:
            if r.value is None or not math.isfinite(r.value):
                report.drop("missing_value")
            else:
                kept.append(r)
        return kept


# --- code resolution ----------------------------------------------------------------------


class ResolveCountry:
    """Maps a source's country code to ISO 3166 alpha-2.

    Codes not in the mapping are dropped as out of scope (regional aggregates such as
    "Euro area", or countries outside the modelled set). That is expected, not an error.
    """

    name = "resolve_country"

    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = mapping

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        kept = []
        for r in records:
            iso2 = self._mapping.get(r.country)
            if iso2 is None:
                report.drop("out_of_scope_country")
            else:
                kept.append(replace(r, country=iso2))
        return kept


IndicatorTarget = tuple[Metric, str | None, str | None]
"""(metric, sector, gas). Sector and gas are None for population."""


class ResolveIndicator:
    """Maps a source-native indicator code to (metric, sector, gas)."""

    name = "resolve_indicator"

    def __init__(self, mapping: Mapping[str, IndicatorTarget]) -> None:
        self._mapping = mapping

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        kept = []
        for r in records:
            target = self._mapping.get(r.indicator)
            if target is None:
                report.reject(self.name, f"unknown_indicator:{r.indicator}", r)
                continue
            metric, sector, gas = target
            # Some sources carry the gas as its own field (Eurostat); keep it if set.
            kept.append(replace(r, metric=metric, sector=sector, gas=gas or r.gas))
        return kept


# --- units --------------------------------------------------------------------------------

# Factor to the canonical unit: Mt CO2e for emissions, persons for population.
UNIT_FACTORS: dict[str, float] = {
    "t": 1e-6,
    "kt": 1e-3,
    "THS_T": 1e-3,  # Eurostat "thousand tonnes"
    "Mt": 1.0,
    "Mt CO2e": 1.0,
    "persons": 1.0,
}


class NormaliseUnits:
    """Converts every value to the canonical unit. Unknown units are rejected, not guessed."""

    name = "normalise_units"

    def __init__(self, factors: Mapping[str, float] = UNIT_FACTORS) -> None:
        self._factors = factors

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        kept = []
        for r in records:
            factor = self._factors.get(r.unit)
            if factor is None:
                report.reject(self.name, f"unknown_unit:{r.unit}", r)
                continue
            assert r.value is not None  # guaranteed by DropMissingValues
            canonical = "persons" if r.unit == "persons" else "Mt CO2e"
            kept.append(replace(r, value=r.value * factor, unit=canonical))
        return kept


class DetectUnitErrors:
    """Flags isolated values that are about 1000x off both neighbouring years.

    A value reported in kt but labelled t (or Mt) still looks plausible on its own, but
    it stands out from the same series in the years around it by a factor close to 1000.

    The first version compared each value with the median of its series. On real
    Eurostat data that flagged small, noisy sub-sectors (Luxembourg, Iceland) whose values
    legitimately move by 100x+, and level shifts after a methodology change. Requiring the
    jump on *both* sides, with neighbours that agree with each other, keeps the true
    pattern (a single spike, such as Irish fugitive CO2 in 1999 and 2001) and ignores
    noise and level shifts. The value must also be ~1000x off the series median; otherwise
    the normal year *between* two spikes (Ireland 2000) would be flagged as well.
    Flagged records are rejected for review, not "fixed".
    The first and last year of a series have only one neighbour and are not checked.
    """

    name = "unit_errors"

    def __init__(
        self, low: float = 300.0, high: float = 3000.0, neighbour_tolerance: float = 10.0
    ) -> None:
        self._low = low
        self._high = high
        self._neighbour_tolerance = neighbour_tolerance

    def _off_by_thousand(self, value: float, other: float) -> bool:
        if value == 0 or other == 0:
            return False
        ratio = abs(value / other)
        return self._low <= ratio <= self._high or self._low <= 1 / ratio <= self._high

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        series: dict[tuple[object, ...], list[Record]] = defaultdict(list)
        for r in records:
            series[(r.source, r.country, r.indicator, r.gas)].append(r)

        bad: set[int] = set()
        for members in series.values():
            members.sort(key=lambda r: r.year)
            typical = statistics.median(abs(r.value or 0.0) for r in members)
            for prev, cur, nxt in zip(members, members[1:], members[2:], strict=False):
                v, a, b = cur.value or 0.0, prev.value or 0.0, nxt.value or 0.0
                neighbours_agree = (
                    a != 0
                    and b != 0
                    and max(abs(a), abs(b)) / min(abs(a), abs(b)) <= self._neighbour_tolerance
                )
                if (
                    neighbours_agree
                    and self._off_by_thousand(v, a)
                    and self._off_by_thousand(v, b)
                    # A normal value squeezed between two spikes is off from its
                    # neighbours too, but not from the series' typical level.
                    and self._off_by_thousand(v, typical)
                ):
                    bad.add(id(cur))
                    report.reject(
                        self.name,
                        f"suspected_unit_error:x{abs(v / statistics.mean((a, b))):.3g}",
                        cur,
                    )
        return [r for r in records if id(r) not in bad]


# --- plausibility -------------------------------------------------------------------------


class CheckPlausibility:
    """Rejects values that cannot be right: years outside range, impossible negatives."""

    name = "plausibility"

    def __init__(self, first_year: int, last_year: int) -> None:
        self._first_year = first_year
        self._last_year = last_year

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        kept = []
        for r in records:
            assert r.value is not None
            if r.year < self._first_year:
                report.drop("before_first_year")
            elif r.year > self._last_year:
                report.reject(self.name, "year_in_future", r)
            elif r.value < 0 and r.sector not in MAY_BE_NEGATIVE:
                report.reject(self.name, "negative_value", r)
            elif r.metric == "population" and r.value < 1:
                report.reject(self.name, "zero_population", r)
            else:
                kept.append(r)
        return kept


# --- duplicates ---------------------------------------------------------------------------


class Deduplicate:
    """Removes duplicate observations.

    Duplicates are matched on the source's own identity (source, country, indicator,
    gas, year), before categories are summed into platform sectors.
    Exact duplicates (same key, same value within tolerance) are collapsed to one.
    Conflicting duplicates (same key, different values) are all rejected, because
    there is no way to know which one is right.
    """

    name = "duplicates"

    def __init__(self, rel_tol: float = 1e-9) -> None:
        self._rel_tol = rel_tol

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        groups: dict[tuple[object, ...], list[Record]] = defaultdict(list)
        for r in records:
            groups[r.native_key()].append(r)
        kept = []
        for members in groups.values():
            first = members[0]
            if len(members) == 1:
                kept.append(first)
                continue
            values = [m.value or 0.0 for m in members]
            if all(math.isclose(v, values[0], rel_tol=self._rel_tol) for v in values):
                report.drop("exact_duplicate", len(members) - 1)
                kept.append(first)
            else:
                for m in members:
                    report.reject(self.name, "conflicting_duplicate", m)
        return kept


# --- transformation -----------------------------------------------------------------------


class SumComponents:
    """Collapses several records that map to the same key by adding them up.

    Used where one target sector is built from several source categories (for example
    OTHER = CRF 1.A.5 + 1.C + 6). Only runs after deduplication, so it never adds up
    true duplicates.
    """

    name = "sum_components"

    def __init__(self, applies_to: Callable[[Record], bool]) -> None:
        self._applies_to = applies_to

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        out: list[Record] = []
        sums: dict[tuple[object, ...], Record] = {}
        for r in records:
            if not self._applies_to(r):
                out.append(r)
                continue
            k = r.target_key()
            prev = sums.get(k)
            if prev is None:
                sums[k] = replace(r, indicator=f"sum:{r.indicator}")
            else:
                sums[k] = replace(
                    prev,
                    value=(prev.value or 0) + (r.value or 0),
                    indicator=f"{prev.indicator}+{r.indicator}",
                )
        return out + list(sums.values())


class CheckSectorTotals:
    """Warns when sectors don't add up to the reported total (does not drop data).

    A gap usually means a sector is missing for that year. It is reported, so people
    reading sector shares know the breakdown is incomplete.
    """

    name = "sector_totals"

    def __init__(self, components: frozenset[str], total: str, rel_tol: float = 0.01) -> None:
        self._components = components
        self._total = total
        self._rel_tol = rel_tol

    def __call__(self, records: list[Record], report: QualityReport) -> list[Record]:
        Key = tuple[str, str, str | None, int]
        totals: dict[Key, float] = {}
        parts: dict[Key, float] = defaultdict(float)
        for r in records:
            if r.metric != "emissions":
                continue
            k = (r.source, r.country, r.gas, r.year)
            if r.sector == self._total:
                totals[k] = r.value or 0.0
            elif r.sector in self._components:
                parts[k] += r.value or 0.0
        for k, total in sorted(totals.items(), key=str):
            if k in parts and not math.isclose(parts[k], total, rel_tol=self._rel_tol):
                src, country, gas, year = k
                report.warn(
                    f"{src} {country} {gas} {year}: sectors sum to {parts[k]:.2f} Mt, "
                    f"total is {total:.2f} Mt ({100 * (parts[k] - total) / total:+.1f}%)"
                )
        return records
