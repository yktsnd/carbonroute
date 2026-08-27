# Sources investigated for a second open GHG-factor database

Scope: broaden `data/factors/` beyond ADEME Base Carbone (already being
ingested separately, ~7-11 base chemicals) with solvents and general
reagents a process chemist uses, subject to the project's hard rules —
live-fetched numbers only, redistributable-with-attribution licence only,
cradle-to-gate per-kg only. See `data/factors/uslci.SOURCES.md` for the
one source that was actually ingested (2 rows: carbon monoxide, ethylene
oxide) and the full reasoning for why it yielded so little.

**Bottom line: real, live-checked open solvent-GWP data is scarce.** Of
everything below, only USLCI's small set of pre-aggregated `LCI_RESULT`
processes cleared every rule, and it does not include the solvents chemists
actually use (THF, DCM, ethyl acetate, acetone, isopropanol, acetonitrile,
DMF, DMSO, heptane) at all. That is a negative result, and it is recorded
here rather than papered over.

| Source | URL | Reachable? | What it actually contains | Licence | Ingested? Why / why not |
|---|---|---|---|---|---|
| **US LCI Database / Federal LCA Commons** | https://www.lcacommons.gov/ , API at https://api.nal.usda.gov/FederalLCACommonsapi | Yes (HTTP 200; API works with a rate-limited shared `DEMO_KEY`) | ~660 unit processes + 24 pre-aggregated `LCI_RESULT` processes. Unit processes cover toluene, methanol, H2SO4, Na2CO3, NaOH, NH3, H2, acetic acid, ethanol — but require solving a linked technosphere graph to get cradle-to-gate numbers. That solve was attempted and produced 50-150x-too-high results (traced to a legacy uranium-enrichment/electricity feedback loop) and was rejected. The 24 aggregated processes are almost all steel/asphalt/roofing/wood; only 3 are chemicals (HCl, CO, ethylene oxide). | U.S.-government-funded, explicit no-fee redistribution-with-attribution grant (verbatim text in `processDocumentation.restrictionsDescription`, fetched live) | **Partially.** 3 rows ingested (CO, ethylene oxide, HCl) via `scripts/ingest_uslci.py`. HCl also ingested; its value disagrees with ADEME's by a factor of 1.42, which the loader now records and reports instead of refusing. No unit-process chemical (i.e. none of toluene/methanol/NaOH/H2SO4/Na2CO3/NH3/H2/acetic acid/ethanol) is ingested — see `data/factors/uslci.SOURCES.md` for the full technical account of the rejected graph-solve. |
| **ADEME Base Carbone** | https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner | Yes | ~7-11 base chemicals (being handled by a separate script/agent) | Licence Ouverte / Open Licence (Etalab) | Not this agent's job — owned by `scripts/ingest_ademe_basecarbone.py`, not touched here. |
| **JRC Life Cycle Data Network (soda4LCA nodes)**, e.g. `eplca.jrc.ec.europa.eu/EF-node` | https://eplca.jrc.ec.europa.eu/EF-node/resource/processes , https://eplca.jrc.ec.europa.eu/LCDN/ | Partially — the EF-node REST API itself works (valid JSON responses) | The publicly accessible data stock is licence-gated and returns almost nothing for common solvents/reagents (near-empty result sets on name search). The `LCDN` node-directory pages (`index.xhtml`, `developer.xhtml`, `nodes.xhtml`) that would enumerate other member nodes did not resolve to a usable listing in the time available (404 / empty). | Mixed / unclear per-node; not evaluated further because there was no usable data behind it | **No.** Thin data; not pursued further after confirming the earlier finding that the accessible stock is essentially empty for our target chemicals. |
| **ProBas (German Umweltbundesamt)** | https://www.probas.umweltbundesamt.de/ | Yes (HTTP 200) | ~20,000 GEMIS-derived process datasets, plausibly including real cradle-to-gate solvent/chemical data (UBA self-describes it as data made available to the public free of charge, "kostenlos zur Verfügung"). Could not confirm content because no working programmatic access was found: the site is a Gatsby SPA whose search/detail view is client-rendered via lazy-loaded JS chunks; `robots.txt` explicitly disallows crawling `/datenbank`; the legacy `php/prozesskategorien.php` and `php/prozessdetails` endpoints (found via web search) now just redirect to the SPA shell (retired); no `sitemap.xml`; no API base URL, GraphQL endpoint, or search-index path found in the static JS bundles (`app-*.js`, `webpack-runtime-*.js`) after a genuine search for `fetch(`/`axios(`/`elastic`/`solr`/`opensearch`/`uba.de` hostnames. | Likely favourable (German federal open-data conventions typically use Datenlizenz Deutschland dl-de/by-2.0 or similar) but never actually confirmed, because no data could be reached to check the licence *of a specific dataset* against | **No — investigated, not rejected on licence, rejected on lack of a discoverable scriptable access path.** Worth another look if a documented ProBas API or bulk-download surfaces later. |
| **PlasticsEurope Eco-profiles** | https://www.plasticseurope.org/en/resources/eco-profiles | No — HTTP 403 Forbidden on a direct fetch (bot-blocked) | Believed to cover petrochemical feedstocks/monomers (ethylene, propylene, benzene, styrene, methanol) with already-characterized cradle-to-gate GWP in PDF reports — but this was never confirmed live because the page could not be reached | Historically published with specific reuse terms; not verified | **No.** Blocked; also limited target-list overlap even if reachable (feedstock/monomer focus, not the pharma-solvent list). |
| **Idemat (TU Delft)** | (not fetched) | Not attempted | Reputed to cover a broad materials/chemicals list including some solvents | Reputed to be restrictive (non-commercial / no-redistribution style terms) but not verified live | **No — not pursued.** Given the project's hard rule against unclear/restrictive licences, and no time spent confirming it live, this is recorded as untried rather than rejected-on-evidence. |
| **GREET (Argonne National Laboratory)** | (not fetched) | Not attempted | Primarily transportation fuels/vehicles life-cycle model; general solvents/reagents are not its focus | DOE-funded, plausibly open | **No — not pursued**, low expected yield for this project's specific chemical list relative to effort. |
| **openLCA Nexus free databases** | (not fetched) | Not attempted | Directory of free LCA databases (varies by entry) | Varies per database | **No — not pursued**, would need per-database licence and content triage; deprioritized after USLCI/ProBas/PlasticsEurope did not pan out within the time available. |
| **Academic solvent-GWP papers** (e.g. green-chemistry solvent-selection-guide style publications) | (not fetched) | N/A | Several open-access papers publish per-solvent cradle-to-gate GWP tables for exactly this project's target list (THF, DCM, EtOAc, acetone, MeCN, DMF, DMSO, etc.) | The paper's own licence (often CC-BY) is not the relevant one — what matters is where *their* GWP numbers came from | **No — excluded on principle, not fetched.** Papers of this kind standardly source their solvent inventories from ecoinvent or GaBi, which this project's rules exclude outright regardless of the paper's own open-access licence. Not worth fetching case-by-case without a specific candidate known to use a non-commercial LCI source. |

