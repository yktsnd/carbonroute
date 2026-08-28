# Process recipes

This directory is the input side of `carbonroute bootstrap` (see
`docs/bootstrap.md` and `src/carbonroute/bootstrap.py`), which computes a
factor for a substance that no openly licensed LCA database covers, from
the same kind of description any chemist already thinks in: what goes in,
how much energy it takes, and what comes out. The engine turns a recipe
plus the factors already in `data/factors/` into a **lower-bound** GWP
figure, published as an interval, not a point estimate — see
`docs/bootstrap.md` for exactly how and why. This file documents the input
format and the rules for filling it in; it does not compute anything.

## Format

One file per substance, named `<substance-slug>.yaml`:

```yaml
substance:
  name: tetrahydrofuran
  cas: "109-99-9"          # optional; check-digit validated on load
  inchikey: WYURNTSHIVDZCO-UHFFFAOYSA-N   # optional, informational only

route:
  name: "Dehydration of 1,4-butanediol (Reppe route)"
  description: "..."       # free text
  stoichiometry: "C4H10O2 -> C4H8O + H2O"   # informational only, not parsed
  yield: 0.995              # optional, must be in (0, 1]
  yield_source: {document: "...", url: "...", locator: "..."}  # required if yield is set

inputs:                      # per 1 kg of product
  - name: 1,4-butanediol
    cas: "110-63-4"          # optional; check-digit validated on load
    kg_per_kg_product: 1.2499
    basis: stoichiometric     # or: stated
    source: {document: "...", url: "...", locator: "..."}  # required if basis is "stated"

energy:
  electricity_kWh_per_kg: 0.12
  electricity_source: {document: "...", url: "...", locator: "..."}
  fuel_MJ_per_kg: 4.5
  fuel_source: {document: "...", url: "...", locator: "..."}

notes: |
  Anything a reader needs: which of several routes this is, what the
  numbers exclude, assumptions made and why, cross-checks against other
  sources.

gaps:                        # first-class field — be explicit
  - "No electricity figure found for this process in any source checked."
```

Only `substance.name` is strictly required by the loader
(`carbonroute.bootstrap.load_recipe`); everything else may be omitted.
**Omit any field you could not source — a blank field is correct; a
plausible-looking guess silently corrupts every comparison downstream.**

### A quirk worth knowing before you write a recipe

