# Sources — letermovir benchmark (B2)

This directory implements `benchmarks/README.md` section **B2**. Everything
here is generated from the public record only; nothing ecoinvent-derived is
present. See `scripts/extract_letermovir_ledger.py` for the generator and its
docstring, which repeats the licensing constraint in full.

## Citation

> Sorgenfrei, F. A. et al. "Integrated Life Cycle Assessment Guides
> Sustainability in Synthesis: Antiviral Letermovir as a Case Study."
> *J. Am. Chem. Soc.* **2025**, *147*, 40944–40957.
> DOI: [10.1021/jacs.5c14470](https://doi.org/10.1021/jacs.5c14470)
> PMC: [PMC12593353](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12593353/)

Licence: **CC BY** (confirmed via Europe PMC record metadata for PMC12593353:
`"license": "cc by"`, `"isOpenAccess": "Y"`). The article and its
Supporting Information are open access under that licence.

Retrieval route (record this exactly — it is how a third party reproduces
the input):

```
https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12593353/supplementaryFiles
```

This Europe PMC endpoint returns a zip (`si.zip`) containing:
- `ja5c14470_si_001.pdf` — the SI text (used only to sanity-check step names
  and conditions; no numeric value in the ledger below was taken from it).
- `ja5c14470_si_002.xlsx` — **the LCA workbook**, the sole numeric source
  for this benchmark's ledger.

## Licensing constraint — restated

The workbook's authors computed their GWP figures with **ecoinvent 3.10**, a
commercially licensed background database. This repository must never
redistribute ecoinvent-derived emission factors. The copy of the workbook
in the SI has every `GWP kgCO2-eq[/kg]` cell cached as `0` (macro not
evaluated on save), so there was nothing non-zero to accidentally copy, but
the extraction script does not read those columns, or the `A. Databases`
sheet, under any circumstance — by construction, not by luck. The ledger
below carries only: material names, masses already back-calculated by the
paper's authors to their functional unit (the `Mass Stoich` column), step
descriptions, and (where the sheet gives one) a step's published yield,
recorded only as a comment.

## Workbook sheets used

- `2.1. Merck LCA FU` → ledger route **`merck`**
  (workbook title cell A1: `"Letermovir 1 kg accumulative"`)
- `1.1 LCA This Work FU` → ledger route **`denovo`**
  (workbook title cell A1: `"Letermovir 1kg cumulative NCCR"`)

Both sheets contain **exactly seven main-route steps and nothing else** —
verified by scanning every row from the last `Product` row to the sheet's
`max_row` (144 for the Merck sheet, 1103 for the denovo sheet — the latter's
high `max_row` is empty formatting, not data) and confirming no further
content beyond a single trailing text note on the denovo sheet
(`"Stoichiometry is taking by the relative values"`, row 108, not a data
row). Neither sheet continues into a reconstructed sub-synthesis of a
precursor or catalyst — those live only in `B.1`–`B.4`, which this benchmark
does not touch at all. **Nothing was left out of either main-route sheet.**

## Row ranges — every step, every material, traceable to a cell

Column layout differs between the two sheets:

- `2.1. Merck LCA FU`: A name · B given stoichiometry · C unit ·
  **D = Mass Stoich (kg)** · E unit · F/G GWP (ignored, see above) ·
  H/I a 4-row per-step **role legend** (see below).
- `1.1 LCA This Work FU`: A name · B given stoichiometry · C unit ·
  D/E moles (optional) · **F = Mass Stoich (kg)** · G unit ·
  H/I GWP (ignored, see above).

| Route | Step | Header row (`Step N`) | `Reactants` row | material rows | `Solvents` row | material rows | `Yield` row | `Product` row |
|---|---|---|---|---|---|---|---|---|
| merck | 1 | 3  | 5  | 6–8   | 9   | 10–11 | — | 13 |
| merck | 2 | 19 | 21 | 22–24 | 25  | 26–27 | — | 29 |
| merck | 3 | 33 | 35 | 36–38 | 39  | 40    | — | 43 |
| merck | 4 | 47 | 49 | 50–54 | 55  | 56–57 | — | 59 |
| merck | 5 | 63 | 65 | 66–70 | 71  | 72–73 | — | 75 |
| merck | 6 | 79 | 81 | 82–84 | 87  | 88–89 | — | 91 |
| merck | 7 | 95 | 97 | 98–101| 103 | 104–106 | — | 107 |
| denovo | 1 | 3  | 5  | 6–8  | 9  | 10–11 | 12 | 13 |
| denovo | 2 | 17 | 19 | 20–21| 23 | 24    | 26 | 27 |
| denovo | 3 | 31 | 33 | 34–35| 37 | 38    | 40 | 41 |
| denovo | 4 | 45 | 47 | 48–52| 53 | 54–55 | 56 | 57 |
| denovo | 5 | 61 | 63 | 64–67| 69 | 70    | 72 | 73 |
| denovo | 6 | 77 | 79 | 80–83| 85 | 86–88 | 89 | 90 |
| denovo | 7 | 94 | 96 | 97–100| 102| 103–105| — | 106 |

A `Product` row is a step's output, not an input — it is never emitted as a
ledger `input`. It re-appears as the next step's first `Reactants` row
(carried forward by name/number, e.g. Merck step 1's product `15`
(row 14) becomes step 2's first reactant (row 22)); that re-appearance *is*
captured, at the row where it is consumed.

Material counts and total charged mass (sum of `mass_kg` over every input,
every step — not a GWP figure, just an inventory-completeness check a
reader can redo from the ledger):

| Route | Steps | Materials (input rows) | Total charged mass (kg per 1 kg product) |
|---|---|---|---|
| merck  | 7 | 40 | 153.1284 |
| denovo | 7 | 37 | 134.5068 |

## Role mapping

Schema roles: `solvent`, `reactant`, `reagent`, `catalyst`, `auxiliary`.
Both sheets only ever use three plain column-A section headings inside a
step block: `Reactants`, `Solvents`, `Product`. There is **no** column-A
heading literally reading `Catalysts`, `Starting Materials`, or `Reagents`
anywhere in either sheet — those exact words appear only in a side table
described below, and only on the Merck sheet. The mapping actually used:

- `Solvents` section → **`solvent`**, uniformly, on both sheets. Unambiguous.
- `Product` section → not emitted (see above).
- `Reactants` section → handled differently per sheet, because the two
  sheets carry different amounts of information:

### Merck sheet (`2.1. Merck LCA FU`) — the authors' own H/I legend

Every step's `Reactants` block is immediately followed, in the same rows but
columns **H** (label) and **I** (formula), by a 4-row legend the paper's
authors built into the spreadsheet itself:

```
H<r>   "Starting Materials"   I<r>   =SUM(G<a>,G<b>,...)
H<r+1> "Reagents"             I<r+1> =SUM(G<c>:G<d>)   (or 0, or a single =G<x>)
H<r+2> "Catalysts"            I<r+2> =G<y>              (or 0)
H<r+3> "Solvent"              I<r+3> =SUM(G<e>:G<f>)
```
(`r` = the `Reactants` header row.) The **I-column formula's cell
references** (never their computed *value* — those are the ecoinvent-derived
GWP figures this project must not touch) name exactly which material rows
belong to which of the four categories. The extraction script
(`scripts/extract_letermovir_ledger.py`, function `parse_merck_sheet`) parses
those formula strings with a regex over `G\d+` / `G\d+:G\d+` and maps:

| Legend label | ledger `role` |
|---|---|
| Starting Materials | `reactant` |
| Reagents | `reagent` |
| Catalysts | `catalyst` |
| Solvent | `solvent` (redundant with, and always consistent with, the `Solvents` heading) |

This is the paper authors' own classification, recovered mechanically —
no chemistry judgement of ours enters into it. It is why, for example, DMAP
and PCl5 (step 3/4) are `reagent` rather than `catalyst` in this ledger even
though a chemist might call DMAP catalytic in other contexts: the authors'
own spreadsheet formula puts it in the `Reagents` sum, and this ledger
follows that, not chemical intuition. Verified by hand against all 7 Merck
steps before trusting the script's output.

### Denovo sheet (`1.1 LCA This Work FU`) — no legend, coarser rule

This sheet has no H/I legend (its H/I columns are the real
`GWP kgCO2-eq/kg` / `GWP kgCO2-eq` columns, ignored per the licensing
constraint). With no finer heading to key off, the mapping used is:

- Everything under `Reactants` → **`reactant`**, *except*:
- A row whose material name is **exactly** `"Catalyst"` (case-insensitive)
  → **`catalyst`**. This is the sheet's own placeholder name for an
  undisclosed chiral catalyst (step 6 of both routes uses this same literal
  placeholder name), so classifying it as `catalyst` is reading the sheet's
  own label, not inferring chemistry.

**This is a known, acknowledged coarsening**, stated explicitly per the
task's instruction to say so rather than silently invent finer structure:
workup/quench chemicals that a chemist would usually call `reagent` (e.g.
denovo step 1's `"1 M NaOH"`, step 4's `"aq. NaHCO3"`/`"TFAA"`/`"NEt3"`, step
7's `"Na2HPO4"`/`"NaOH"`/`"Acetone"`) are recorded as `role: reactant` in
this ledger, because the sheet gives no sub-heading that would justify
calling them anything else without guessing. No row on this sheet was
mapped to `auxiliary`; that role exists in the schema but nothing in either
sheet's structure singled out a case for it.

## `yield: 1.0` — why, on every step, both routes

Every `Step N` block's `Mass Stoich` (Merck: column D; denovo: column F) is
already the mass **back-calculated by the paper's own authors to their
functional unit** of 1 kg letermovir out (workbook titles: `"Letermovir 1 kg
accumulative"` / `"Letermovir 1kg cumulative NCCR"`). Confirmed on Merck
step 1: every material's `Mass Stoich` (D) equals its `Given Stoichiometry`
(B) multiplied by one shared scale factor `$D$14/$B$14` — the same
factor for every row in that step, i.e. straight linear scaling to the
functional unit, already applied.

If this ledger additionally applied carbonroute's own step-yield mass
conversion (dividing upstream masses by the cumulative yield from that step
on), the yield loss already baked into these masses would be counted a
second time, inflating every upstream mass. So `yield: 1.0` is set on every
step of both routes, and is not a placeholder — it is the only value
consistent with masses that are already FU-scaled.

Each step's **published** yield, exactly as printed in the workbook, is
recorded only as a YAML comment beside that step (never applied to mass):

| Route | Step | Published yield (workbook `Yield` row) |
|---|---|---|
| denovo | 1 | 0.99 (row 12) |
| denovo | 2 | 0.99 (row 26) |
| denovo | 3 | 0.99 (row 40) |
| denovo | 4 | 0.97 (row 56) |
| denovo | 5 | 0.80 (row 72) |
| denovo | 6 | 0.62775 (row 89) — the sheet itself labels this one `"Overall Yield"` in column C, not just `"Yield"`; recorded verbatim, not interpreted. |
| denovo | 7 | not given — no `Yield` row exists in this step's block. |
| merck  | 1–7 | not given — the Merck sheet has **no** `Yield` row anywhere; it scales purely via the `Given Stoichiometry` → `Mass Stoich` ratio described above. |

## `electricity_kWh: 0.0` — why

The workbook's inventory is material-only: there is no energy/electricity
line item anywhere in either route sheet. `electricity_kWh: 0.0` is set on
every step, with a comment, rather than estimating a process-energy figure
from outside the published record — the task instructions are explicit that
no energy figure should be invented, and this ledger honors that literally.
Correspondingly, `assumptions.grid_factor` is a documented, cited zero
(`value_kgCO2e_per_kWh: 0.0`, `source` explaining it is unused by
construction) rather than an uncited placeholder value.

## Assumptions block

- `functional_unit: {mass_kg: 1.0, basis: product}` — matches the workbook's
  own functional unit exactly (1 kg letermovir).
- `boundary: cradle-to-gate` — matches the paper's stated scope.
- `gwp_method: {name: IPCC-AR6, horizon_years: 100, feedbacks: false}` — a
  **label of intent**, not a claim of reproducing the paper's own
  calculation chain. The paper itself reports **GWP100a per IPCC 2021 (AR6)**
  (stated in its Methods). This benchmark's own numbers, once someone
  attaches a public factor table to this ledger, will come from that public
  table, not from the paper's ecoinvent-based run — see "Cannot be
  reproduced" below.
- `solvent_recovery_default: 0.0`, `waste_treatment: excluded` — the
  workbook gives no solvent-recovery fraction anywhere in either route
  sheet, so no recovery is assumed; this matches a straightforward reading
  of "as-charged" mass.

## CAS resolution log

Method: PubChem PUG REST, `compound/name/<name>/cids/JSON` then
`compound/cid/<cid>/synonyms/JSON`, first CAS-shaped synonym
(`\d{2,7}-\d{2}-\d`) validated against `carbonroute.schema.cas_checksum_ok`.
Rate-limited to ≤5 req/s. Cached locally (scratchpad only, not committed —
see script `--cas-cache`). A name is **never** sent to PubChem, and is
recorded as `cas: null` directly, when it is a bare compound number/label
used by the workbook to refer to a carried-over intermediate (e.g. `"15"`,
`"11a"`, `"8a (8)"`) or the sheet's own bespoke placeholder catalyst name
(`"Catalyst"`) — per the task instructions, guessing a structure for either
would be silent data corruption, not resolution.

Of 48 distinct material names across both sheets: **31 resolved** to a
validated CAS, **10 were never queried** (bare compound numbers / the
`"Catalyst"` placeholder — correctly `cas: null` by construction), and
**7 were queried and did not resolve** (also `cas: null`, honestly, not
guessed).

| Name | Result | Detail |
|---|---|---|
| `(t-Bu)3P-Pd G2` | null (unresolved) | No CID for the literal name. |
| `1 M NaOH` | **1310-73-2** | via normalized query `NaOH` |
| `11a` | null (skipped) | compound label |
| `15` | null (skipped) | compound label |
| `16` | null (skipped) | compound label |
| `17` | null (skipped) | compound label |
| `2` | null (skipped) | compound label |
| `2- picoline` | **109-06-8** | via normalized query `2-picoline` |
| `2-Me-THF` | null (unresolved) | No CID for the literal abbreviation. |
| `2-amino-3-fluorobenzoic acid` | **825-22-9** | direct |
| `2-bromo-6-fluoroaniline` | **65896-11-9** | direct |
| `2-isothiocyanato-1-methoxy-4-(trifluoromethyl)benzene` | **1360934-34-4** | direct |
| `3` | null (skipped) | compound label |
| `4` | null (skipped) | compound label |
| `5` | null (skipped) | compound label |
| `8a (8)` | null (skipped) | compound label |
| `AcCl` | **75-36-5** | direct |
| `Acetone` | **67-64-1** | direct |
| `BH3SMe3` | null (unresolved) | No CID for the literal formula-name. |
| `Catalyst` | null (skipped) | bespoke/undisclosed catalyst placeholder |
| `DMAP` | **1122-58-3** | direct |
| `EDC HCl` | **25952-53-8** | direct |
| `Et3N` | **121-44-8** | direct |
| `EtOAc` | **141-78-6** | direct |
| `H2O` | **7732-18-5** | direct |
| `K3PO4` | **7778-53-2** | direct |
| `KOH` | **1310-58-3** | direct |
| `Ketene Acetal` | null (unresolved) | resolves to exactly 1 CID (19867143) but it has no CAS-shaped synonym — a generic class name, not one substance. |
| `MTBE` | **1634-04-4** | direct |
| `Magnesium (monoperoxyphthalate)2` | null (unresolved) | No CID for the literal name. |
| `MeOH` | **67-56-1** | direct |
| `Methyl acrylate` | **96-33-3** | direct |
| `NEt3` | **121-44-8** | direct |
| `Na2HPO4` | **7558-79-4** | direct |
| `NaH2PO4` | **7558-80-7** | direct |
| `NaOH` | **1310-73-2** | direct |
| `PCl5` | **10026-13-8** | direct |
| `Pentane` | **109-66-0** | direct |
| `Phenyl chloroformate` | **1885-14-9** | direct |
| `Salicylic Acid` | **69-72-7** | direct |
| `Sec Butanol` | null (unresolved) | No CID for `"Sec Butanol"` as spaced/capitalized in the sheet. |
| `TFAA` | **407-25-0** | direct |
| `Toluene` | **108-88-3** | direct |
| `aq. NaHCO3` | **144-55-8** | via normalized query `NaHCO3` (leading `"aq. "` stripped) |
| `citric acid` | **77-92-9** | direct |
| `iProAc` | **108-21-4** | direct |
| `piperazine bis hydrochloride` | null (unresolved) | No CID for the literal name. |
| `toluene` | **108-88-3** | direct |

For the record only — **not** applied to the ledger, because applying it
would mean substituting our own chemical-nomenclature knowledge for the
literal workbook text, which the task instructions say not to do — a human
reviewer checking PubChem manually can confirm several of the "unresolved"
names are standard abbreviations/spellings of compounds PubChem does index
under a different string (CAS check digits verified before listing here):
`2-Me-THF` ~ 2-methyltetrahydrofuran (CID 7301, CAS 96-47-9); `BH3SMe3` ~
borane dimethyl sulfide complex (CID 9833925, CAS 13292-87-0); `Sec Butanol`
~ sec-butanol / 2-butanol, racemic (CID 6568, CAS 78-92-2); `piperazine bis
hydrochloride` ~ piperazine dihydrochloride (CID 8893, CAS 142-64-3);
`Magnesium (monoperoxyphthalate)2` ~ magnesium monoperoxyphthalate
(CID 54691831, CAS 78948-87-5). These are offered as a lead for a future
contributor to verify and add as an explicit synonym table, not as data in
this ledger — note in particular that "Sec Butanol" is a stereochemistry-
free name and CID 6568 is the racemate; the workbook does not say which
enantiomer (or whether racemic) is used, so even this lead is not a clean
substitute for the literal name. `(t-Bu)3P-Pd G2` (a Buchwald-type
tri-*tert*-butylphosphine Pd(0) G2 precatalyst) and `Ketene Acetal` (a
generic class name, not one substance) were not identified with confidence
and are left null.

## Published results — quoted as the benchmark's ground truth

From the paper's text and Table 1 (quoted for citation, not reproduced by
this tool — see next section):

- **Merck route**: GWP 382 kgCO2e/kg letermovir at 50% catalyst recovery;
  350 at 80% recovery; 342 at 90% recovery. PMI 147.
- **De novo route**: GWP 369 kgCO2e/kg at 50% recovery; 323 at 80%; 311 at
  90%. PMI 127.
- **Published ranking: de novo < Merck, by about 3%** (at matched recovery
  assumptions).
- **Per-step GWP, Merck route** (paper text): Step 1 = 126, Step 2 = 26,
  Step 3 = 8, Step 4 = 41, Step 5 = 36, Step 6 = 60, Step 7 = 83
  kgCO2e/kg letermovir.

## Cannot be reproduced by this tool

The published GWP figures quoted above were computed by the paper's authors
using **ecoinvent 3.10**, a commercially licensed background LCA database
that this project does not have, may not redistribute, and does not use.
**This benchmark cannot and does not attempt to reproduce those absolute
numbers.** Its only claim, per `benchmarks/README.md` acceptance condition
1, is a *ranking* — whichever public, citable factor table is attached to
this ledger, the pass condition is that carbonroute places `denovo` below
`merck` in GWP, the same order the paper reports, not agreement in
kgCO2e/kg. Building or wiring up that public factor table and the ranking
assertion itself is explicitly out of scope for this ledger/SOURCES.md pair
(owned by the benchmark-assertion author, per the task brief).