## Detail: the USLCI graph-solve rejection (why it matters for future attempts)

This is worth recording in full because it is the reason USLCI's much
larger, more relevant unit-process coverage (toluene, methanol, H2SO4,
Na2CO3, NaOH, NH3, H2, acetic acid) was not used, and because it is a
concrete, checkable finding rather than a vague "too hard":

1. USLCI unit processes link to each other via `defaultProvider` fields on
   technosphere exchanges (e.g. "Toluene, at plant" consumes "Petroleum
   refined, to material use, at refinery", several transport processes,
   and "Electricity, at grid"). Getting a cradle-to-gate number means
   solving that whole linked system, not reading one process's own
   exchange list.
2. The reachable subgraph from 12 candidate target processes was built
   (BFS over `defaultProvider` links) and solved exactly, as a linear
   system `(I - C) x = d` where `C` holds technosphere coefficients and
   `d` holds each process's own IPCC-AR6-characterized direct emissions,
   using `numpy.linalg.solve`. The system has a large but finite condition
   number (~8×10⁹) and solves to a specific answer — but that answer is
   physically implausible: toluene ≈ 103 kgCO2e/kg, methanol ≈ 232,
   ammonia ≈ 150, hydrogen (SMR) ≈ 1079, sulfuric acid ≈ 16.4, acetic acid
   ≈ 368 — all roughly 50-150× typical published cradle-to-gate ranges for
   these chemicals.
