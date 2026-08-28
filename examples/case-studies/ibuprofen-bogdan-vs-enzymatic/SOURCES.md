# Ibuprofen (Bogdan vs enzymatic route) — sources and provenance

## Citation

Grimaldi, F.; Tran, N. N.; Sarafraz, M. M.; Lettieri, P.; Morales-Gonzalez,
O. M.; Hessel, V. "Life Cycle Assessment of an Enzymatic Ibuprofen
Production Process with Automatic Recycling and Purification." *ACS
Sustainable Chem. Eng.* **2021**, 9, 39, 13157–13166.
DOI: [10.1021/acssuschemeng.1c02309](https://doi.org/10.1021/acssuschemeng.1c02309).

**© 2021 American Chemical Society. Not open access, not CC BY** — verified
directly from the Warwick WRAP institutional-repository record for this
article (`wrap.warwick.ac.uk/id/eprint/158477/`), which states plainly:
"Access rights to Published version: Restricted or Subscription Access.
Copyright Holders: Copyright © 2021 American Chemical Society." **No source
PDF is committed in this repository for that reason** — unlike the letermovir
and ZIF-8 case studies, this one is citation-only, the same treatment already
used for the BREFs and patents cited in `data/processes/`. Every number below
is a citation to a specific published table, not a redistribution of the
document.

A free-to-read author-accepted-manuscript copy is deposited at UCL
Discovery (`discovery.ucl.ac.uk/id/eprint/10137829/`) and Warwick WRAP; that
copy is what was actually read to extract the numbers below, cross-checked
against a page-image render of the same PDF (not text extraction alone) for
Tables 4, 6, 7, 8, 9.

## Why this case study

The paper compares three ibuprofen routes by Aspen Plus process simulation
at a shared 500 g/day pilot scale: the industrial BHC process (the
benchmark), the Bogdan continuous-flow route, and a novel enzymatic variant
of the Bogdan route (its last step replaced with an Amano lipase-catalysed
hydrolysis in an ionic-liquid medium). This ledger uses the **Bogdan vs
enzymatic** pair: the two share the most process structure (identical first
two reactors, differing only in the third), which concentrates the
comparison on one real, decision-relevant question — is swapping a
KOH/methanol saponification for an enzymatic step in an ionic liquid
actually better? — rather than spreading the delta across two totally
unrelated catalytic systems (BHC uses HF, Raney nickel and Pd; Bogdan and
its enzymatic variant use neither).

## What "input" means here

Both Table 6 (Bogdan, PDF pages 12–13 of the AAM) and Table 8 (enzymatic,
pages 14–15) list, per reactor, an "Input" column (what was charged) and an
"Output" column (what left the reactor, including recovered/unreacted
material). This ledger's `mass_kg` values are the **Input** column only —
matching this project's own definition, "what was actually charged in that
step" (`docs/data.md`) — even where the Output column shows the same
material leaving in nearly the same amount (e.g. triflic acid, evidently
recovered within the simulated pass): it was still charged fresh at that
mass into that reactor, which is what the ledger tracks.

An intermediate carried from one reactor to the next **within the same
route** (4-isobutylpropiophenone from Reactor 1 to Reactor 2; methyl
2-(4-isobutylphenyl)propanoate from Reactor 2 to Reactor 3) is excluded as a
ledger input in both routes — it is not an externally sourced material, and
counting it would double the mass attributed to whatever produced it one
reactor earlier. This mirrors the letermovir benchmark's treatment of its
own carried-over intermediates. Table 8's Reactor 2 explicitly lists its
carried intermediate ("4 isobutylacetophenone", 542.65 g) as an input line;
Table 6's Reactor 2 does not list one at all (the two tables are not
internally consistent about this) — either way, this ledger excludes it in
both, consistently.

## This ledger's own arithmetic: functional-unit renormalization

