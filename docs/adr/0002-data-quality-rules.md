# ADR 0002: Data quality rules: drop, reject or warn, never silently fix

- Status: accepted
- Date: 2026-10-05

## Context

Public data has gaps, duplicates, mixed units and occasional errors. Silently "fixing"
values makes the output look clean but untrustworthy; failing a whole run because of
one bad cell makes the platform useless.

## Decision

Each rule has exactly one of three outcomes:

| Outcome | Meaning | Examples |
|---|---|---|
| **drop** (counted) | Expected, not an error | Missing values, regional aggregates, years before 1990, exact duplicates |
| **reject** (stored in `ingest.rejected_record`) | Looks wrong, needs a human | Unknown unit, negative emissions outside LULUCF, conflicting duplicates, suspected unit error |
| **warn** (stored in the run's quality report) | Data is loaded, but users should know | Sectors don't add up to the reported total |

Rules are small classes with one interface (`records, report -> records`), composed by
`pipeline.build_steps`, and tested individually.

## How the unit-error rule was designed (with real data)

A kt value mislabelled as t (or the reverse) is off by ~1000x but still a plausible
number on its own. It only stands out next to the same series in other years.

1. **First version:** flag values ~1000x off the series median. On the live Eurostat
   data it flagged 7 records. Looking at them showed 5 false positives: tiny, noisy
   sub-sectors (Luxembourg "other combustion" moves between 0.1 and 63 kt) and a
   methodology level shift (Iceland agriculture CO2, 0.01 -> 2.4 kt from 1995).
2. **Second version:** flag only a value that is ~1000x off *both* neighbouring years,
   when the neighbours agree with each other. This kept the real pattern (Ireland fugitive
   CO2: 0.02, **38.29**, 0.04, **56.09**, 0.04 kt) but also flagged Ireland 2000,
   the normal value *between* the two spikes.
3. **Final version:** additionally require the value to be ~1000x off the series median.
   Result on live data: exactly the two Irish spikes are rejected.

All three real cases are regression tests in `tests/test_steps.py`.

## The sector-total check found a missing category, then a source inconsistency

- The first run warned 85 times that sectors don't add up for DK, NO and SE (about 2%
  short). Their national totals include **indirect CO2**, which is reported outside the
  CRF sectors. Adding `CRF_INDCO2` as its own sector fixed 83 warnings.
- The remaining 2 warnings are real: Eurostat reports Sweden's 2022 energy-industry
  emissions as 2.6 Mt GHG (9.0 in 2021, 8.4 in 2023) while the national total stays
  smooth. The data is loaded as published; the warning tells users the 2022 sector
  breakdown for Sweden is incomplete.