3. Tracing the worst-converging node identified the cause: "Fuel grade
   uranium, at regional storage" consumes ~4080 kWh of electricity per kg
   of product (consistent with legacy gaseous-diffusion enrichment,
   long retired in the US in favour of centrifuge enrichment at roughly
   1/50th the energy intensity). "Electricity, at grid" draws part of its
   mix from nuclear generation, which in turn (through this process) draws
   ~4080 kWh/kg back from the grid — a near-closed loop that amplifies
   *every* process reachable through grid electricity, i.e. almost the
   entire network.
4. This strongly suggests a data-vintage mismatch inside USLCI (an old,
   energy-intensive enrichment dataset feeding a modern average grid mix)
   rather than a bug in the linear-algebra approach itself — but confirming
   that with confidence, and correcting it responsibly, would mean
   auditing and patching a ~660-process third-party database by hand. That
   is out of scope for a reproducible ingestion script, and shipping the
   uncorrected numbers would violate this project's core rule that every
   number must be checkable by a third party without turning up something
   that discredits it on inspection.

Anyone revisiting USLCI for the solvent list should either (a) use a real
LCA calculation engine (openLCA) that can flag/exclude this kind of
provider loop with proper diagnostics, or (b) find a different upstream
source for grid electricity's nuclear-fuel link that does not route through
this specific legacy dataset.

## What this leaves uncovered

None of the following made it into any factor table via this
investigation: THF, 2-methyltetrahydrofuran, dichloromethane, ethyl
acetate, acetone, ethanol (as a lab solvent — USLCI has denatured fuel
ethanol, but that is not the same product/route and was excluded along
with the rest of the unit processes anyway), isopropanol, acetonitrile,
DMF, DMSO, heptane, or nitrogen gas. This is the honest state of open,
redistributable, cradle-to-gate solvent GWP data as of this investigation
(2026-08-26/27) — see `data/factors/uslci.SOURCES.md` and the table above
for what was actually checked before concluding that.

---

# 2026-08-27 — ILCD / soda4LCA and national open-database round (probas_gemis)

