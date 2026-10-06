"""World Bank Indicators API v2.

Format: paginated JSON. Each page is ``[metadata, [observations]]``; ``metadata.pages``
says how many pages there are. Missing years are ``"value": null``. GHG series are
from EDGAR, in Mt CO2e.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

import httpx

from emissions.quality.steps import IndicatorTarget
from emissions.records import Record
from emissions.reference import BY_ISO3, FIRST_YEAR
from emissions.sources.base import Download, SourceError, get

URL: Final = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"

INDICATORS: Final[Mapping[str, tuple[IndicatorTarget, str]]] = {
    "EN.GHG.ALL.MT.CE.AR5": (("emissions", "TOTAL_EXCL_LULUCF", "GHG"), "Mt CO2e"),
    "EN.GHG.CO2.MT.CE.AR5": (("emissions", "TOTAL_EXCL_LULUCF", "CO2"), "Mt CO2e"),
    "SP.POP.TOTL": (("population", None, None), "persons"),
}
PER_PAGE: Final = 1000
MAX_PAGES: Final = 50


class WorldBankAdapter:
    code = "worldbank"
    country_map: Mapping[str, str] = {iso3: c.iso2 for iso3, c in BY_ISO3.items()}
    indicator_map: Mapping[str, IndicatorTarget] = {k: v[0] for k, v in INDICATORS.items()}

    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]:
        countries = ";".join(self.country_map)
        downloads = []
        for indicator in INDICATORS:
            url = URL.format(countries=countries, indicator=indicator)
            page, pages = 1, 1
            while page <= pages:
                params = {
                    "format": "json",
                    "date": f"{FIRST_YEAR}:{last_year}",
                    "per_page": str(PER_PAGE),
                    "page": str(page),
                }
                r = get(http, url, params=params)
                meta = _page_meta(r.content, r.url)
                pages = min(int(meta.get("pages") or 1), MAX_PAGES)
                downloads.append(Download(str(r.url), r.content, r.headers.get("content-type", "")))
                page += 1
        return downloads

    def parse(self, downloads: list[Download]) -> list[Record]:
        records = []
        for d in downloads:
            doc = json.loads(d.content)
            rows: list[dict[str, Any]] = doc[1] or []
            for row in rows:
                indicator = row["indicator"]["id"]
                unit = INDICATORS[indicator][1] if indicator in INDICATORS else "unknown"
                value = row.get("value")
                records.append(
                    Record(
                        source=self.code,
                        country=row.get("countryiso3code") or row["country"]["id"],
                        indicator=indicator,
                        year=int(row["date"]),
                        value=float(value) if value is not None else None,
                        unit=unit,
                    )
                )
        return records


def _page_meta(content: bytes, url: object) -> dict[str, Any]:
    """The API reports errors as ``[{"message": [...]}]`` with HTTP 200."""
    try:
        doc = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SourceError(f"World Bank returned invalid JSON from {url}") from exc
    if not isinstance(doc, list) or not doc or not isinstance(doc[0], dict):
        raise SourceError(f"unexpected World Bank payload from {url}")
    if "message" in doc[0]:
        raise SourceError(f"World Bank error from {url}: {doc[0]['message']}")
    if len(doc) < 2:
        raise SourceError(f"World Bank page without data array from {url}")
    meta: dict[str, Any] = doc[0]
    return meta
