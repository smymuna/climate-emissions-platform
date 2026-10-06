"""Reference data: the countries, sectors, gases and sources the platform models.

Kept in code (and seeded into PostgreSQL by the initial migration) so that every
pipeline stage resolves codes against the same list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Country:
    iso2: str
    iso3: str
    name: str
    eurostat: str
    """Eurostat's geo code. Same as ISO 3166 alpha-2 except Greece (EL) and the UK (UK)."""
    is_eu27: bool


# EU-27, EFTA and the United Kingdom.
COUNTRIES: Final[tuple[Country, ...]] = (
    Country("AT", "AUT", "Austria", "AT", True),
    Country("BE", "BEL", "Belgium", "BE", True),
    Country("BG", "BGR", "Bulgaria", "BG", True),
    Country("HR", "HRV", "Croatia", "HR", True),
    Country("CY", "CYP", "Cyprus", "CY", True),
    Country("CZ", "CZE", "Czechia", "CZ", True),
    Country("DK", "DNK", "Denmark", "DK", True),
    Country("EE", "EST", "Estonia", "EE", True),
    Country("FI", "FIN", "Finland", "FI", True),
    Country("FR", "FRA", "France", "FR", True),
    Country("DE", "DEU", "Germany", "DE", True),
    Country("GR", "GRC", "Greece", "EL", True),
    Country("HU", "HUN", "Hungary", "HU", True),
    Country("IE", "IRL", "Ireland", "IE", True),
    Country("IT", "ITA", "Italy", "IT", True),
    Country("LV", "LVA", "Latvia", "LV", True),
    Country("LT", "LTU", "Lithuania", "LT", True),
    Country("LU", "LUX", "Luxembourg", "LU", True),
    Country("MT", "MLT", "Malta", "MT", True),
    Country("NL", "NLD", "Netherlands", "NL", True),
    Country("PL", "POL", "Poland", "PL", True),
    Country("PT", "PRT", "Portugal", "PT", True),
    Country("RO", "ROU", "Romania", "RO", True),
    Country("SK", "SVK", "Slovakia", "SK", True),
    Country("SI", "SVN", "Slovenia", "SI", True),
    Country("ES", "ESP", "Spain", "ES", True),
    Country("SE", "SWE", "Sweden", "SE", True),
    Country("IS", "ISL", "Iceland", "IS", False),
    Country("LI", "LIE", "Liechtenstein", "LI", False),
    Country("NO", "NOR", "Norway", "NO", False),
    Country("CH", "CHE", "Switzerland", "CH", False),
    Country("GB", "GBR", "United Kingdom", "UK", False),
)

BY_ISO2: Final = {c.iso2: c for c in COUNTRIES}
BY_ISO3: Final = {c.iso3: c for c in COUNTRIES}
BY_EUROSTAT: Final = {c.eurostat: c for c in COUNTRIES}


@dataclass(frozen=True, slots=True)
class Sector:
    code: str
    name: str
    description: str


SECTORS: Final[tuple[Sector, ...]] = (
    Sector(
        "TOTAL_EXCL_LULUCF",
        "Total (excl. LULUCF)",
        "All emissions excluding land use, land-use change and forestry",
    ),
    Sector(
        "ENERGY_INDUSTRIES",
        "Energy industries",
        "Public electricity and heat, refining, solid fuel manufacture (CRF 1.A.1)",
    ),
    Sector(
        "MANUFACTURING",
        "Manufacturing and construction",
        "Fuel combustion in industry and construction (CRF 1.A.2)",
    ),
    Sector("TRANSPORT", "Transport", "Domestic transport fuel combustion (CRF 1.A.3)"),
    Sector(
        "BUILDINGS_OTHER",
        "Buildings and other combustion",
        "Households, commercial, agriculture/forestry/fishing fuel use (CRF 1.A.4)",
    ),
    Sector("FUGITIVE", "Fugitive emissions", "Leaks from fuel production and transport (CRF 1.B)"),
    Sector(
        "INDUSTRIAL_PROCESSES",
        "Industrial processes",
        "Process emissions and product use, e.g. cement, chemicals (CRF 2)",
    ),
    Sector("AGRICULTURE", "Agriculture", "Livestock, soils, manure (CRF 3)"),
    Sector("WASTE", "Waste", "Landfill, wastewater, incineration without energy recovery (CRF 5)"),
    Sector("OTHER", "Other", "Remaining CRF categories (1.A.5, 1.C, 6)"),
    Sector(
        "INDIRECT_CO2",
        "Indirect CO2",
        "CO2 from atmospheric oxidation of methane and NMVOCs; reported by some "
        "countries (e.g. DK, NO, SE) and included in their national totals",
    ),
    Sector("LULUCF", "LULUCF", "Land use, land-use change and forestry; often a net sink (CRF 4)"),
)

SECTOR_CODES: Final = frozenset(s.code for s in SECTORS)
# Sectors whose components add up to TOTAL_EXCL_LULUCF (used by the consistency check).
TOTAL_COMPONENTS: Final = SECTOR_CODES - {"TOTAL_EXCL_LULUCF", "LULUCF"}
# Sectors where a negative value is legitimate (net removals).
MAY_BE_NEGATIVE: Final = frozenset({"LULUCF"})

GASES: Final = ("GHG", "CO2")


@dataclass(frozen=True, slots=True)
class Source:
    code: str
    name: str
    url: str
    licence: str
    priority: int
    """Lower wins when several sources have a value. Official inventories first."""


SOURCES: Final[tuple[Source, ...]] = (
    Source(
        "eurostat",
        "Eurostat: Greenhouse gas emissions by source sector (env_air_gge)",
        "https://ec.europa.eu/eurostat/databrowser/view/env_air_gge/default/table",
        "CC BY 4.0",
        1,
    ),
    Source(
        "worldbank",
        "World Bank World Development Indicators (EDGAR-based GHG series)",
        "https://data.worldbank.org/indicator/EN.GHG.ALL.MT.CE.AR5",
        "CC BY 4.0",
        2,
    ),
    Source(
        "owid",
        "Our World in Data: CO2 and Greenhouse Gas Emissions",
        "https://github.com/owid/co2-data",
        "CC BY 4.0",
        3,
    ),
)

SOURCE_CODES: Final = frozenset(s.code for s in SOURCES)

FIRST_YEAR: Final = 1990
"""Kyoto / EU target base year. Earlier data is out of scope."""