`route.yield` is applied **uniformly to every `basis: stoichiometric`
input** in the recipe (there is no per-input yield). Without a
`route.yield`, the engine does **not** drop a stoichiometric input from the
sum — it counts it at its bare theoretical (100%-yield) amount, which is
itself a legitimate lower bound (real feedstock consumption can only be
*higher* than the theoretical minimum, never lower), but a looser one than
a yield-adjusted figure gives. The engine records this explicitly in its
own output rather than silently treating the theoretical amount as real
("stoichiometric quantity with no sourced yield to divide by; counted at
theoretical demand, which understates it"). A recipe only derives literally
**nothing** when *every* input fails to resolve to a factor (directly held
or itself derived) — several files below have no held feedstock at all
(e.g. tetrahydrofuran's 1,4-butanediol) and are flagged as currently
non-deriving in their `gaps:` for that reason, not for lacking a yield.

Given that, a `route.yield` that is genuinely a reaction *yield* still
matters — it tightens the floor from a loose theoretical bound to a
realistic one — and several files here use a *conversion* or *selectivity*
figure as a documented proxy for it, because that was the only real number a
source gave — every such substitution is spelled out in that file's
`notes` and flagged again in `gaps`, never done silently.

## Sourcing rules

- **Every number carries a citation to a document actually retrieved and
  read** — a PDF fetched and searched, a patent's own text pulled from
  Google Patents, never a remembered figure, a search-result snippet, or
  "typical industrial practice." Where a source was found only via a
  WebSearch summary and could not be verified by reading the underlying
  document (Google Patents rate-limited this session repeatedly), that is
  stated explicitly and the number is **not** used.
- **Balanced stoichiometry** may be derived from the reaction equation and
  standard atomic weights — that is arithmetic, not data — and is marked
  `basis: stoichiometric`. Every other number needs a
  `{document, url, locator}` citation and is marked `basis: stated`.
- **A range in the source** is recorded in `notes` in full, and the
  midpoint is used in the YAML with `basis: stated` (or as `route.yield`),
  stating plainly that a midpoint was taken.
- **CAS numbers** are verified with `carbonroute.schema.cas_checksum_ok`
  (`PYTHONPATH=src`) before being written down, and resolved (together with
  InChIKeys) via PubChem PUG REST.
- **A gap is not a failure.** `gaps:` is where a reader is told exactly
  what was looked for, where, and not found — including, per the quirk
  above, whether the recipe currently derives anything at all.

## Where the data came from

- **EU BAT Reference Documents (BREFs)**, published by the JRC at
  `https://eippcb.jrc.ec.europa.eu/reference` (mirrored PDFs served from
  `bureau-industrial-transformation.jrc.ec.europa.eu`). These proxy/CDN
  servers reject requests without a real browser `User-Agent` and
  `Referer` header (returns a 244-byte "Request Rejected" page even on a
  200 status) — set both explicitly when fetching. Three BREFs were used:
  - **LVOC** (Large Volume Organic Chemicals, Dec 2017, JRC109279) — covers
    Lower Olefins, Aromatics, Ethylbenzene/Styrene, Formaldehyde, Ethylene
    Oxide/Glycols, Phenol, Ethanolamines, TDI/MDI, EDC/VCM, Hydrogen
    Peroxide. None of this project's target solvents/chemicals are a
    direct match *except* toluene (a component of the Aromatics chapter's
    BTX stream) and acetone (a co-product of the Phenol chapter's cumene
    process) — see those two files for how much or little this BREF ends
    up contributing.
  - **LVIC-AAF** (Large Volume Inorganic Chemicals — Ammonia, Acids and
    Fertilisers, Aug 2007) — used for ammonia; the single best-sourced file
    in this directory.
  - **LVIC-S** (Large Volume Inorganic Chemicals — Solids and Others, Aug
    2007) — used for sodium bicarbonate (the Solvay process).
- **US EPA AP-42** — checked (chapter/section listings only) and found not
  to cover any of this project's target substances; not used.
- **Google Patents** (`patents.google.com/patent/<number>/en`) — used for
  every organic-chemical route without BREF coverage: worked examples give
  real reaction conditions and, sometimes, real yields. Fetching required a
  real browser `User-Agent`; the service returned HTTP 503 unpredictably
  throughout this session (sometimes clearing on an immediate retry,
  sometimes persisting for many minutes) — several candidate patents could
  not be retrieved at all and are named in the relevant file's `gaps:` as
  leads for a future session.
- **PubChem PUG REST** — `compound/name/<name>/cids/JSON`, then
  `.../cid/<cid>/property/InChIKey/JSON` and `.../cid/<cid>/synonyms/JSON`
  (first CAS-shaped synonym, `\d{2,7}-\d{2}-\d`) for every substance named
  in any recipe, feedstock or product.

## Coverage

"Derives now?" was checked directly, not estimated: by running
`carbonroute.bootstrap.derive_all` against every file in this directory
plus a scratch factor table holding placeholder values for exactly the 18
substances the coordinating engine reported as currently held in
`data/factors/` (water, methanol, ethanol, isopropanol, toluene, benzene,
hexane, dichloromethane, acetic acid, ammonia, hydrogen, carbon monoxide,
ethylene oxide, NaOH, HCl, H2SO4, H3PO4, Na2SO4). "Yes" means the recipe
appears in `result.derived` (a non-zero floor, however incomplete); it will
change as `data/factors/` grows. A substance whose own factor is *already*
held directly is marked so; its recipe is then useful mainly for
cross-checking that held value, or as a feedstock for something further
downstream. "Partial" means it derives but at least one input/energy term
did not resolve — every recipe below omits at least one term (most have no
sourced energy at all), so "Partial" marks the ones missing a *feedstock*
term specifically, on top of that.

| Substance | File | Feedstocks | Energy | Yield/conversion | Derives now? |
|---|---|---|---|---|---|
| ammonia | `ammonia.yaml` | stated (N2, process steam) + stoichiometric (H2) | stated (fuel, BAT range) | — (not needed; two stated inputs) | **Yes** |
| sodium bicarbonate | `sodium-bicarbonate.yaml` | stoichiometric (NaCl, NH3, CO2) | none found | stated (Na+ conversion, ~70%) | **Yes** |
| tetrahydrofuran | `tetrahydrofuran.yaml` | stoichiometric (1,4-butanediol) | none found | stated (patent, 99.5%) | No (feedstock not held) |
| 2-methyltetrahydrofuran | `2-methyltetrahydrofuran.yaml` | stoichiometric (furfural, H2) | none found | derived (this ledger's own combination of two stage figures, 76.5%) | Partial (only H2 resolves) |
| ethyl acetate | `ethyl-acetate.yaml` | stoichiometric (ethanol, acetic acid) | none found | stated (patent, 97%) | **Yes** |
| isopropyl acetate | `isopropyl-acetate.yaml` | stoichiometric (isopropanol, acetic acid) | none found | stated (patent, 97%) | **Yes** |
| acetone | `acetone.yaml` | stoichiometric (isopropanol) | none found | stated (patent, 99.4% selectivity) | **Yes** |
| dichloromethane | `dichloromethane.yaml` | stoichiometric (methyl chloride, chlorine) | none found | derived (this ledger's midpoint of 3 patent figures, 91%) | No (feedstocks not held) |
| acetonitrile | `acetonitrile.yaml` | none (byproduct, no allocation basis found) | none found | — | No |
| ethanol | `ethanol.yaml` | stoichiometric (ethylene) | none found | none sourced (unconfirmed lead only) | No — feedstock not held (substance itself already held directly) |
| isopropanol | `isopropanol.yaml` | stoichiometric (propylene) | none found | stated (patent, 97% selectivity) | No — feedstock not held (substance itself already held directly) |
| n-heptane | `n-heptane.yaml` | none (physical separation, no source found) | none found | — | No (substance itself already held directly) |
| n-pentane | `n-pentane.yaml` | none (physical separation, no source found) | none found | — | No (substance itself already held directly) |
| MTBE | `mtbe.yaml` | stoichiometric (isobutylene, methanol) | none found | stated (patent, 99.8%) | Partial (only methanol resolves) |
| triethylamine | `triethylamine.yaml` | stoichiometric (acetonitrile, H2) | none found | stated (patent, 96.5%) — route NOT confirmed dominant, see file | Partial (only H2 resolves) |
| acetic acid | `acetic-acid.yaml` | stoichiometric (methanol, CO) | none found | none sourced | **Yes**, at bare theoretical (un-yield-adjusted) demand — see the "quirk" above (substance itself already held directly) |
| DMF | `dmf.yaml` | stoichiometric (dimethylamine, CO) | none found | derived (this ledger's calc from patent batch masses, 98%) | **Yes** (chains through dimethylamine) |
| dimethylamine `*` | `dimethylamine.yaml` | stoichiometric (methanol, ammonia) | none found | stated (patent, methanol conversion used as proxy, 90%) | **Yes** |
| DMSO | `dmso.yaml` | stoichiometric (dimethyl sulfide, O2) | none found | stated (patent, 99%) | No (feedstocks not held) |
| toluene | `toluene.yaml` | none (extraction, not synthesis) | stated (BREF, BB2 unit aggregate) | n/a | **Yes** (substance itself already held directly) |
| water (deionised) | `water.yaml` | none | none found | n/a | No (substance itself already held directly) |
| 1-butyl-3-methylimidazolium chloride `**` | `1-butyl-3-methylimidazolium-chloride.yaml` | stoichiometric (1-methylimidazole, 1-chlorobutane) | none found | stated (ChemSpider Synthetic Pages 747, 82.2%) | No (feedstocks not held) |
| 1-butyl-3-methylimidazolium hexafluorophosphate `**` | `1-butyl-3-methylimidazolium-hexafluorophosphate.yaml` | stoichiometric ([BMIM]Cl, KPF6) | none found | none sourced (3 verification attempts failed — see file's notes) | No (feedstocks not held, chains through the file above) |

`*` dimethylamine is not one of the 20 originally-requested substances; it
was added because DMF's dominant route consumes it, and because both of
*its* own feedstocks (methanol, ammonia) are already held, so it lets DMF's
recipe chain all the way down to two held factors instead of dead-ending.

`**` these two were added in a later session, targeting the [BMIM][PF6]
ionic liquid that dominates the unresolved mass in
`examples/case-studies/ibuprofen-bogdan-vs-enzymatic/` — see that case
study's `SOURCES.md` for the full account of what was and was not found.
Neither currently derives; both are sourced groundwork for whenever a
factor for 1-methylimidazole, 1-chlorobutane, or potassium
hexafluorophosphate is added.

**12 of the 23 files here (11 of the 20 originally-requested substances,
plus the dimethylamine helper) currently derive a non-zero floor**,
verified by actually running the engine (see above), not just counting
sourced numbers. Ammonia and toluene are the fullest treatments (a
feedstock/stated-input line *and* an energy line) — **toluene is, in
fact, the only file with a sourced electricity figure** (0.0415 kWh/kg,
from the same LVOC BREF table as its fuel figure); ammonia has a fuel
figure only. Every other file in this directory has **no process-energy
figure of any kind** — this is the single biggest and most consistent gap
across the whole directory, exactly as the brief warned it would be the
hardest number to find.
