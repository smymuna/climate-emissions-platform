# ADR 0001: Staged pipeline with a landing zone and separate schemas

- Status: accepted
- Date: 2026-10-05

## Context

Three public sources publish emissions data in different formats (JSON-stat, paginated
JSON, a wide CSV), units (kt vs Mt), country codes (EL vs GR vs GRC) and with regional
aggregates mixed into country rows. Sources revise past years. When a number looks
wrong, we need to be able to say where it came from.

## Decision

Every run goes through the same stages:

| Stage | Where | What |
|---|---|---|
| Extract | `sources/*.py` `extract()` | Download, with retries |
| Land | `landing.py` | Raw bytes saved to disk, content-addressed (sha256), before parsing |
| Parse | `sources/*.py` `parse()` | Source format -> `Record` in the source's own codes |
| Validate & clean | `quality/steps.py` | Shared, reusable steps (see ADR 0002) |
| Transform | `quality/steps.py` | Resolve codes, normalise units, sum categories into sectors |
| Load | `db/repository.py` | COPY into a temp table + one set-based upsert |
| Serve | `mart.*` views + `api/` | Application-ready indicators |

PostgreSQL schemas mirror this: `ingest` (runs, landed files, rejected records), `core`
(reference data and facts), `mart` (views the API reads).

Source-specific code is limited to download, parsing and code mappings. All cleaning
rules are shared, so a fourth source needs a parser and two mapping tables.

## Consequences

- Any run can be traced: `ingest.run` -> `ingest.landing_file` (exact bytes) ->
  `ingest.rejected_record` (what was quarantined and why).
- Loads are idempotent: a re-run with unchanged data reports 0 inserted, 0 updated.
  Revised values show up as `rows_updated`.
- A run that fails is still recorded with its error, because the run row is committed
  in its own transaction before loading starts.
- The landing zone is a local directory. In production it would be object storage (S3);
  `LocalLandingStore` is the only class that would change.
