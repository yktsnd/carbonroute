# Deciding a comparison without knowing the values

## The observation this rests on

Ranking two routes is an easier question than measuring either one, and it
stays easier when the data is bad.

`carbonroute compare` normally refuses to rank when too little of the
differing mass resolves to a factor, and that refusal is the right default:
a ranking computed from half the mass is a ranking about half the mass. But
the refusal is sometimes stronger than the situation deserves. You do not
always need to know what a missing factor *is*. You only need to know enough
about where it *cannot be* for the answer to stop depending on it.

`--bounds` asks that question.

## What it computes

The signed difference between two routes is linear in every factor:

```
delta = resolved_delta + Σ (delta_mass_i × f_i)
```

Give each unresolved material an interval its true factor is asserted to lie
in, and this expression becomes a box. Because the expression is linear and
each term's sign is fixed by the sign of `delta_mass_i`, the extreme corners
of that box are known without any search:

- **largest** `delta`: take `high` where `delta_mass_i > 0`, `low` where `delta_mass_i < 0`
- **smallest** `delta`: the other way round

Two evaluations settle it. If both extremes fall on the same side of zero,
the ranking is the same everywhere in the box — including at the true
values, wherever they turn out to be.

There is no sampling and no approximation here. The reported worst cases
*are* the worst cases.

One side is often enough. If `delta` cannot get above zero, it is negative
everywhere in the box no matter how far below zero the other extreme runs.
So a material left deliberately unbounded above — an honest position, and a
common one — does not block a conclusion it can only reinforce.

## A bound is not a factor

This distinction is the whole design, and the code enforces it:

- bounds never enter the Monte Carlo
- bounds never contribute to a total, indicative or otherwise
- bounds never appear in a factor table
- bounds never turn an unresolved material into a resolved one, so
  **coverage is reported exactly as it would be without them**

A bound is used for one thing only: asking whether the verdict survives
everywhere inside it. The answer is always reported together with the box it
was proved over, because a proof over the wrong box is worth nothing.

## Why this lets bad data be used honestly

Two published estimates for the same substance that disagree by a factor of
eight cannot be averaged into a factor anyone should trust. Averaging them
would manufacture a precision neither study supports.

They can, however, *bracket* one. The interval spanning both is a defensible
bound precisely **because** it is wide enough to contain the disagreement.
And if the verdict holds across that whole interval, then the disagreement
was never load-bearing: the comparison can be settled without settling the
argument.

This is what turns unusable literature into usable evidence. The bar for
"good enough to bound with" is far lower than the bar for "good enough to
compute with", and for a comparison the lower bar is frequently all you need.

## When it does not decide

The useful output then is not another "indeterminate" but **the inequality
that would decide it**. For each unresolved material, the report gives the
value at which the ranking ties, holding every *other* unresolved material at
its least favourable admissible value. Because the others are held
adversarially, a material that clears its own threshold settles the
comparison on its own.

Three things a row can say:

| status | meaning |
|---|---|
| a threshold | the tie point; the verdict holds on the stated side of it |
| `any value — cannot flip it` | no non-negative value of this material reaches the tie point, so the verdict does not rest on it at all |
| `not computable` | another material carries no ceiling; bound that one to get this one |

This converts "we need data" into "we need to know whether this one number
is above 1.7", which a chemist can often answer immediately, and which tells
anyone gathering data exactly which measurement is worth paying for.

## Using it

```bash
carbonroute compare route.yaml --a A --b B --bounds bounds.yaml
```

The file:

```yaml
bounds:
  "cas:174501-64-5":
    low: 3.5
    high: null          # omitted ceiling = "not bounded above"
    rationale: >
      Why this interval is defensible. Required — an interval without a
      stated reason is exactly the kind of unexplained number this project
      exists to keep out, and it is cheap to demand one, because a bound
      that cannot be justified in a sentence should not be asserted.
    sources:
      - "A citation."
```

Keys are the same material keys `carbonroute resolve --show-missing`
prints (`cas:...` or `name:...`). `low` is required and must be `>= 0`; no
cradle-to-gate factor is negative, so zero is always a true floor — which is
also what a material with no bound at all is given, leaving its ceiling open
and saying so.

## Choosing a defensible bound

Ranked roughly by how hard they are to argue with:

1. **Mass balance.** A 0.05 M aqueous buffer is >99% water by mass, so its
   footprint is bounded below by its water content times the water factor
   already held. This is arithmetic, not estimation.
2. **A held factor for a simpler relative.** Potassium hydroxide's ceiling
   can be set at several times the sodium hydroxide factor already in the
   tables — same chlor-alkali chemistry, different alkali metal.
3. **The empirical floor of the loaded tables.** "No organic substance in
   any table we hold falls below X" is a weak claim, which is what makes it
   safe for materials whose mass is too small to matter.
4. **Published estimates, used as brackets.** Including estimates that
   disagree with each other — see above.

The direction matters. For each material, work out which end of its interval
argues *against* the conclusion you expect, and spend the effort there. A
generous bound on the material that opposes your verdict costs nothing if the
verdict survives it, and costs you the verdict honestly if it does not.

## The worked case

`examples/case-studies/ibuprofen-bogdan-vs-enzymatic/` is the case this
feature was built for: 52.9% coverage, no ranking possible from factors
alone, and nine unresolved materials. Under bounds, seven of the nine turn
out to be incapable of changing the answer at any value, one is irrelevant,
and the entire comparison reduces to a single inequality about a single
ionic liquid. See that directory's `SOURCES.md` for the full account,
including what the result then revealed about the ledger itself.
