"""The record that flows through the pipeline, and the per-run quality report."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Metric = Literal["emissions", "population"]


@dataclass(frozen=True, slots=True)
class Record:
    """One observation. Starts in source-native form and is normalised step by step.

    After parsing: ``country``, ``indicator`` and ``unit`` are the source's own codes.
    After the resolve steps: ``country`` is ISO 3166 alpha-2, and ``metric`` / ``sector`` /
    ``gas`` are set from the indicator mapping. After unit normalisation, emissions are in
    Mt CO2e and population in persons.
    """

    source: str
    country: str
    indicator: str
    year: int
    value: float | None
    unit: str
    metric: Metric | None = None
    sector: str | None = None
    gas: str | None = None

    def native_key(self) -> tuple[str, str, str, str | None, int]:
        """Identity in the source's own terms. Two records with this key are duplicates."""
        return (self.source, self.country, self.indicator, self.gas, self.year)

    def target_key(self) -> tuple[str, str, str, str | None, str | None, int]:
        """Identity in the platform's model. Several source categories can share one."""
        return (self.source, self.country, self.metric or "", self.sector, self.gas, self.year)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Rejection:
    step: str
    reason: str
    record: Record


@dataclass
class QualityReport:
    """What each step did to the data during one run. Stored with the run as JSON."""

    counts: list[dict[str, int | str]] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    rejections: list[Rejection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def record_step(self, step: str, n_in: int, n_out: int) -> None:
        self.counts.append({"step": step, "in": n_in, "out": n_out})

    def drop(self, reason: str, n: int = 1) -> None:
        """Expected removals that are not data errors (missing values, out-of-scope rows)."""
        self.dropped[reason] += n

    def reject(self, step: str, reason: str, record: Record) -> None:
        """Records that look wrong. They are quarantined, not loaded."""
        self.rejections.append(Rejection(step, reason, record))

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def summary(self) -> dict[str, Any]:
        return {
            "steps": self.counts,
            "dropped": dict(self.dropped),
            "rejected": dict(Counter(f"{r.step}:{r.reason}" for r in self.rejections)),
            "warnings": self.warnings[:100],
            "warnings_total": len(self.warnings),
        }
