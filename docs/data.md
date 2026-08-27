# Factor tables

An emission factor table is a CSV file. One row is one material. One or
more of these files are loaded into a `FactorTable` (`src/carbonroute/resolve.py`)
and used to look up the GWP of every material a route consumes.

`data/factors/` ships empty at v0 — see
["Why there are no factors in `data/factors/`"](#why-there-are-no-factors-in-datafactors)
below. `examples/factors_illustrative.csv` is a fake table for exercising
the pipeline only; do not use it as a starting point for a real table
beyond copying its column layout.

## Column reference

Required columns, in the order `resolve.py` expects them to exist (order in
the file itself does not matter, only that all of these are present):

| Column | Meaning |
| --- | --- |
| `identifier` | A CAS registry number (e.g. `108-88-3`) or an InChIKey (three dash-separated blocks, first block 14 uppercase letters). This is the primary join key against a route's materials. CAS is checked with its mod-10 check digit on the ledger side; the factor table does not re-validate it, so get it right. |
| `name` | The material's common name. Used as a fallback join key, normalized (lower-cased, whitespace-collapsed) when a route material has no CAS. |
| `gwp_kgCO2e_per_kg` | Cradle-to-gate global warming potential, kg CO2e per kg of material, at the boundary and GWP method the ledger declares. Must be a non-negative number. |
| `source` | Where the number came from. **Never empty** — a row with a blank `source` is rejected at load time (spec section 6.2, enforced in `FactorTable.load_file`). Rows whose source begins with the literal string `ILLUSTRATIVE` are flagged as fabricated placeholders throughout the tool (`Factor.is_illustrative`) and any report that consumes one is required to say so. |
| `database_version` | The version or edition of the source you pulled the number from. Use whatever the source itself calls its version; `n/a` if it genuinely has none. |
| `region` | The geographic scope the value applies to (e.g. `GLO`, `RER`, `JP`). Use the source's own region code. |
| `retrieved_date` | The date (ISO 8601, `YYYY-MM-DD`) you pulled this value, not the date the source was published. Sources get revised; this is what lets someone check whether your copy is stale. |
| `uncertainty_class` | One of the classes defined in `src/carbonroute/config/uncertainty.yaml` (`primary`, `supplier`, `background_db`, `literature`, `structural_estimate`, `analogue_substitute`, `assumption`, `unknown`). Determines the geometric standard deviation used for this row in the Monte Carlo. An unrecognized or blank value falls back to `unknown`, the widest class. |

Recommended (optional) columns:

| Column | Meaning |
| --- | --- |
| `license` | The license the source value is distributed under (e.g. `CC-BY-4.0`, `CC0-1.0`, or a plain-text note like "public domain, US EPA"). See below — this is what makes mixing sources auditable. |
| `notes` | Anything a reader needs to interpret the row: what process the value represents, known caveats, why you chose it over an alternative. |
| `inchikey` | The InChIKey for the substance, from a structure database. It joins on structure rather than on a registry number, so it survives the CAS ambiguity that plagues names like "hexane". A row that carries one is indexed under it as well as under `identifier`, so a ledger written against structures still finds it. |
| `gsd` | A geometric standard deviation **published by the source for this very row**. When present it overrides the class default from `config/uncertainty.yaml` in the Monte Carlo, which is the right precedence: the class defaults are uncalibrated placeholders, and a dispersion that arrived with the data is the one number here that is not a guess. Must be >= 1.0, where 1.0 means "treat as exact". **Leave it empty unless the source published something you can convert** — an empty cell means "the source was silent, fall back to the class", and inventing a value here is the same sin as inventing the factor. If the source gives a relative standard deviation (coefficient of variation `cv`), convert with `gsd = exp(sqrt(log(1 + cv**2)))` and say so in `notes`. |

Any other column is preserved by CSV readers in general but is not read by
`carbonroute`; the loader only requires the columns above to exist and does
not reject extra ones.

## Provenance classes

`uncertainty_class` is not a free-text field in spirit even though it is
one in the CSV — it must match a key in `config/uncertainty.yaml`, which is
what ties a row to a dispersion width in the Monte Carlo
(`docs/uncertainty.md` explains the model). The classes, from narrowest to
widest as currently configured, are:

- `primary` — measured on the actual process, by the actual operator.
- `supplier` — provided by the material's producer, not independently
  checked.
- `background_db` — a generic cradle-to-gate value from a background LCI
  database (e.g. USLCI, an EF-format dataset).
- `literature` — a published study whose process and vintage only partly
  match your material.
- `structural_estimate` — predicted from molecular structure by a model
  (the v0 tool has no such model wired in; this class exists for future use,
  see `docs/spec-ja.md` section 15.1).
- `analogue_substitute` — borrowed from a different but chemically similar
  material because nothing more specific was found.
- `assumption` — a number the analyst declared outright, such as a grid
  factor with no per-material meaning.
- `unknown` — provenance not stated; also the fallback for any value your
  table does not name explicitly.

Pick the narrowest class that honestly describes where the number came
from. A wrong class in the optimistic direction (calling a background-database
value `primary`, for instance) understates uncertainty and can flip a
ranking that should have been reported as indeterminate.

## License handling per row

Different rows in the same table are allowed to come from different
sources with different licenses — `FactorTable.load` happily merges
multiple CSV files, and even a single file can mix provenance row by row.
This is deliberate: it is normal to have USLCI-derived values for some
solvents and a supplier-declared value for one specialty reagent in the
same table. What makes that mixing safe is that license and source are
tracked *per row*, not once per file, so a consumer of the table (or of a
lock file built from it) can tell exactly what they are and are not allowed
to redistribute, row by row.

Practical rule: if you cannot write a real value in the `license` column
for a row, you should question whether you are allowed to have that row in
a table you intend to share. Values you generated yourself from public,
uncopyrightable facts can reasonably carry a permissive license of your own
choosing (`CC0-1.0`, `CC-BY-4.0`); values transcribed from someone else's
database carry whatever *that* database's license says, not your choice.

## Why ecoinvent rows must never be committed

ecoinvent is distributed under a commercial license that does not permit
redistributing its data. This is a real, common, and useful background
database — it is also one this repository cannot ship any part of,
directly or reformatted, without violating that license and forfeiting the
"public data only" property the whole default pipeline depends on (spec
section 2, section 13).

Concretely:

- Do not commit a CSV containing values read from ecoinvent, in this
  repository or in a fork you intend to redistribute.
- If you have an ecoinvent license, use it — but keep the resulting table
  outside the repository (or, if the repository is private and never
  redistributed, be certain your license terms actually permit that) and
  pass it in explicitly with `--factors /path/to/your/ecoinvent_table.csv`.
  `carbonroute` treats any factor table as an adapter you supply; nothing
  about the CLI or the default `data/factors/` lookup requires or prefers
  a commercial source.
- A lock file built from such a table (`carbonroute lock`) still records
  the table's path and SHA-256 hash, not its contents, so sharing a lock
  file does not leak the values themselves — but it does reveal that a
  particular file was used, so treat the lock file with the same care you'd
  give the table it was built from if that fact itself is sensitive.

## Building your own table

1. **Pick a source you can cite and that permits at least the use you
   intend.** Reasonable public starting points include USLCI, an
   Environmental Footprint (EF) reference dataset, a peer-reviewed LCA
   paper's supplementary data, or a supplier's published Environmental
   Product Declaration. Read the license before you start transcribing.
2. **Decide the boundary and GWP method you are pulling values at.** They
   need to match (or be defensibly comparable to) the ledger's
   `assumptions.boundary` and `assumptions.gwp_method` — `carbonroute`
   does not convert between GWP methods or system boundaries for you.
3. **For each material, record one row** with the columns above filled in
   honestly: the source's own identifier converted to CAS or InChIKey if it
   is not already one, the value as published (do not silently reinterpret
   units — the required unit is kg CO2e per kg of material), the source's
   version/edition, its region, today's date as `retrieved_date`, and the
   narrowest `uncertainty_class` you can defend.
4. **Fill `license` per row**, even if every row in your first table
   shares the same source and license — it costs nothing now and pays off
   the day you add a second source.
5. **Validate the table loads.** `carbonroute resolve route.yaml --factors
   your_table.csv --show-missing` will fail loudly (via `FactorTableError`)
   on a missing required column, a blank `source`, a non-numeric or
   negative GWP value, or two rows disagreeing on the value for the same
   identifier. Fix the underlying disagreement rather than deleting one of
   the rows unless you are sure which is right.
6. **Do not fill gaps with values you cannot cite.** An unresolved material
   is reported as unresolved (`resolve --show-missing`, or as `missing` in
   a `RouteResult`); that is the intended behavior, not a defect to paper
   over. Spec section 13: "do not silently fill missing values with a
   default; report a gap as a gap."
7. **Commit the table only if its license and your redistribution rights
   allow it** — see the ecoinvent warning above; the same reasoning applies
   to any other license that forbids redistribution.

## When two tables disagree

Nothing stops two sources from giving different numbers for the same substance,
and in practice they do: ADEME and the US LCI Database differ by a factor of
1.42 on hydrochloric acid, both openly licensed, both citable.

The loader does not refuse to run, and it does not pick quietly. It keeps the
value from the first table in **sorted path order** — so the outcome never
depends on the order a caller happened to pass its arguments — records the
alternative as a `Conflict`, and every report that touches the table prints a
"Sources disagree" section showing both values, both sources and the ratio. The
lock file pins which one was used.

A disagreement is not a defect in either source. It measures how far openly
available data spreads for the same material, which is one of the questions
this project set out to answer. Suppressing it would throw that away. If you
want a particular source to win, load only that source, or order the file names
so it sorts first.

An identical duplicate is not a conflict and is ignored.

## Synonym tables: the names a ledger uses

A ledger written by a chemist says `2-Me-THF`. A factor table says
`2-methyltetrahydrofuran`. Nothing connects them, so the material goes
unresolved and its mass drops silently out of the comparison. On the letermovir
benchmark that one name was worth 20.65 kg per functional unit — 16% of the
differing mass — and the factor for it was already in the table.

`data/synonyms/*.csv` closes that gap. Columns: `alias`, `identifier`,
`inchikey`, `source`, `retrieved_date`, `notes`. A row without a `source` is
rejected: an alias is an identity claim about chemistry, and an unchecked one
silently attributes one substance's footprint to another.

`scripts/resolve_synonyms.py` generates candidate rows. It takes the names a
ledger failed to resolve, asks PubChem what they are, and records the CID and
InChIKey that support each mapping. A name that resolves to more than one
compound, or whose CAS fails its check digit, is reported and left out — as are
compound numbers (`15`, `8a (8)`), bespoke catalysts and placeholders like
`Catalyst`, none of which name a substance at all.

Where the exact string is not in PubChem's index, the script retries **purely
orthographic** variants: whitespace collapsed around hyphens, spaces turned into
hyphens or removed, the last internal hyphen dropped. That is punctuation, not
chemistry — nothing is changed about a substituent, a locant or a parent — and
the variant that actually matched is written into `notes` so a reviewer can see
what was asked. `2-Me-THF` resolves through `2-MeTHF`; `2- picoline` through
`2-picoline`.

Lookup order is exact identifier, then synonym, then name. An exact CAS always
wins, so a synonym can never override a material that already resolved.

**Review the generated file before committing it.** This is the one place in the
project where a machine proposes a claim about chemistry, and it is the one
place a wrong row does its damage quietly.
