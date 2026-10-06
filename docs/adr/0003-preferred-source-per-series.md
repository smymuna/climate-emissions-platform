# ADR 0003: One preferred source per series, not per year

- Status: accepted
- Date: 2026-10-05

## Context

The three sources disagree. For 2022 GHG totals (excluding LULUCF), the gap between the
highest and lowest source is above 10% for 26 of 30 countries, mostly because of
different methods: Eurostat publishes the official UNFCCC inventories, the World Bank
uses EDGAR estimates, and OWID uses yet another compilation.

The API must return one number per country and year for its indicators.

## Decision

- Sources have a priority: Eurostat (official inventory) > World Bank > OWID.
- The preferred source is chosen **per series** (country, sector, gas): the
  highest-priority source with any data for that series supplies every year.
- Raw values from every source stay in `core.emission` and are exposed by
  `/v1/emissions?source=...` and side by side in `/v1/reconciliation`.

## Why not per year

Filling gaps year by year from a lower-priority source looks helpful but creates jumps
caused by method changes, not by emissions changes. A 10% "drop" between two years
could be nothing more than switching from EDGAR to the UNFCCC inventory. Trends and
"change vs 1990" would be wrong.

## Consequences

- If the preferred source lacks a year, that year is missing rather than silently filled.
- The UK has no Eurostat data after Brexit, so its series comes entirely from the World
  Bank. This shows up as `emissions_source` in the API.
