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
