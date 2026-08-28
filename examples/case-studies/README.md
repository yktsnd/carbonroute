# Case studies: additional real published route comparisons

This folder holds route comparisons built from real, published papers,
beyond the primary benchmark featured in [`benchmarks/`](../../benchmarks/)
and in the top-level README. They exist to answer a simple question:
*does carbonroute's coverage-gated, ranking-only behaviour hold up across
more than one paper, or did we just get lucky (or unlucky) with the
featured example?*

Short answer: yes, it holds up. Every real paper we tried so far hits the
same wall — cradle-to-gate LCA factor data for specialty solvents and
reagents is thin in public sources, so the *measured, resolvable* fraction
of each route's mass is well under 100%. carbonroute reports exactly that
fraction and refuses to rank routes it can't cover, rather than filling
the gap with an invented number.

## How to read the table

`coverage` is the fraction of the union of both routes' post-cancellation
delta mass (kg per functional unit) that resolves to a public factor.
`verdict` is what `carbonroute compare` actually prints for that pair.

| Case study | Paper | Coverage | Verdict from factors | Verdict from bounds |
|---|---|---|---|---|
| [`ibuprofen-bogdan-vs-enzymatic`](ibuprofen-bogdan-vs-enzymatic/) | Grimaldi et al., *ACS Sustainable Chem. Eng.* 2021 | 52.9% | `indeterminate` | **decided** — `bogdan` lower, below 51% IL recycling |
| [`benchmarks/letermovir`](../../benchmarks/letermovir/) | Sorgenfrei et al., *J. Am. Chem. Soc.* 2025 (CC BY) | 75.5% | `indeterminate` | not attempted |
| [`zif8-dmf-vs-glycerol-carbonate`](zif8-dmf-vs-glycerol-carbonate/) | Sessa et al., *ChemSusChem* 2025 (CC BY) | 6.8% | (below `min_delta_coverage`, no ranking attempted) | not attempted |

Letermovir has the highest coverage and is the demo in the top-level
README, since it best shows carbonroute narrowing a comparison as far as
public data allows.

**Ibuprofen is the one that gets decided.** It has the *worst* coverage of
the two, and it is nonetheless the case that ends in an answer — because
`--bounds` (see [`docs/bounds.md`](../../docs/bounds.md)) asks whether the
ranking is the same everywhere the missing factors could be, rather than
what they are. Seven of its nine unresolved materials turn out to be
incapable of changing the answer at any value; the whole comparison
reduces to one inequality about one ionic liquid, and to one recycling
rate. That case study's `SOURCES.md` is the fullest worked example in the
repository, and it also records the ledger defect that getting a decisive
answer exposed.

## Reproducing a case study

```bash
carbonroute validate examples/case-studies/<name>/ledger.yaml
carbonroute coverage --ledger examples/case-studies/<name>/ledger.yaml --a <route_a> --b <route_b>
carbonroute compare  --ledger examples/case-studies/<name>/ledger.yaml --a <route_a> --b <route_b>
```

Route IDs for each case are listed in that case's `ledger.yaml` and
`SOURCES.md`.

## A rejected candidate, for the record

A fourth paper (a sertraline "digital twin" sustainability assessment,
not included here) was investigated and **rejected**, for two reasons:

1. Its own abstract states the underlying values come from "literature-derived
   data, machine learning models, and digital twin–based sustainability
   assessment tools" — i.e. AI/ML-modelled estimates, not primary
   measurements. carbonroute's factor table never accepts AI-generated
   numbers, so this source can't be used regardless of how convenient its
   figures look.
2. A supplementary-data citation surfaced during investigation (a Zenodo
   DOI) was checked directly against the Zenodo API and resolved to an
   unrelated economics journal — the citation does not exist as claimed.

Neither of these is a reason to distrust the paper's own chemistry, only
a reason it can't be a carbonroute data source. It's noted here so the
"why isn't this in the case studies?" question has an on-the-record
answer.
