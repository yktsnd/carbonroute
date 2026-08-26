# `ademe_base_carbone.csv` — sources, licence, and retrieval log

## Dataset

**ADEME Base Carbone®** — the French public LCA / emission-factor database
published by l'Agence de la transition écologique (ADEME).

- Dataset landing page: https://data.ademe.fr/datasets/base-carboner
- Dataset API root: https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner
- Dataset title (as returned by the API): `Base carbone®`
- `dataVersion` at time of retrieval: `2026-06-30T10:17:08.470Z`

## Licence and attribution

The dataset's own metadata (`license` field on the API root) declares:

> **Licence Ouverte / Open Licence** — https://www.etalab.gouv.fr/licence-ouverte-open-licence

This is the Etalab "Licence Ouverte" (Open Licence), which permits free
reuse — including commercial reuse, redistribution and adaptation — subject
to attribution of the source. Attribution used in this file's `source`
column and required for any downstream reuse:

> Data derived from **ADEME, Base Carbone®**
> (https://data.ademe.fr/datasets/base-carboner), made available under the
> **Licence Ouverte / Open Licence (Etalab)**.

The `license` column on every row of `ademe_base_carbone.csv` also carries
this statement so it travels with the data even outside this repository.

## Retrieval

- Retrieved: **2026-08-26**
- Retrieval tool: `scripts/ingest_ademe_basecarbone.py` (this repository) —
  re-run with:
  ```
  PYTHONPATH=src python3 scripts/ingest_ademe_basecarbone.py \
      [--out data/factors/ademe_base_carbone.csv] [--report]
  ```
- API calls made by the script (all live, no cached/pre-fetched numbers):
  1. `GET https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner`
     — dataset metadata (title, licence, `dataVersion`).
  2. `GET https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner/lines?Code_de_la_catégorie_eq=<category>&size=200[&after=<cursor>]`
     — row data, once per category listed below, paginated via the `next`
     link's `after` cursor.
  3. PubChem PUG REST, for every ADEME row that survived the filters:
     - `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/<name>/cids/JSON`
     - `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/<cid>/property/InChIKey,MolecularFormula,CanonicalSMILES/JSON`
     - `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/<cid>/synonyms/JSON`
     rate-limited to <= 4 requests/second, cached on disk by request URL so
     re-runs are cheap and reproducible.

PubChem PUG REST is a public, US-government (NIH/NLM) service; the data it
returns (CID, InChIKey, synonym list including CAS numbers) is in the
public domain.

## Category exploration

The full category tree was enumerated live via
`.../base-carboner/values_agg?field=Code_de_la_catégorie&agg_size=400&size=0`
and every branch that could plausibly contain reactor-feedstock chemicals
was fetched and inspected by hand.

**Category actually used as a source of candidate rows** (11 rows fetched):

- `Achats de biens > Plastiques et produits chimiques > Produits chimiques > Produits chimiques de base`

**Categories fetched, inspected, and excluded wholesale**, with the reason
recorded (row counts as fetched on 2026-08-26):

| Category | Rows | Reason excluded |
|---|---:|---|
| `... > Produits chimiques > Autres produits chimiques` | 1 | sole row is a formulated product ("Produits de traitement de la vapeur d'eau"), not a substance |
| `... > Produits chimiques > Peintures et résines` | 4 | formulated adhesives/lacquers/varnishes, not single PubChem-resolvable substances |
| `... > Plastiques et caoutchouc > Polymères de l'éthylène` | 8 | bulk polymer resins, not reactor feedstocks; ambiguous duplicate values present (e.g. LDPE at two different values with no distinguishing field) |
| `... > Plastiques et caoutchouc > Plastique moyen` | 2 | generic averaged plastic, not a substance |
| `... > Plastiques et caoutchouc > Polymères du chlorure de vinyle` | 2 | bulk polymer resin (PVC), not a reactor feedstock |
| `... > Plastiques et caoutchouc > Polymères du styrène` | 2 | bulk polymer resin (polystyrene), not a reactor feedstock |
| `... > Plastiques et caoutchouc > Polyamides` | 1 | bulk polymer resin (nylon), not a reactor feedstock |
| `... > Plastiques et caoutchouc > Polymères de propylène` | 1 | bulk polymer resin (PP), not a reactor feedstock |
| `Combustibles > Fossiles > Gazeux > Gaz industriels` | 10 | industrial off-gas fuels (blast-furnace gas, coke-oven gas), priced per GJ, not per kg — wrong unit basis |
| `Achats de biens > Hydrogène > Production d'hydrogène` | 20 | hydrogen resolves cleanly to CAS 1333-74-0, but ADEME gives 7 mutually exclusive production-route-specific values (electrolysis on 5 grid/source mixes, biomethane reforming, natural-gas reforming), spanning 0.45–19.8 kgCO2e/kg H2, with no generic/market-average row. Picking one route would be an editorial judgement this script refuses to make silently. |

Also considered and excluded on inspection (not separately re-fetched by
the script, reasoning recorded here):

- `Process et émissions fugitives > PRG à 100 ans ...`: these rows give the
  GWP of a gas *if released* (e.g. carbon dioxide = 1 kgCO2e/kg,
  tautologically), i.e. the gas's own global-warming potential — not the
  cradle-to-gate emissions of *manufacturing* it. Including them would
  silently redefine what the `gwp_kgCO2e_per_kg` column means for this
  table, so they are excluded even though real and fetchable.
- Fertiliser/pesticide/viticulture subtrees under
  `... > Produits chimiques > Engrais, phytosanitaires ...`: out of scope
  per the brief (agricultural inputs, not reactor feedstocks), and several
  entries there visibly share one proxied value across unrelated
  substances.

## Filtering applied to the 11 candidate rows

1. Keep only `Type_Ligne == "Elément"` and
   `Type_de_l'élément == "Facteur d'émission"`.
2. Keep only rows whose `Unité_anglais` is a per-mass unit: `kgCO2e/kg`
   (factor unchanged) or `kgCO2e/ton` (**divided by 1000** to convert to
   kgCO2e/kg). The untouched original value and unit are preserved verbatim
   in the `notes` column of every row.
3. Drop rows naming a graded/diluted commercial solution or a vague
   generic term, before ever querying PubChem, because attaching such a
   value to a pure substance's CAS number would misrepresent it:
   - `Acide nitrique 50%` — graded/diluted commercial solution (50%), not
     the pure substance.
   - `Soude 50%` — graded/diluted commercial solution (50%), not the pure
     substance.
   - `Hypochlorite de sodium 15% (alcalin chloré)` — graded/diluted
     commercial solution (15%), not the pure substance.
   - `Alcool` — generic/ambiguous name, does not specify which alcohol.
4. For every surviving row, resolve the ADEME name to PubChem
   (`compound/name/.../cids` → exactly one CID required), fetch
   `InChIKey` and synonyms for that CID, take the **first** CAS-shaped
   synonym (`\d{2,7}-\d{2}-\d`), and verify its check digit with
   `carbonroute.schema.cas_checksum_ok`. Any row that fails any of these
   steps is dropped and reported.
5. One row's ADEME English name (`Solide soda (powder, granule)`) is a
   literal machine translation of the French `Soude solide (poudre,
   granulés)`, not a usable PubChem query string. It is queried on PubChem
   as `Sodium hydroxide` instead (CAS/InChIKey/CID all still resolved live
   from PubChem, not asserted); both the original ADEME name and the
   substituted query name are recorded in `notes`.

`gsd` is derived from ADEME's `Incertitude` percentage, treated as a
coefficient of variation `cv = pct/100`, via
`gsd = exp(sqrt(log(1 + cv**2)))`. Left empty on rows where `Incertitude`
is absent (none of the kept rows lack it). The original percentage is kept
verbatim in `notes`.

## Kept rows (7)

| CAS | Name | kgCO2e/kg | Original ADEME value | Incertitude |
|---|---|---:|---|---:|
| 110-54-3 | Hexane | 0.313 | 313 kgCO2e/ton | 50% |
| 1310-73-2 | Sodium hydroxide | 0.458 | 458 kgCO2e/ton | 100% |
| 67-56-1 | Methanol | 0.521 | 521 kgCO2e/ton | 50% |
| 7647-01-0 | Hydrochloric acid | 1.199 | 1199 kgCO2e/ton | 50% |
| 7664-38-2 | Phosphoric acid | 1.424 | 1424 kgCO2e/ton | 50% |
| 7664-93-9 | Sulphuric acid | 0.148 | 148 kgCO2e/ton | 50% |
| 7757-82-6 | Sodium sulphate | 0.473 | 473 kgCO2e/ton | 100% |

All rows: `Localisation_géographique = France continentale`;
`Date_de_modification = 2014-11-05`.

## Rejected candidates (4, from the 11-row candidate category)

| ADEME name | Element id | Reason |
|---|---|---|
| Acide nitrique 50% | 20666 | graded/diluted commercial solution (50%), not the pure substance |
| Alcool | 20852 | generic/ambiguous name — does not specify which alcohol |
| Hypochlorite de sodium 15% (alcalin chloré) | 20794 | graded/diluted commercial solution (15%), not the pure substance |
| Soude 50% | 20847 | graded/diluted commercial solution (50%), not the pure substance |

No row was dropped for failing PubChem resolution or a CAS check-digit
failure in this run — all 7 rows that passed the unit/name filters
resolved cleanly to exactly one PubChem CID with a valid CAS number.

## Caveats for anyone using this table

- **Data vintage**: every kept row was last modified in ADEME's database on
  **2014-11-05**. These are not current-year figures; treat them as a
  multi-year-old snapshot of French industrial LCA estimates, not a
  live-market number.
- **Geographic scope**: all rows are scoped to `France continentale`
  (mainland France) grid/energy mix and, presumably, French/European
  production routes. They are not necessarily representative of production
  elsewhere (e.g. US or Chinese chemical manufacturing, which can have
  substantially different grid carbon intensity and process routes).
- **Coverage is intentionally small**: only 7 substances. This reflects
  what ADEME's "Produits chimiques de base" category actually contains as
  clean, per-mass, single-substance entries — not a limitation of the
  script. Whole adjacent branches (paints/resins, plastics, industrial
  gases, hydrogen) were deliberately excluded rather than force-fit; see
  the exclusion table above.
- **Plausibility**: cradle-to-gate values of roughly 0.15–1.4 kgCO2e/kg for
  bulk inorganic acids/bases and light solvents are broadly consistent with
  published LCA literature for these commodity chemicals (e.g. sulphuric
  acid's low value reflects its highly exothermic, energy-exporting
  contact process). Sodium hydroxide and sodium sulphate carry the highest
  `Incertitude` (100%) of the set — treat those two figures as the least
  reliable of the seven.
- **Uncertainty class**: all rows use `uncertainty_class = literature`
  per the task brief; `gsd` is *derived* from ADEME's stated `Incertitude`
  and is therefore only as good as that self-reported figure.
