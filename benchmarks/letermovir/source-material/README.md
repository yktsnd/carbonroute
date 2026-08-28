# Primary source material for the letermovir benchmark

These two files are the Supporting Information of:

> Sorgenfrei et al., "Integrated Life Cycle Assessment Guides Sustainability
> in Synthesis: Antiviral Letermovir as a Case Study", *J. Am. Chem. Soc.*
> **2025**, 147, 40944. DOI: [10.1021/jacs.5c14470](https://doi.org/10.1021/jacs.5c14470)
> — PMC12593353.

Retrieved 2026-08-26 from Europe PMC's supplementary-files endpoint:
`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12593353/supplementaryFiles`
(a stable, versioned REST endpoint — re-fetching it should return the same zip).

- `ja5c14470_si_002.xlsx` — the LCA workbook. `scripts/extract_letermovir_ledger.py`
  reads this file directly to build `benchmarks/letermovir/ledger.yaml`. Its
  `GWP kgCO2-eq/kg` columns are ecoinvent-derived and were never read by that
  script or copied anywhere in this repository — see `../SOURCES.md`.
- `ja5c14470_si_001.pdf` — the SI text (experimental procedures, reaction
  conditions), used to cross-check step names and confirm reagent identities
  while building the ledger.

## Why these are committed

**Licence: CC BY**, confirmed via Europe PMC's own record metadata for
PMC12593353 (`"license": "cc by"`, `"isOpenAccess": "Y"`) — not assumed from
the article being freely readable. CC BY explicitly permits redistribution
with attribution, which is the category this project's rules already accept
for factor data (see `docs/data.md`).

These files are the entire empirical basis of the B2 benchmark. Committing
them means the benchmark stays reproducible even if Europe PMC's endpoint, the
publisher's site, or this session's cached copy all became unavailable —
matching the same reasoning behind `data/raw/` for the API-fetched factor
tables (see `docs/reproducibility.md`). Re-running
`scripts/extract_letermovir_ledger.py` against the committed
`ja5c14470_si_002.xlsx` here, with `--offline`, reproduces
`benchmarks/letermovir/ledger.yaml` byte-for-byte with no network access at
all.

Attribution: Sorgenfrei, K. et al. *J. Am. Chem. Soc.* 2025, 147, 40944.
Licensed CC BY. Not modified from the version retrieved above.