Scope: ILCD / soda4LCA / EPD-style LCA nodes and national open databases,
specifically hunting for process solvents and bulk reagents (per the
project's priority list). Result actually ingested:
`data/factors/probas_gemis.csv` / `.SOURCES.md`, via
`scripts/ingest_probas_gemis.py` — **7 rows**: water (distilled), toluene,
isopropanol, acetic acid, ethanol, ammonia, hydrogen. First solvents/
reagents this project has actually landed from a live LCA-database source
(prior rounds landed 0 solvents from ADEME Base Carbone + USLCI combined).

**The find**: ProBas (`https://data.probas.umweltbundesamt.de`), the
German Umweltbundesamt's soda4LCA node. The brief's `probas.umweltbundesamt.de`
SPA (blocked, no API, per the prior round's note) has been superseded by
this new host, which *is* a working soda4LCA REST API
(`/resource/processes?format=json&search=true&name=...`). Most of its
content is republished ecoinvent (`dataSources: [{"name": "ecoinvent 3.8
cut-off"}]`, confirmed live on every such row, plus the node's own
`Probas2_Aufstockung2` data stock self-describing as an ecoinvent-import
test stock) and is excluded outright. What is left is UBA's own **GEMIS**
content (Öko-Institut, since 1987) — independent literature-sourced
(Ullmann's Encyclopedia, BUWAL, ECN, Römpp, ESU/PSI/BEW), licensed
"Free of charge for all users and uses" per-process, with a node-level
usage-terms PDF requiring attribution and prohibiting alteration — the
licence class this project accepts. Full detail, including the complete
"searched and found nothing" list for the 15 priority substances GEMIS
does not model (THF, 2-MeTHF, DCM, ethyl acetate, isopropyl acetate,
acetone, acetonitrile, DMF, DMSO, n-heptane, n-pentane, MTBE,
triethylamine, sodium bicarbonate, potassium phosphate, sodium
phosphates), is in `data/factors/probas_gemis.SOURCES.md`.

**Everything else probed this round, all negative/excluded** (full
detail and exact URLs in `probas_gemis.SOURCES.md`):

| Source | Result |
|---|---|
| Ökobaudat (`oekobaudat.de/OEKOBAU.DAT/...` — note: dot, not the brief's `/OEKOBAUDAT/`, which infinite-redirect-loops) | Working API, essentially empty for this project's chemical list (construction-materials focus); its two substance-shaped hits ("Drinking water", "Ammonia (R717)") are both explicitly Sphera/GaBi-sourced ("GaBi Database Edition 2021" / "Sphera Managed LCA Content Databases") — excluded |
| JRC Life Cycle Data Network (`lcdn.jrc.ec.europa.eu`) | Node directory is an empty JS shell with no discoverable API (confirmed again this round) |
| ELCD (`eplca.jrc.ec.europa.eu/ELCD3/`) | HTTP 404 — confirmed dead |
| EPD Norway (`epdnorway.lca-data.com`, a live soda4LCA node found via GLAD/ECO-Platform search, as a stand-in for "enumerate JRC LCDN member nodes") | Working API; only one substance-list hit ("Bioethanol", CAS 64-17-5 given in its own text), sourced from "ecoinvent database (all versions)" — excluded. Confirms EPD/construction nodes carry finished products, not bulk chemicals, and mostly sit on ecoinvent anyway |
| ECO Platform data portal (`data.eco-platform.org`) / French INIES (`base-inies.fr`) | Both serve an Angular SPA at the paths tried, no working classic soda4LCA REST endpoint found; not pursued further given the EPD Norway result already shows what this class of node contains |
| AusLCI | Requires proof of an ecoinvent licence just to download — excluded on the access gate itself, no live fetch needed |
| ADEME — datasets beyond Base Carbone (AGRIBALYSE, "Transition(s) 2050" scenario tables e.g. `hydrogene-g9`, ~20 search terms enumerated) | AGRIBALYSE is food/agricultural-ingredient LCI, out of scope; the hydrogen scenario table has **no stated unit** anywhere in its schema and mixes historical with 2050-projection values — skipped, no verifiable per-kg conversion exists. No dataset resolves under the ids `base-empreinte` / `base-empreinter` / `empreinte-base-carbone` (all HTTP 404) |

## Running count across all rounds

Substances now covered by *some* live-fetched, non-commercial, per-kg
cradle-to-gate row somewhere in `data/factors/` (see each file's own
`.SOURCES.md` for exact provenance and any cross-table conflicts the
loader records): the ~9 from `ademe_base_carbone.csv`/`uslci.csv` (prior
rounds) plus this round's 7 (water, toluene, isopropanol, acetic acid,
ethanol, ammonia, hydrogen — ammonia and hydrogen may now disagree with
`ademe_base_carbone.csv`'s route-specific values if that file carries
them; check `FactorTable.load(...).conflicts` for the current state).

**Still entirely missing from every table, after this round**: THF,
2-methyltetrahydrofuran, dichloromethane, ethyl acetate, isopropyl
acetate, acetone, acetonitrile, DMF, DMSO, n-heptane, n-pentane, MTBE,
triethylamine, sodium bicarbonate, potassium phosphate, sodium
phosphates. That is 15 of the 23 priority substances — the laboratory/
process-solvent and buffer-salt half of the list specifically — for which
no open, non-commercial, per-kg cradle-to-gate LCA-database record was
found in either this round or any prior one. Every open LCA-style
database reachable this round (Ökobaudat, ProBas, JRC LCDN, ELCD, EPD
Norway, ECO Platform/INIES, AusLCI, ADEME) was built for construction
materials, national energy/materials-flow accounting, or bulk
petrochemical feedstocks — none model pharma-grade process solvents. A
different source class (safety-data-sheet-adjacent industry LCA reports,
solvent-selection-guide primary datasets, or a chemical-industry-specific
open database not yet identified) would be needed to close that gap.

## 2026-08-27 — publisher-issued PCFs, EPDs, and association eco-profiles

Scope: a different lane from every round above — not open LCA databases,
but values producers and standards bodies publish directly (Product Carbon
Footprints, Environmental Product Declarations, industry-association
eco-profiles), for process solvents and bulk chemicals. Full citations and
every rejected candidate are in `data/factors/published_pcf.SOURCES.md`
(generated alongside `data/factors/published_pcf.csv` by
`scripts/ingest_published_pcf.py`); this section is a short pointer plus
the headline result, per the project's running log convention.

**Bottom line: this lane worked, and is worth another pass.** Unlike the
open-LCA-database lanes above (which hit a wall on solvents specifically),
publisher/association documents yielded 5 verified, cradle-to-gate,
per-kg values in a single session, including one solvent that no other
table in this repo currently carries:

| CAS | Substance | kgCO2e/kg | Class | Publisher |
|---|---|---|---|---|
| 71-43-2 | Benzene | 1.86 | literature | PlasticsEurope & CEFIC/APPE (BTX Eco-profile, 2013) |
| 75-09-2 | Dichloromethane | 0.48 | supplier | Nobian (EPD International, EPD-IES-0022304:001, 2025) |
| 108-88-3 | Toluene | 1.22 | literature | PlasticsEurope & CEFIC/APPE (BTX Eco-profile, 2013) |
| 1333-74-0 | Hydrogen | 7.5 | literature | PlasticsEurope ("H2 reformer" Eco-profile, 2005) |
| 7664-41-7 | Ammonia | 2.4 | literature | PlasticsEurope ("Ammonia" Eco-profile, 2005) |

Toluene, hydrogen, and ammonia now disagree with `probas_gemis.csv`'s
values for the same CAS numbers (ratios ~1.13–1.39×); `FactorTable.load()`
records all three as `Conflict`s rather than refusing to load — checked
live this round (`FactorTable.load(default_factor_paths())` loads all four
CSVs currently in `data/factors/` cleanly, 36 rows, 4 conflicts total,
including one pre-existing HCl conflict between ADEME and USLCI). Benzene
and dichloromethane loaded with no conflict.

**What made this lane work where open-database lanes didn't**: PlasticsEurope
publishes real per-substance eco-profiles for petrochemical building blocks
(BTX aromatics, ammonia, hydrogen, phenol/acetone, hydrocarbon-solvent
blends) built from primary member-company data — but `plasticseurope.org`
itself 403s every direct fetch, and even the Wayback Machine mirror of that
specific domain is currently behind an `archive.org` bot-challenge page on
this network (both matches the previous round's dead end). The unblocked
path was `legacy.plasticseurope.org` — an older Concrete5-era version of
the same site, HTTP 200, hosting the same interactive eco-profile flowchart
with working `/download_file/<id>/0` links straight to the report PDFs.
Worth remembering for any future round that hits the same `plasticseurope.org`
403: try `legacy.plasticseurope.org` before giving up on PlasticsEurope
entirely.

**What this lane explicitly rejected, on the source's own say-so**: the
PlasticsEurope/CEFIC Phenol and Acetone EPD (Sept 2016) states inline that
its own LCI is "not based on primary industry data but solely on literature
data" from the GaBi 2015 database — both candidate numbers (Acetone 1.64,
Phenol 1.79 kgCO2e/kg) were read and then discarded for exactly the reason
this project's rules name. See the SOURCES.md file for this and seven other
rejected candidates (IMPCA's methanol guidance tool, HSPA's blended-UVCB
solvent eco-profiles, Fertilizers Europe's energy-only ammonia data, BASF's
relative-only rPCF disclosure, the TfS guideline itself, and more), each
with the specific reason it didn't clear this project's bar.

**Still missing after this round, specifically from the priority list**:
water, THF, 2-MeTHF, ethyl acetate, isopropyl acetate, acetone (a real
number was *found* but rejected — see above), acetonitrile, DMF, DMSO,
isopropanol (an association/producer figure specifically; note ProBas may
already carry this from an earlier round), n-heptane, n-pentane, MTBE,
triethylamine, acetic acid, methanol, phenol (same as acetone — found,
rejected). None of the pharma/lab-solvent-specific chemicals (THF, 2-MeTHF,
DCM's siblings like ethyl/isopropyl acetate, acetonitrile, DMF, DMSO) turned
up a producer PCF or EPD anywhere searched this round; BASF is the most
likely publisher of several of these (it explicitly sells THF, NMP, DMF-
adjacent intermediates and has an ISO-14067 PCF programme covering "all
45,000 sales products") but distributes individual values through a
customer-only portal (`myPMportal.basf.com`), not a public document — this
remains the single biggest identified gap-with-a-known-shape: if BASF (or
any producer) ever publishes even one representative example PCF value in
a public sustainability report or product datasheet rather than gating it
behind a login, that would be immediately usable and is worth checking for
specifically in any follow-up round.
