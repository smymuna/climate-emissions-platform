"""Our World in Data CO2 and GHG dataset.

Format: one wide CSV (~14 MB, ~80 columns, one row per country-year back to 1750).
Regional aggregates ("World", "European Union (27)") have an empty ``iso_code``.
CO2 and GHG columns are in million tonnes; empty cells are missing values.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Final

import httpx

from emissions.quality.steps import IndicatorTarget
from emissions.records import Record
from emissions.reference import BY_ISO3, FIRST_YEAR
from emissions.sources.base import Download, SourceError, get

URL: Final = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"

COLUMNS: Final[Mapping[str, tuple[IndicatorTarget, str]]] = {
    "total_ghg_excluding_lucf": (("emissions", "TOTAL_EXCL_LULUCF", "GHG"), "Mt"),
    "co2": (("emissions", "TOTAL_EXCL_LULUCF", "CO2"), "Mt"),
    "population": (("population", None, None), "persons"),
}
REQUIRED: Final = {"country", "year", "iso_code", *COLUMNS}


class OwidAdapter:
    code = "owid"
    country_map: Mapping[str, str] = {iso3: c.iso2 for iso3, c in BY_ISO3.items()}
    indicator_map: Mapping[str, IndicatorTarget] = {k: v[0] for k, v in COLUMNS.items()}

    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        r = get(http, URL)
        return [Download(str(r.url), r.content, r.headers.get("content-type", ""))]

    def parse(self, downloads: list[Download]) -> list[Record]:
        records = []
        for d in downloads:
            reader = csv.DictReader(io.StringIO(d.content.decode("utf-8")))
            missing = REQUIRED - set(reader.fieldnames or [])
            if missing:
                raise SourceError(f"OWID CSV is missing columns: {sorted(missing)}")
            for row in reader:
                year = int(row["year"])
                if year < FIRST_YEAR:
                    continue  # 200+ years of history we don't model; skip before parsing
                # Aggregates have no ISO code; keep the name so the drop is traceable.
                country = row["iso_code"] or f"name:{row['country']}"
                for column, (_target, unit) in COLUMNS.items():
                    cell = row[column].strip()
                    records.append(
                        Record(
                            source=self.code,
                            country=country,
                            indicator=column,
                            year=year,
                            value=float(cell) if cell else None,
                            unit=unit,
                        )
                    )
        return records
