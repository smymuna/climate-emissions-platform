"""Eurostat env_air_gge: greenhouse gas emissions by UNFCCC (CRF) source sector.

Format: JSON-stat 2.0. Values are a sparse object keyed by the flat index of a cell in
an N-dimensional cube; ``id`` and ``size`` give the dimension order and lengths.
Missing cells are either absent or carry status "m". Unit: thousand tonnes CO2e.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any, Final

import httpx

from emissions.quality.steps import IndicatorTarget
from emissions.records import Record
from emissions.reference import BY_EUROSTAT, FIRST_YEAR
from emissions.sources.base import Download, SourceError, get

URL: Final = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_air_gge"

CRF_TO_SECTOR: Final[Mapping[str, str]] = {
    "TOTX4_MEMO": "TOTAL_EXCL_LULUCF",
    "CRF1A1": "ENERGY_INDUSTRIES",
    "CRF1A2": "MANUFACTURING",
    "CRF1A3": "TRANSPORT",
    "CRF1A4": "BUILDINGS_OTHER",
    "CRF1A5": "OTHER",
    "CRF1B": "FUGITIVE",
    "CRF1C": "OTHER",
    "CRF2": "INDUSTRIAL_PROCESSES",
    "CRF3": "AGRICULTURE",
    "CRF4": "LULUCF",
    "CRF5": "WASTE",
    "CRF6": "OTHER",
    # Not a CRF sector, but part of TOTX4_MEMO for countries that report it. Without it
    # sectors don't add up to the total for DK, NO and SE (found by CheckSectorTotals).
    "CRF_INDCO2": "INDIRECT_CO2",
}
GASES: Final = ("GHG", "CO2")


def iter_jsonstat(
    doc: Mapping[str, Any],
) -> Iterator[tuple[dict[str, str], float | None, str | None]]:
    """Yield (coordinates, value, status) for every cell that has a value or a status.

    The flat index is row-major over ``doc["id"]`` with lengths ``doc["size"]``, so the
    last dimension changes fastest.
    """
    try:
        dims: list[str] = doc["id"]
        sizes: list[int] = doc["size"]
        labels = {
            d: {pos: code for code, pos in doc["dimension"][d]["category"]["index"].items()}
            for d in dims
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise SourceError("not a JSON-stat dataset") from exc
    if len(dims) != len(sizes):
        raise SourceError("JSON-stat id and size differ in length")

    values: Mapping[str, float] = doc.get("value") or {}
    status: Mapping[str, str] = doc.get("status") or {}
    for flat in sorted({*values.keys(), *status.keys()}, key=int):
        rest = int(flat)
        coords: dict[str, str] = {}
        for dim, size in zip(reversed(dims), reversed(sizes), strict=True):
            coords[dim] = labels[dim][rest % size]
            rest //= size
        yield coords, values.get(flat), status.get(flat)


class EurostatAdapter:
    code = "eurostat"
    country_map: Mapping[str, str] = {c.eurostat: c.iso2 for c in BY_EUROSTAT.values()}
    indicator_map: Mapping[str, IndicatorTarget] = {
        crf: ("emissions", sector, None) for crf, sector in CRF_TO_SECTOR.items()
    }

    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        params: list[tuple[str, str]] = [
            ("format", "JSON"),
            ("lang", "EN"),
            ("unit", "THS_T"),
            ("sinceTimePeriod", str(FIRST_YEAR)),
        ]
        params += [("src_crf", c) for c in CRF_TO_SECTOR]
        params += [("geo", g) for g in self.country_map]
        # One request per gas keeps each response well under Eurostat's size limits.
        downloads = []
        for gas in GASES:
            r = get(http, URL, params=[*params, ("airpol", gas)])
            downloads.append(Download(str(r.url), r.content, r.headers.get("content-type", "")))
        return downloads

    def parse(self, downloads: list[Download]) -> list[Record]:
        records = []
        for d in downloads:
            try:
                doc = json.loads(d.content)
            except json.JSONDecodeError as exc:
                raise SourceError(f"Eurostat returned invalid JSON from {d.url}") from exc
            for coords, value, _status in iter_jsonstat(doc):
                records.append(
                    Record(
                        source=self.code,
                        country=coords["geo"],
                        indicator=coords["src_crf"],
                        year=int(coords["time"]),
                        value=value,  # status "m" cells have no value -> None
                        unit=coords["unit"],
                        gas=coords["airpol"],
                    )
                )
        return records
