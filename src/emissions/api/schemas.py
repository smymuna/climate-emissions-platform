from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Gas = Literal["GHG", "CO2"]


class CountryOut(BaseModel):
    iso2: str
    iso3: str
    name: str
    is_eu27: bool


class SectorOut(BaseModel):
    code: str
    name: str
    description: str


class SourceOut(BaseModel):
    code: str
    name: str
    url: str
    licence: str
    priority: int = Field(description="Lower wins when several sources have data")


class EmissionOut(BaseModel):
    country: str
    sector: str
    gas: Gas
    year: int
    value_mt_co2e: float
    source: str


class Page[T](BaseModel):
    data: list[T]
    total: int
    limit: int
    offset: int


class IndicatorOut(BaseModel):
    year: int
    total_ghg_mt: float
    emissions_source: str
    population: int | None
    population_source: str | None
    ghg_per_capita_t: float | None
    change_vs_1990_pct: float | None
    change_vs_prev_year_pct: float | None


class CountryIndicators(BaseModel):
    country: CountryOut
    unit: str = "Mt CO2e (total, excl. LULUCF), t CO2e per person"
    series: list[IndicatorOut]


class SectorShareOut(BaseModel):
    sector: str
    name: str
    value_mt_co2e: float
    share_pct: float | None = Field(description="Share of the total excl. LULUCF")
    source: str


class SectorBreakdown(BaseModel):
    country: str
    year: int
    gas: Gas
    total_mt_co2e: float | None
    sectors: list[SectorShareOut]


class ReconciliationOut(BaseModel):
    country: str
    gas: Gas
    year: int
    eurostat_mt: float | None
    worldbank_mt: float | None
    owid_mt: float | None
    n_sources: int
    spread_pct: float | None


class RunOut(BaseModel):
    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_parsed: int | None
    records_valid: int | None
    records_rejected: int | None
    rows_inserted: int | None
    rows_updated: int | None
    rows_unchanged: int | None
    quality: dict[str, Any] | None
    error: str | None
