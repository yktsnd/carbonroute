# "Surely the data exists?" — yes, and here is who has it

It does exist. It is not free.

Every factor this project could not find — tetrahydrofuran, acetonitrile,
dimethyl sulfoxide, n-pentane — is in **ecoinvent**, and ecoinvent is sold under
an annual commercial subscription. Its licence page lists Single-User,
Enterprise, Developer and Educational tiers, with pricing on enquiry rather than
published ([ecoinvent.org/licenses](https://ecoinvent.org/licenses/), retrieved
2026-08-27). Sphera's GaBi is the other large commercial option. Buying one of
those is what practically everyone doing this work does.

The study this project benchmarks against did exactly that: its supplementary
workbook scores both letermovir routes against **ecoinvent 3.10**
([doi:10.1021/jacs.5c14470](https://doi.org/10.1021/jacs.5c14470), open access).
This repository can carry that study's *masses* and not its *factors*, and that
asymmetry is the whole reason `data/factors/` looks thin.

## So this project's gap is a choice, not a failure

The specification (section 2) requires the default configuration to run on
redistributable public data, and treats commercial databases as an optional
adapter. That is a deliberate trade: give up accuracy, keep the property that a
third party can re-run every number without buying anything. `docs/limitations.md`
argues the trade; this file just makes clear that it *is* one.

## What the well-resourced actually do

Named in the same paper's methods section, each built on a licensed database
plus internal primary data:

- **FLASC** (GSK) — fast LCA of synthetic chemistry.
- **PMI-LCA tool** (Merck, with the ACS Green Chemistry Institute
  Pharmaceutical Roundtable).
- **ChemPager** (Roche) — wraps the ACS GCIPR's SMART-PMI predictor.
- **Green chemistry process scorecard** (Novartis).

Alongside that, suppliers are increasingly asked for product-specific carbon
footprints through schemes such as **TfS** (which the specification cites). Those
numbers are real, current and supplier-specific — and they arrive under contract,
not on a website. The one this project found in public, Nobian's EPD for
dichloromethane, is the exception that shows how rare publication is.

## The part that should give everyone pause

A licence does not solve the problem. It moves it.

The letermovir authors report that on their first pass **only about 20% of the
chemicals in the synthesis were found in ecoinvent v3.9.1–3.11**, and that
ecoinvent "covers merely 1000 chemicals". They give a concrete example: diisopropylamine
and dimethylamine are in the database, while the downstream reagents actually used —
LDA, EDC — are not.

Compare that with this project's own measurement on the same two routes:

| | Chemicals resolved |
| --- | --- |
| The paper's first pass, with an ecoinvent licence | ~20% |
| This project, public data plus derived factors, no licence | 23.3% (10 of 43) |

Those are not quite the same quantity — theirs counts chemicals in the synthesis,
ours counts materials whose mass differs between the routes — so read it as an
order of magnitude, not a scoreboard. The point is not that a free table matches
a commercial one. It is that **the fraction of a real pharmaceutical route that
any database covers is small**, and the interesting work starts after the lookup
fails.

The paper's own answer to that was to reconstruct the missing chemicals from
literature process data by retrosynthesis. That is precisely what
`carbonroute bootstrap` does, and `docs/bootstrap.md` describes it. The
difference is that here the reconstruction is a file you can read, and its
result is published as a bound rather than a number.

Both approaches criticised in that same section — Merck's tool dropping
chemicals it cannot find, and FLASC substituting compound-class averages — are
failure modes this project deliberately avoids: a missing material is reported
as missing, and no proxy is silently substituted for it.

## If you have a licence, use it

`carbonroute` is built to take one. Export a per-kilogram cradle-to-gate table
from ecoinvent, SimaPro or openLCA into the CSV format in
[`docs/data.md`](data.md), keep the file **outside this repository**, and point
the tool at it:

```bash
carbonroute compare route.yaml --a merck --b denovo \
  --factors /path/to/your/ecoinvent_export.csv \
  --factors data/factors/derived.csv
```

Two things then happen that are worth having. Coverage jumps, so the tool will
actually rank the routes instead of returning `indeterminate`. And where a
licensed value and a derived one cover the same substance, the loader records the
disagreement and prints both — which is the cheapest available check on how far
the bootstrap model is off. A derived floor sitting above a licensed measurement
means one of the two is wrong, and you want to know that.

Do not commit the export. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
