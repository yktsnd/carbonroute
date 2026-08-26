# Factor tables

Each CSV here is one emission-factor table. One row is one material.

## Columns

Required: `identifier`, `name`, `gwp_kgCO2e_per_kg`, `source`, `database_version`,
`region`, `retrieved_date`, `uncertainty_class`.
Recommended: `license`, `notes`.

`identifier` is a CAS registry number or an InChIKey; it is the join key.
`uncertainty_class` must be one of the classes in
`src/carbonroute/config/uncertainty.yaml`.

A row with an empty `source` is rejected at load time. Tables from different
providers may be mixed in one directory — provenance and licence are carried
per row precisely so that mixing stays auditable.

## What is deliberately not here

- **No ecoinvent-derived rows.** ecoinvent is licensed commercially and cannot
  be redistributed. Use `--factors` to point at a table you generated locally
  from your own licence.
- **No values without a citable source.** This directory ships empty of numbers
  rather than shipping numbers nobody can check. `examples/factors_illustrative.csv`
  contains obviously-fake values, marked `ILLUSTRATIVE` in the `source` column,
  so the pipeline can be exercised; every report that consumes such a row states
  that its conclusion is not usable.

See `docs/data.md` for how to build a real table.