The paper reports absolute g/day flows at one shared plant scale (500 g/day
of BHC's headline reactant), not separately normalized per route. The two
routes' own simulated ibuprofen output differs slightly — Bogdan: 495.7
g/day (Table 6, Reactor 3 output); enzymatic: 541.4 g/day (Table 8, Reactor
3 output) — a difference this project cannot ignore, since carbonroute's
comparison is only valid per a *shared* functional unit. **This ledger
therefore divides every charged mass by that route's own daily ibuprofen
output before entering it as `mass_kg`, converting the paper's shared-plant
figures onto a per-1-kg-ibuprofen basis for each route independently.** This
division is this project's own transparent arithmetic, not part of the
source data, exactly analogous to how the specification's own yield-based
functional-unit conversion works (`docs/data.md`) — every ledger step
carries `yield: 1.0` as a result, so carbonroute does not re-apply a second,
unwanted conversion on top.

## Values, with the exact source cell

| Material | Route | Table value (g/day) | Divisor (g/day) | Ledger `mass_kg` | Source |
| --- | --- | --- | --- | --- | --- |
| isobutylbenzene | bogdan | 277 | 495.7 | 0.558806 | Table 6, Reactor 1 input |
| propionic acid | bogdan | 152.9 | 495.7 | 0.308453 | Table 6, Reactor 1 input |
| trifluoromethanesulfonic acid | bogdan | 309.8 | 495.7 | 0.624975 | Table 6, Reactor 1 input |
| trimethyl orthoformate | bogdan | 219 | 495.7 | 0.441799 | Table 6, Reactor 2 input |
| methanol | bogdan | 1764.2 | 495.7 | 3.559007 | Table 6, Reactor 2 input |
| trifluoromethanesulfonic acid | bogdan | 1694.7 | 495.7 | 3.418802 | Table 6, Reactor 2 input |
| iodobenzene diacetate | bogdan | 555.6 | 495.7 | 1.120839 | Table 6, Reactor 2 input |
| potassium hydroxide | bogdan | 1175.2 | 495.7 | 2.370789 | Table 6, Reactor 3 input |
| methanol | bogdan | 6389.1 | 495.7 | 12.889046 | Table 6, Reactor 3 input |
| water | bogdan | 1283.8 | 495.7 | 2.589873 | Table 6, Reactor 3 input |
| isobutylbenzene | enzymatic | 392.2 | 541.4 | 0.724418 | Table 8, Reactor 1 input |
| propionic acid | enzymatic | 216.43 | 541.4 | 0.399760 | Table 8, Reactor 1 input |
| trifluoromethanesulfonic acid | enzymatic | 438.54 | 541.4 | 0.810011 | Table 8, Reactor 1 input |
| trimethyl orthoformate | enzymatic | 1141.3 | 541.4 | 2.108053 | Table 8, Reactor 2 input |
| methanol | enzymatic | 995.2 | 541.4 | 1.838197 | Table 8, Reactor 2 input |
| trifluoromethanesulfonic acid | enzymatic | 2017.3 | 541.4 | 3.726081 | Table 8, Reactor 2 input |
| iodobenzene diacetate | enzymatic | 661.30 | 541.4 | 1.221463 | Table 8, Reactor 2 input |
| water | enzymatic | 167.8 | 541.4 | 0.309937 | Table 8, Reactor 3 input |
| 1-butyl-3-methylimidazolium hexafluorophosphate | enzymatic | 4554.1 | 541.4 | 8.411710 | Table 8, Reactor 3 input, "Ionic liquid [BMIM][PF6]" |
| Amano lipase from *Pseudomonas fluorescens* | enzymatic | 62.85 | 541.4 | 0.116088 | Table 8, Reactor 3 input |
| phosphate buffer solution, 0.05 M | enzymatic | 874.8 | 541.4 | 1.615811 | Table 8, Reactor 3 input |

The Amano lipase preparation and the phosphate buffer solution are each a
formulated product/mixture, not a single CAS-identifiable substance;
`cas: null` is used for both, and both are correctly reported as unresolved
rather than guessed at.

## Electricity: not charged

Tables 7 and 9 report equipment **heat duty in kW**, not energy-per-batch or
energy-per-functional-unit. Converting kW to kWh needs an operating-time
basis the paper does not state cleanly enough to cite a specific number
from (a continuous-flow pilot's "on" time per day is not given). Rather than
assume one, this ledger charges no electricity at all
(`grid_factor.value_kgCO2e_per_kWh: 0.0`, documented as a scope
limitation in the ledger itself); the comparison below is a materials-only
comparison.

## CAS resolution

All CAS numbers were resolved live via PubChem PUG REST
(name → CID → synonyms, first CAS-shaped synonym validated against
`carbonroute.schema.cas_checksum_ok`), 2026-08-28.

## Coverage, measured

```
carbonroute coverage examples/case-studies/ibuprofen-bogdan-vs-enzymatic/ledger.yaml --a bogdan --b enzymatic
```

**52.9% of the differing mass resolves** (2 of 11 materials — methanol and
water, both fully covered). The dominant unresolved item is the ionic liquid
[BMIM][PF6] (8.41 kg/FU in the delta), followed by triflic acid, trimethyl
orthoformate and potassium hydroxide; none of these were found in ADEME Base
Carbone or ProBas/GEMIS (checked 2026-08-28). `carbonroute compare` returns
`indeterminate`, below the 80% ranking floor. The resolved part alone leans
toward the enzymatic route being higher, driven by its much larger ionic
liquid and buffer inputs being absent from that lean entirely — a case where
the *direction* even the partial evidence points is exactly why this project
never treats a partial resolution as a substitute for a real one.

## A dedicated attempt to close the [BMIM][PF6] and triflic acid gap

This case study's two largest unresolved items ([BMIM][PF6] at 8.41 kg/FU,
triflic acid at 4.54 kg/FU — together 86% of the unresolved mass) were the
subject of a dedicated follow-up investigation, on the reasoning that a real
production recipe (per `docs/bootstrap.md`) might close them the way it has
for several solvents. The result is a partial, honestly-documented dead end,
recorded here so a future session does not repeat the same dead ends:

- **[BMIM][PF6]**: its standard two-step literature synthesis is
  quaternization of 1-methylimidazole with 1-chlorobutane to
  [BMIM]Cl, then anion exchange with a hexafluorophosphate salt.
  A real, directly-verified yield (82.2%) for the *first* step was found
  and written up as `data/processes/1-butyl-3-methylimidazolium-chloride.yaml`
  (source: ChemSpider Synthetic Pages, entry 747, Tom Welton group,
  Imperial College London, DOI 10.1039/SP747). A citable, verified yield
  for the *second* step could not be obtained despite three separate
  attempts — the standard literature procedure (Organic Syntheses 2002,
  79, 236) sits behind a JavaScript browser check this session's tooling
  could not pass; three close patent analogues were found via search
  summaries but their PDFs 403'd/503'd on direct fetch, so the summarized
  numbers were discarded, unverified, rather than used. That step is
  recorded as `data/processes/1-butyl-3-methylimidazolium-hexafluorophosphate.yaml`
  using bare stoichiometry with no yield (a legitimate but loose lower
  bound). Even so, **the chain currently derives nothing**: running
  `carbonroute bootstrap` confirms both recipes are `SKIPPED`, because
  their own feedstocks (1-methylimidazole, 1-chlorobutane, potassium
  hexafluorophosphate) have no factor of their own, held or derived, and
  none was found in ADEME Base Carbone or ProBas/GEMIS by live query.
  (ADEME does hold a "1-chlorobutane" entry, but it is an IPCC AR6
  *atmospheric* GWP characterization factor for the substance as a
  released greenhouse gas — not a cradle-to-gate production factor — and
  was correctly not used for that reason.)
- **Triflic acid**: a directly on-topic patent, WO2011104724A2
  ("A process for the manufacture of triflic acid"), was identified but
  could not be fetched (Google Patents returned HTTP 503 repeatedly).
  The general industrial route (electrochemical fluorination of
  methanesulfonic acid) is documented in secondary sources but no
  quantities were recovered.
- A peer-reviewed process-simulation LCA of a structurally close ionic
  liquid, [BMIM][BF4] (not [PF6]), was found and directly verified:
  Baaqel, Bernardi, Hallett, Guillén-Gosálbez & Chachuat, *ACS Sustainable
  Chem. Eng.* 2023, 11, 7157 (DOI 10.1021/acssuschemeng.3c00547,
  open access via PMC10170515), reports **27.3 kgCO2e/kg**, sourced from
  ecoinvent 3.5 background data. The same paper states this is an order
  of magnitude higher than an earlier independent estimate for the same
  compound (Zhang et al., 3.5 kgCO2e/kg) — a real, citable illustration of
  just how uncertain even peer-reviewed structural/process-simulation
  estimates are for this class of chemical, and part of why this project
  did not treat either number as a usable proxy for [BMIM][PF6] specifically.
  (An initial web-search summary claimed this same paper gives 30.9
  kgCO2e/kg for [BMIM][PF6] itself; that number was checked directly
  against the paper's full text and does not appear anywhere in it — a
  fabricated citation, caught before use, not a real finding.)

**Conclusion**: this is not a failure of method, it is a directly-confirmed
absence of public data. The paper's own methodology section states its
background inventory came from GaBi + ecoinvent 3.6 — the same commercial
databases this project cannot access — for exactly these materials.
