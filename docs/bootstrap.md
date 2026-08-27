# Deriving factors when no database has them

## The problem this solves

The solvents a process chemist actually reaches for — THF, dichloromethane,
acetonitrile, 2-MeTHF — have no openly licensed, per-kilogram, cradle-to-gate
GWP that this project could find. The values exist; they sit inside commercial
LCI databases that cannot be redistributed. `docs/sources-investigated.md`
records the search. Looking harder does not fix it.

So `carbonroute bootstrap` stops looking a substance up and computes it instead,
from the same kind of description the tool already understands: what goes in,
how much energy it takes, what comes out.

This is not a new idea in the field — it is what the letermovir study did for
chemicals missing from its own database, and what the specification anticipated
in section 15.1 as the slot for structure- or process-derived estimates. What is
different here is that the derivation runs inside the tool, from files anyone
can read, with a citation attached to every number that was not arrived at by
arithmetic.

## How it works

`data/processes/<substance>.yaml` is a **production recipe**: the industrial
route, its feedstocks per kilogram of product, its process energy, its yield,
and a `{document, url, locator}` citation for each stated figure. The format is
documented in `data/processes/README.md`.

Given a recipe and the factors already in hand:

```
floor = sum(kg_feedstock_per_kg x factor_feedstock)
      + electricity_kWh_per_kg x grid_factor
      + fuel_MJ_per_kg x fuel_factor
```

A feedstock may itself have a recipe, in which case its derived value is used
and the recipes are resolved in dependency order. The table bootstraps itself.

## Why the result is a bound before it is an estimate

Every term in that sum is non-negative. An omitted term — an energy figure the
BREF does not give, a minor reagent, a feedstock with no factor of its own —
can therefore only make the result **too small, never too large**. What comes
out is a floor that follows from the data, and the tool says exactly which terms
it managed to include and which it did not.

That is a much stronger claim than an estimate. It is also, on its own, not very
useful: a floor cannot rank two routes if the gap above it is unbounded.

## From a bound to something usable

The floor becomes the low end of an interval. The high end is the floor divided
by a **completeness floor**: the assumed worst case for how much of the true
footprint the recipe captures. At the default of 0.5, a recipe is assumed to
account for at least half of the real value, so the interval spans a factor of
two.

That number is an assumption. It is not measured, not fitted, and not defensible
from first principles — it is a declared convention, exactly like the
indeterminate band, and it is a command-line option so that a reader can
disagree with it and rerun.

The interval is then published as a lognormal whose 90% range reproduces it:

```
median = sqrt(low x high)
gsd    = (high / low) ** (1 / (2 x 1.645))
```

which means a derived factor needs no special handling anywhere else. It flows
through the same Monte Carlo as every other factor, it is wide by construction,
and it can never collapse to a point — even a recipe that states every term gets
an interval, because a model of a plant is not a measurement of one.

## Keeping a model from being read as a measurement

- The `source` column starts with `DERIVED`, the counterpart of `ILLUSTRATIVE`.
- The provenance class is `structural_estimate`, the second-widest class.
- The `notes` column carries the full derivation: every term included with its
  arithmetic, every term omitted with the reason.
- Any report that consumes one prints a warning block naming the substance and
  its modelled range.

## Using it

```bash
carbonroute bootstrap \
  --processes data/processes \
  --grid-kgco2e-per-kwh 0.42 --grid-source "the grid factor you can cite" \
  --fuel-kgco2e-per-mj 0.07 --fuel-source "the fuel factor you can cite" \
  --report -o data/factors/derived.csv
```

Supplying no energy factors is allowed: those terms drop out, the bound gets
weaker, and the output says so. Supplying one without a source is refused — an
undocumented number is the thing this tool exists to prevent.

### Which energy factors to supply

The grid factor belongs to whoever runs the tool, not to the recipe, because it
depends on where the plant is — and that choice moves the answer more than most
of the chemistry does. Some citable options, verified live in ADEME's Base
Carbone (Licence Ouverte / Open Licence):

| What | Value | Where |
| --- | --- | --- |
| Grid electricity, France continentale, 2020 | 0.0599 kgCO2e/kWh | Base Carbone element id 28333, stated uncertainty 10% |
| Natural gas, boiler combustion | 0.243 kgCO2e/kWh | element id 25826 |
| Natural gas, mix | 56.8 kgCO2e/GJ = 0.0568 kgCO2e/MJ | element id 26629, stated uncertainty 5% |

**Read the France figure carefully before using it.** At 0.06 kgCO2e/kWh it is
among the lowest grid factors in the world, because the French grid is largely
nuclear. Applying it to a plant in a coal-heavy grid understates that plant by
more than an order of magnitude. Pick the factor for the geography you are
actually modelling and cite it; the tool records whatever you pass in the
derivation trace, but it cannot tell you that you picked the wrong one.

This is why `data/factors/derived.csv` as shipped carries **no energy terms at
all**. A repository-wide grid assumption would be a geography smuggled into
every comparison. The shipped table is a weaker, geographically neutral floor;
regenerate it with your own grid factor to tighten it.

`--report` prints the full derivation for every substance, which is the output
to read before trusting any of it.

## What this does not do

It does not model heat integration, recycle loops, co-product allocation, or
anything a real process engineer would insist on. It builds a floor out of a
linear recipe and widens it by a declared factor. Where a real cradle-to-gate
value exists under a licence that permits redistribution, that value should
replace the derived one — and when both are present the loader reports the
disagreement, which is the fastest way to find out how far off the model was.
