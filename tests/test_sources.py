from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from emissions.sources import eurostat, owid, worldbank
from emissions.sources.base import Download, SourceError, get
from emissions.sources.eurostat import EurostatAdapter, iter_jsonstat
from emissions.sources.owid import OwidAdapter
from emissions.sources.worldbank import WorldBankAdapter
from tests.conftest import FIXTURES, fixture_download

# --- Eurostat (JSON-stat) ------------------------------------------------------------------


def test_jsonstat_decodes_flat_index_to_coordinates() -> None:
    doc = json.loads((FIXTURES / "eurostat_env_air_gge_de_el.json").read_bytes())
    cells = {(c["geo"], c["src_crf"], c["airpol"], c["time"]): v for c, v, _ in iter_jsonstat(doc)}
    # Values checked against the Eurostat data browser.
    assert cells[("EL", "TOTX4_MEMO", "GHG", "2022")] == 77584.26
    assert cells[("EL", "TOTX4_MEMO", "CO2", "2022")] == 57580.71


def test_jsonstat_status_m_cells_have_no_value() -> None:
    doc = json.loads((FIXTURES / "eurostat_env_air_gge_de_el.json").read_bytes())
    flagged = [(c, v) for c, v, st in iter_jsonstat(doc) if st == "m"]
    assert flagged
    assert all(v is None for _, v in flagged)
    assert {c["src_crf"] for c, _ in flagged} == {"CRF1C"}


def test_jsonstat_rejects_non_dataset() -> None:
    with pytest.raises(SourceError):
        list(iter_jsonstat({"foo": 1}))


def test_eurostat_parse() -> None:
    records = EurostatAdapter().parse([fixture_download("eurostat_env_air_gge_de_el.json")])
    el = [r for r in records if r.country == "EL" and r.indicator == "TOTX4_MEMO"]
    assert {(r.gas, r.year) for r in el} >= {("GHG", 2022), ("CO2", 2022)}
    assert all(r.unit == "THS_T" for r in records)


def test_eurostat_maps_greece_and_uk_codes() -> None:
    m = EurostatAdapter.country_map
    assert m["EL"] == "GR"
    assert m["UK"] == "GB"
    assert "GR" not in m


@respx.mock
def test_eurostat_extract_requests_one_file_per_gas() -> None:
    body = (FIXTURES / "eurostat_env_air_gge_de_el.json").read_bytes()
    route = respx.get(eurostat.URL).respond(
        content=body, headers={"content-type": "application/json"}
    )
    with httpx.Client() as http:
        downloads = EurostatAdapter().extract(http, last_year=2026)
    assert len(downloads) == 2
    gases = sorted(call.request.url.params["airpol"] for call in route.calls)
    assert gases == ["CO2", "GHG"]
    params = route.calls[0].request.url.params
    assert "EL" in params.get_list("geo")
    assert "CRF_INDCO2" in params.get_list("src_crf")


def test_eurostat_invalid_json() -> None:
    with pytest.raises(SourceError, match="invalid JSON"):
        EurostatAdapter().parse([Download("u", b"<html>", "text/html")])


# --- World Bank (paginated JSON) -----------------------------------------------------------


def test_worldbank_parse_keeps_nulls_as_missing() -> None:
    page = json.loads((FIXTURES / "worldbank_ghg_page1.json").read_bytes())
    page[1][0]["value"] = None
    records = WorldBankAdapter().parse([Download("u", json.dumps(page).encode(), "")])
    assert records[0].value is None
    assert records[1].value is not None
    assert records[0].unit == "Mt CO2e"


@respx.mock
def test_worldbank_follows_pagination() -> None:
    pages = {
        "1": (FIXTURES / "worldbank_ghg_page1.json").read_bytes(),
        "2": (FIXTURES / "worldbank_ghg_page2.json").read_bytes(),
    }

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pages[request.url.params["page"]])

    route = respx.get(url__regex=re.compile(r"https://api\.worldbank\.org/v2/country/.+")).mock(
        side_effect=respond
    )
    with httpx.Client() as http:
        downloads = WorldBankAdapter().extract(http, last_year=2024)
    # 2 pages for each of the 3 indicators
    assert len(downloads) == 2 * len(worldbank.INDICATORS)
    assert route.call_count == 6
    records = WorldBankAdapter().parse(downloads[:2])
    assert {r.country for r in records} == {"DEU", "GRC", "EMU"}  # EMU dropped later


@respx.mock
def test_worldbank_error_payload_with_http_200() -> None:
    respx.get(url__regex=r"https://api\.worldbank\.org/.*").respond(
        json=[{"message": [{"id": "120", "key": "Invalid value"}]}]
    )
    with httpx.Client() as http, pytest.raises(SourceError, match="Invalid value"):
        WorldBankAdapter().extract(http, last_year=2024)


# --- OWID (wide CSV) -----------------------------------------------------------------------


def test_owid_parse_skips_pre_1990_and_names_aggregates() -> None:
    records = OwidAdapter().parse([fixture_download("owid_co2_sample.csv", "text/csv")])
    assert min(r.year for r in records) == 1990
    countries = {r.country for r in records}
    assert "DEU" in countries
    assert "name:World" in countries
    assert "name:Kosovo" in countries  # no ISO code in OWID
    de_2022 = {r.indicator: r.value for r in records if r.country == "DEU" and r.year == 2022}
    assert de_2022["total_ghg_excluding_lucf"] == pytest.approx(706.251)


def test_owid_missing_column_fails_loudly() -> None:
    csv = b"country,year,iso_code,co2\nGermany,2022,DEU,1\n"
    with pytest.raises(SourceError, match="missing columns"):
        OwidAdapter().parse([Download("u", csv, "text/csv")])


def test_owid_empty_cells_are_missing() -> None:
    csv = (
        b"country,year,iso_code,co2,total_ghg_excluding_lucf,population\n"
        b"Germany,2022,DEU,,706.2,84086227\n"
    )
    records = OwidAdapter().parse([Download("u", csv, "text/csv")])
    assert {r.indicator: r.value for r in records}["co2"] is None


def test_owid_url_is_the_published_dataset() -> None:
    assert owid.URL.endswith("owid-co2-data.csv")


# --- HTTP retries --------------------------------------------------------------------------


@respx.mock
def test_get_retries_then_succeeds() -> None:
    route = respx.get("https://x.test/a").mock(
        side_effect=[httpx.Response(503), httpx.ConnectError("boom"), httpx.Response(200)]
    )
    sleeps: list[float] = []
    with httpx.Client() as http:
        assert get(http, "https://x.test/a", sleep=sleeps.append).status_code == 200
    assert route.call_count == 3
    assert sleeps == [2.0, 4.0]


@respx.mock
def test_get_gives_up_and_does_not_retry_client_errors() -> None:
    respx.get("https://x.test/a").respond(503)
    respx.get("https://x.test/b").respond(404)
    with httpx.Client() as http:
        with pytest.raises(SourceError, match="503"):
            get(http, "https://x.test/a", retries=2, sleep=lambda _: None)
        with pytest.raises(SourceError, match="404"):
            get(http, "https://x.test/b", sleep=lambda _: pytest.fail("must not retry"))
