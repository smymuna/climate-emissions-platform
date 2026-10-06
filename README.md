# Climate Emissions Platform

[![CI](https://github.com/smymuna/climate-emissions-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/smymuna/climate-emissions-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![License](https://img.shields.io/badge/license-MIT-green)

**A backend platform that ingests three public climate and emissions sources, cleans and
normalises them, and serves standardised greenhouse gas indicators for 32 European
countries through a REST API.**

Sources: **Eurostat** (official EU inventories, JSON-stat), the **World Bank** (EDGAR
estimates, paginated JSON API) and **Our World in Data** (a 14 MB wide CSV). They differ
in format, unit, country codes and method. The platform turns them into one model of
countries, sectors, reporting periods and emissions in PostgreSQL. It keeps every
source's raw values and records exactly what was dropped, rejected or flagged in each
run.

![Dashboard showing Germany's emissions falling from about 1,250 Mt in 1990 to 650 Mt in 2024, a sector breakdown, and a ranking of European countries by change since 1990](docs/dashboard.jpg)

*The React dashboard on real data. It also has a source comparison view, a data-quality
panel and dark mode.*

```console
$ docker compose up --build
$ curl localhost:8000/v1/countries/DE/indicators?from_year=2024
{"country": {"iso2": "DE", "name": "Germany", ...},
 "series": [{"year": 2024, "total_ghg_mt": 649.77, "emissions_source": "eurostat",
             "ghg_per_capita_t": 7.78, "change_vs_1990_pct": -48.1,
             "change_vs_prev_year_pct": -3.0, ...}]}
```

## What it does

- **Ingests** about 59,000 records per full run (1990–2024, 32 countries, 12 sectors, GHG and CO2)
  and loads about 31,000 clean rows, in about 10 seconds.
- **Validates and cleans** with reusable components: missing values, out-of-scope
  aggregates, unit normalisation, unit-error detection, impossible values, duplicates,
  sector consistency.
- **Serves** headline indicators (total, per capita, change vs 1990 and vs the previous year),
  sector breakdowns with shares, raw values per source, a **cross-source reconciliation**
  view, and the ingestion history with each run's quality report.

## Architecture

```mermaid
flowchart LR
    subgraph Sources
        ES[Eurostat<br/>JSON-stat, kt]
        WB[World Bank<br/>paged JSON, Mt]
        OW[OWID<br/>CSV, Mt]
    end
    ES & WB & OW --> X[Extract<br/>retries + backoff]
    X --> L[(Landing zone<br/>raw bytes, sha256)]
    L --> P[Parse<br/>per-source adapter]
    P --> Q[Validate & clean<br/>shared quality steps]
    Q --> T[Transform<br/>codes, units, sectors]
    T --> DB[(PostgreSQL<br/>ingest / core / mart)]
    DB --> API[FastAPI]
```

| PostgreSQL schema | Contents |
|---|---|
| `ingest` | `run` (status, row counts, quality report as JSON), `landing_file`, `rejected_record` |
| `core` | `country`, `sector`, `source`, `reporting_period`, `emission`, `population` |
| `mart` | Views: `emission_preferred`, `country_indicator`, `source_reconciliation` |

Only download, parsing and code mappings are source-specific
(`src/emissions/sources/`). All cleaning rules are shared
(`src/emissions/quality/steps.py`). See [ADR 0001](docs/adr/0001-staged-pipeline.md).

## Data quality

Each rule either **drops** (expected, counted), **rejects** (stored for review) or
**warns** (loaded, flagged). Nothing is silently corrected.
See [ADR 0002](docs/adr/0002-data-quality-rules.md).

| Problem in the real data | How it's handled |
|---|---|
| Eurostat reports kt, the others Mt | `NormaliseUnits` converts to Mt CO2e; unknown units are rejected |
| Greece is `EL` in Eurostat, `GRC` elsewhere; UK is `UK` | Per-source country maps to ISO alpha-2 |
| "Euro area", "World", "European Union (27)" mixed into country rows | Dropped as out of scope (counted, not errors) |
| Gaps: status `m`, `null`, empty CSV cells | One `DropMissingValues` rule after parsing |
| A value reported in the wrong unit (~1000x off) | `DetectUnitErrors`: isolated spike vs both neighbours *and* the series median |
| The same observation twice with different values | Both rejected as `conflicting_duplicate` |
| Several source categories form one sector | `SumComponents`, after deduplication |
| Sectors that don't add up to the national total | Warning in the run's quality report |

**What the checks found in the live data**

- **Indirect CO2:** the first run warned 85 times that sectors didn't add up for Denmark,
  Norway and Sweden. These countries include indirect CO2 in their totals, reported outside
  the usual sectors. Adding it as a sector fixed 83 of the warnings.
- **Sweden 2022:** Eurostat reports energy-industry emissions of 2.6 Mt (9.0 in 2021,
  8.4 in 2023) while the national total stays smooth. The data is loaded as published,
  with a warning.
- **Ireland:** fugitive CO2 values of 38.29 and 56.09 kt in 1999 and 2001, surrounded by
  values around 0.02–0.04 kt. These are rejected as suspected unit errors. The first
  version of the detector also flagged noisy small series; the ADR describes how it was
  refined on the real data.

**Sources disagree.** For 2022, the gap between sources is above 10% for 26 of 30
countries (average 18.8%), because they use different methods. The API therefore uses
one source per series instead of mixing sources year by year
([ADR 0003](docs/adr/0003-preferred-source-per-series.md)), and exposes the comparison:

```console
$ curl "localhost:8000/v1/reconciliation?year=2022&min_spread_pct=20"
[{"country": "IE", "eurostat_mt": 59.01, "worldbank_mt": 63.86, "owid_mt": 39.38, "spread_pct": 45.3}, ...]
```

## Frontend

`frontend/`: a React + TypeScript dashboard (Vite, TanStack Query). See
[frontend/README.md](frontend/README.md).

- Pick a country to see its total and per-capita emissions, change since 1990 and vs the previous
  year, and a sector breakdown. A ranking shows every country's change since 1990.
- **Compare all three sources** overlays Eurostat, World Bank and OWID for one country,
  which makes the method differences visible.
- The data-quality panel shows the latest ingestion runs and where sources disagree.
- Charts are plain SVG components with hover and keyboard tooltips, a data-table view
  for each chart, and dark mode. The source colours were checked for colour-vision
  deficiency in both themes.
- The view is in the URL (`?country=FR`), so links can be shared.

## API

OpenAPI docs at `/docs`. Errors use RFC 9457 `application/problem+json`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/countries`, `/v1/sectors`, `/v1/sources` | Reference data |
| `GET /v1/emissions?country=&sector=&gas=&source=&from_year=&to_year=` | Values, paged; `source=preferred` or a source code |
| `GET /v1/countries/{code}/indicators` | Total, per capita, change vs 1990 / previous year |
| `GET /v1/countries/{code}/sectors?year=` | Sector breakdown with shares |
| `GET /v1/reconciliation?year=&min_spread_pct=` | Side-by-side totals from every source |
| `GET /v1/runs` | Ingestion history with quality reports |
| `GET /healthz`, `/readyz` | Liveness / readiness (database reachable) |

Country codes accept ISO alpha-2 or alpha-3 in any case (`de`, `DEU`).

## Running it

**Docker** (PostgreSQL + migrations + ingestion + API):

```bash
docker compose up --build        # API on http://localhost:8000/docs
```

**Locally:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export EMISSIONS_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/emissions
emissions migrate                    # schema (Alembic) + reference data
emissions ingest                     # all sources; or --source eurostat
emissions serve                      # API on :8000
```

```text
eurostat   run 1: parsed  28944  dropped   1928  rejected    2  loaded  24567  (+24567 new, 0 changed, 0 unchanged)  warnings 2
worldbank  run 2: parsed   3456  dropped    134  rejected    0  loaded   3322  (+3322 new, 0 changed, 0 unchanged)  warnings 0
owid       run 3: parsed  26649  dropped  23289  rejected    0  loaded   3360  (+3360 new, 0 changed, 0 unchanged)  warnings 0
```

Running `ingest` again reports `+0 new, 0 changed`: loads are idempotent.

## Deployment

Free-tier hosting, all in the EU where possible:

```mermaid
flowchart LR
    U[Browser] --> V[Vercel<br/>React frontend]
    V -->|HTTPS, CORS| R[Render, Frankfurt<br/>FastAPI Docker image]
    R --> N[(Neon PostgreSQL<br/>eu-central-1)]
    G[GitHub Actions<br/>monthly ingest] --> N
```

| Piece | Where | Config |
|---|---|---|
| Database | [Neon](https://neon.tech), free plan | Connection string → secret `EMISSIONS_DATABASE_URL` |
| Data refresh | GitHub Actions | [`.github/workflows/ingest.yml`](.github/workflows/ingest.yml): runs migrations + ingestion monthly or on demand |
| API | [Render](https://render.com), free web service | [`render.yaml`](render.yaml) blueprint, Docker, health check on `/healthz` |
| Frontend | [Vercel](https://vercel.com), free plan | Root directory `frontend`, env `VITE_API_URL` = the Render URL |

Setup, in order:

1. **Neon:** create a project (region Frankfurt) and copy the connection string.
2. **GitHub:** add it as the repository secret `EMISSIONS_DATABASE_URL`, then run the
   *Ingest* workflow from the Actions tab. It creates the schema and loads the data.
3. **Render:** *New → Blueprint*, pick this repository, and set `EMISSIONS_DATABASE_URL`
   (same string) and `EMISSIONS_CORS_ORIGINS` (for example `["https://<your-app>.vercel.app"]`).
4. **Vercel:** import the repository, set the root directory to `frontend` and
   `VITE_API_URL` to the Render URL, then deploy.

The free Render plan sleeps after 15 minutes without traffic. The first request then
takes up to a minute, and the frontend shows a message while the API wakes up.

## Engineering

- **Tests:** 52 backend tests, about 92% coverage. Unit tests for every quality rule, using the real
  Ireland, Luxembourg, Iceland and Sweden cases as regression tests. Parser tests run on
  captured real responses. HTTP retry tests use `respx`. The **integration tests run on
  real PostgreSQL**: full pipeline, idempotent re-runs, change detection, failed-run
  recording, SQL views and API.
- **Loading:** `COPY` into a temp table, then one `INSERT ... ON CONFLICT DO UPDATE ...
  WHERE value IS DISTINCT FROM` that reports inserted / updated / unchanged rows.
- **Schema:** Alembic migrations; constraints in the database (foreign keys, `CHECK` on
  gas and on negative values outside LULUCF).
- **Quality:** `ruff`, `mypy --strict`; CI on GitHub Actions with a PostgreSQL service
  container, then a Docker build and smoke test. The frontend job runs `oxlint`, 19 Vitest
  tests and a type-checked production build.

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/emissions_test pytest --cov
```

## Limitations

- Totals exclude LULUCF. Sector detail exists only for Eurostat; World Bank and OWID
  provide national totals.
- The preferred source per series can differ between countries (UK: World Bank, because
  Eurostat has no UK data; Liechtenstein: OWID).
- Revisions overwrite the stored value (the run that changed it is recorded). Keeping
  every vintage would need a bitemporal table.
- The landing zone is a local folder. In production this would be object storage.

## Data and licences

Eurostat (env_air_gge), World Bank WDI and Our World in Data are published under CC BY 4.0.
Code: MIT, see [LICENSE](LICENSE).
