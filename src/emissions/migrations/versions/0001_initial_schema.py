"""Initial schema: reference tables, emissions facts, ingestion bookkeeping, mart views.

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


UPGRADE = """
CREATE SCHEMA core;
CREATE SCHEMA ingest;
CREATE SCHEMA mart;

-- reference data (synced from emissions/reference.py by `emissions migrate`) ----------

CREATE TABLE core.country (
    iso2          char(2) PRIMARY KEY,
    iso3          char(3) NOT NULL UNIQUE,
    name          text    NOT NULL,
    eurostat_code text    NOT NULL UNIQUE,
    is_eu27       boolean NOT NULL
);

CREATE TABLE core.sector (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL,
    sort_order  smallint NOT NULL
);

CREATE TABLE core.source (
    code     text PRIMARY KEY,
    name     text NOT NULL,
    url      text NOT NULL,
    licence  text NOT NULL,
    priority smallint NOT NULL UNIQUE
);

CREATE TABLE core.reporting_period (
    year         smallint PRIMARY KEY CHECK (year BETWEEN 1900 AND 2100),
    is_base_year boolean GENERATED ALWAYS AS (year = 1990) STORED
);

-- ingestion bookkeeping --------------------------------------------------------------

CREATE TABLE ingest.run (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source           text NOT NULL REFERENCES core.source (code),
    status           text NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    records_parsed   integer,
    records_valid    integer,
    records_rejected integer,
    rows_inserted    integer,
    rows_updated     integer,
    rows_unchanged   integer,
    quality          jsonb,
    error            text
);
CREATE INDEX run_source_started_idx ON ingest.run (source, started_at DESC);

CREATE TABLE ingest.landing_file (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id     bigint NOT NULL REFERENCES ingest.run (id) ON DELETE CASCADE,
    url        text NOT NULL,
    path       text NOT NULL,
    sha256     char(64) NOT NULL,
    size_bytes bigint NOT NULL,
    fetched_at timestamptz NOT NULL
);

CREATE TABLE ingest.rejected_record (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id  bigint NOT NULL REFERENCES ingest.run (id) ON DELETE CASCADE,
    step    text NOT NULL,
    reason  text NOT NULL,
    record  jsonb NOT NULL
);
CREATE INDEX rejected_record_run_idx ON ingest.rejected_record (run_id);

-- facts ------------------------------------------------------------------------------

CREATE TABLE core.emission (
    source        text     NOT NULL REFERENCES core.source (code),
    country       char(2)  NOT NULL REFERENCES core.country (iso2),
    sector        text     NOT NULL REFERENCES core.sector (code),
    gas           text     NOT NULL CHECK (gas IN ('GHG', 'CO2')),
    year          smallint NOT NULL REFERENCES core.reporting_period (year),
    value_mt_co2e numeric(14, 6) NOT NULL,
    run_id        bigint   NOT NULL REFERENCES ingest.run (id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, country, sector, gas, year),
    CHECK (value_mt_co2e >= 0 OR sector = 'LULUCF')
);
-- API queries filter by country/sector/gas across sources and years.
CREATE INDEX emission_lookup_idx ON core.emission (country, sector, gas, year);

CREATE TABLE core.population (
    source     text     NOT NULL REFERENCES core.source (code),
    country    char(2)  NOT NULL REFERENCES core.country (iso2),
    year       smallint NOT NULL REFERENCES core.reporting_period (year),
    persons    bigint   NOT NULL CHECK (persons > 0),
    run_id     bigint   NOT NULL REFERENCES ingest.run (id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, country, year)
);

-- application-ready views ------------------------------------------------------------

-- One source per series (country, sector, gas): the highest-priority source that has
-- any data for it. Choosing per series, not per year, keeps a time series consistent:
-- mixing sources year by year would create artificial jumps.
CREATE VIEW mart.emission_preferred AS
WITH chosen AS (
    SELECT DISTINCT ON (e.country, e.sector, e.gas) e.country, e.sector, e.gas, e.source
    FROM core.emission e
    JOIN core.source s ON s.code = e.source
    ORDER BY e.country, e.sector, e.gas, s.priority
)
SELECT e.country, e.sector, e.gas, e.year, e.value_mt_co2e, e.source
FROM core.emission e
JOIN chosen c USING (country, sector, gas, source);

CREATE VIEW mart.population_preferred AS
WITH chosen AS (
    SELECT DISTINCT ON (p.country) p.country, p.source
    FROM core.population p
    JOIN core.source s ON s.code = p.source
    ORDER BY p.country, s.priority
)
SELECT p.country, p.year, p.persons, p.source
FROM core.population p
JOIN chosen c USING (country, source);

-- Headline indicators per country and year (total GHG excluding LULUCF).
CREATE VIEW mart.country_indicator AS
WITH total AS (
    SELECT country, year, value_mt_co2e, source
    FROM mart.emission_preferred
    WHERE sector = 'TOTAL_EXCL_LULUCF' AND gas = 'GHG'
)
SELECT
    t.country,
    t.year,
    t.value_mt_co2e                                            AS total_ghg_mt,
    t.source                                                   AS emissions_source,
    p.persons                                                  AS population,
    p.source                                                   AS population_source,
    round(t.value_mt_co2e * 1e6 / p.persons, 2)                AS ghg_per_capita_t,
    round(100 * (t.value_mt_co2e / NULLIF(b.value_mt_co2e, 0) - 1), 1)
                                                               AS change_vs_1990_pct,
    round(100 * (t.value_mt_co2e / NULLIF(prev.value_mt_co2e, 0) - 1), 1)
                                                               AS change_vs_prev_year_pct
FROM total t
LEFT JOIN mart.population_preferred p ON p.country = t.country AND p.year = t.year
LEFT JOIN total b    ON b.country = t.country AND b.year = 1990
LEFT JOIN total prev ON prev.country = t.country AND prev.year = t.year - 1;

-- Side-by-side totals from every source, to see where sources disagree.
CREATE VIEW mart.source_reconciliation AS
SELECT
    country,
    gas,
    year,
    max(value_mt_co2e) FILTER (WHERE source = 'eurostat')  AS eurostat_mt,
    max(value_mt_co2e) FILTER (WHERE source = 'worldbank') AS worldbank_mt,
    max(value_mt_co2e) FILTER (WHERE source = 'owid')      AS owid_mt,
    count(*)                                               AS n_sources,
    round(100 * (max(value_mt_co2e) - min(value_mt_co2e)) / NULLIF(avg(value_mt_co2e), 0), 1)
                                                           AS spread_pct
FROM core.emission
WHERE sector = 'TOTAL_EXCL_LULUCF'
GROUP BY country, gas, year;
"""

DOWNGRADE = """
DROP SCHEMA mart CASCADE;
DROP SCHEMA core CASCADE;
DROP SCHEMA ingest CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
