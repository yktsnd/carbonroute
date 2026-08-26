# Uncertainty model

## The unhedged statement first

**Every geometric standard deviation (GSD) in
`src/carbonroute/config/uncertainty.yaml` is an uncalibrated placeholder.**
They were set by analogy with the ecoinvent pedigree matrix (Weidema &
Wesnaes 1996 and the ecoinvent data quality guideline), not by fitting to
any measured dispersion of GWP values for the material classes this tool
actually sees. The file says so at the top; this document says so again,
because the numbers directly set how wide the Monte Carlo distribution is
for every factor, and therefore directly move `p_a_lower` and the verdict a
report shows. Nothing about the tool's design makes an uncalibrated GSD
safe to trust as-is — treat the current values as a placeholder under test,
not as data (spec section 7.5, section 14). Widening or narrowing them is
one of the easiest ways to accidentally change a route comparison's
conclusion, so if you touch `uncertainty.yaml`, say what you changed and
why in the same place you report the result.

## How the lognormal-from-GSD model works

Each material's GWP factor `g_i`, as read from a factor table, is treated
as the **median** of a lognormal distribution rather than as an exact
number. The distribution's spread is set by the geometric standard
deviation assigned to that row's `uncertainty_class`:

```
g = value * exp(sigma * z),   z ~ N(0, 1),   sigma = log(gsd)
```

A GSD of 1.0 means "no dispersion" — the factor is used at its point value
and the sampler is not invoked for it at all. A GSD of 1.5, the current
default for `background_db`, means the interval that contains the middle
90% of the distribution spans roughly a factor of 2.2 either side of the
median. The eight classes and their current placeholder GSDs are listed in
`uncertainty.yaml` and summarized in `docs/data.md`.

The electricity grid factor gets exactly the same treatment: one draw per
Monte Carlo iteration, using the GSD for
`assumptions.grid_factor.uncertainty_class` (`assumption` by default).

## One draw per material key, applied to the difference

This is the part of the model that makes the comparison-first design
actually pay off, so it is worth being precise about it.

`carbonroute` does not draw a separate random factor for route A's copy of
a material and route B's copy of the same material. It draws **one**
random multiplier per material key (spec section 7.5) and applies it to
the **mass difference** between the two routes for that key:

```
delta_j = sum_i(delta_mass_i * g_ij) + delta_elec * grid_j
```

where `delta_mass_i = mass_in_A_i - mass_in_B_i` and `g_ij` is the j-th
Monte Carlo draw of material `i`'s factor. If a material is used in equal
adjusted quantity by both routes, `delta_mass_i` is zero and that draw
contributes nothing regardless of how uncertain the factor is — the
material's uncertainty cancels exactly, on every iteration, not just on
average. If a material appears in only one route, its full uncertainty
carries into the comparison, because there is no equal-and-opposite term to
cancel it against.

Concretely: two routes that both use large quantities of toluene, whose GWP
factor is genuinely uncertain, will not have that uncertainty inflate the
spread of the *comparison* at all if both routes use the same (adjusted)
amount of it. Only the quantities and materials that actually differ
between the routes drive the width of the outcome distribution. This is
also why the diff step (`compute.diff_routes`) drops rows whose adjusted
masses match exactly and only warns about unresolved materials when they
are part of the surviving, non-cancelling difference (spec section 7.4).

This is the same idea DeltaLCA applies to comparing electronics hardware
designs (arXiv:2311.09611): compare by differencing before propagating
uncertainty, so that the analysis only has to be accurate about what is
different, not about everything either design contains.

Sampling is deterministic given a seed: draws happen in sorted material-key
order using `numpy.random.default_rng(seed)`, so the same ledger, factor
table, and seed reproduce byte-identical output (spec section 10).

## What the statistics mean

- `p_a_lower` = the fraction of Monte Carlo iterations where route A's
  total came out lower than route B's — an estimate of `P(GWP_A < GWP_B)`
  under the assumed distributions, not a frequentist confidence level and
  not a statement about which route is "truly" lower in some
  distribution-free sense.
- The verdict is `"indeterminate"` whenever `p_a_lower` falls inside
  `assumptions.indeterminate_band` (0.4-0.6 by default) — not because
  0.4-0.6 has any particular statistical justification, but as a
  deliberate convention so a near-tie is never dressed up as a ranking.
  The band's default has no empirical basis either; it, too, is
  configurable and its rationale is "no rationale, just a convention"
  (spec section 7.6).
- The reported median and 90% interval of the difference describe the
  *modeled* uncertainty given the GSDs above — if the GSDs are wrong, these
  intervals are wrong in the same direction, silently.

## Open items (spec section 14)

These are listed in the specification as explicitly unresolved as of v0,
and remain unresolved in this codebase:

- **The GSD assigned to each provenance class.** Current values are a
  pedigree-matrix-inspired guess, not a calibrated estimate.
- **The Monte Carlo iteration count.** 10,000 is a provisional default;
  see `docs/convergence.md` for what a convergence check would look like
  and confirmation that one has not yet been run.
- **The probability range treated as indeterminate.** 0.4-0.6 is a
  convention, not a derived threshold.
- **The systematic gap between public-data-only values and values from a
  commercial database like ecoinvent for the same material.** Nothing in
  this tool currently measures or corrects for this; a route compared
  using only public data could be biased relative to the same comparison
  done with commercial background data, in a direction and magnitude that
  is currently unknown.
- **How much of a real difference set a solvent-and-common-reagent factor
  table can actually cover.** The first factor tables this project expects
  people to build are scoped to solvents and generic reagents (spec
  section 12, step 4); how large a fraction of typical route-to-route
  differences that scope resolves, versus leaving unresolved, has not been
  measured.

None of these has a target date attached in the specification. Anyone
relying on `carbonroute`'s probability output for a real decision should
treat the list above as open questions about that output's reliability,
not as a routine disclaimer.

## What the Monte Carlo does not cover

The sampling above describes the dispersion of the factors that were *found*.
It says nothing about the materials that were not. Treating an unresolved
material as absent is the same as assigning it a factor of zero, which is
exactly the silent default the specification forbids (section 13).

Two mechanisms keep that gap visible.

**A coverage floor.** `assumptions.min_delta_coverage` is the share of the
differing mass that must resolve before any ranking is reported. Below it the
verdict is `indeterminate` and the report says why, no matter how narrow the
interval over the resolved part looks. A tight interval over a tenth of the
problem is not a tight answer. The 0.8 default has no empirical basis; like the
indeterminate band it is a declared convention, and it lives in the ledger so
that a reader can disagree with it in writing.

**A break-even factor.** `compute.unresolved_flip_factor` refuses to guess what
the missing materials are worth and instead computes what they would have to
average for the ranking to reverse:

```
breakeven = -(resolved delta GWP) / (signed unresolved delta mass)
```

A small break-even means the ranking rests on the missing data. A large one, or
none at all — which happens when the unresolved mass leans the same way the
resolved part already does — means it survives most of what the gap could hold.
Either way the reader gets a number that follows from the data rather than an
assumption smuggled in as a zero. It assumes a single average across the
unresolved set, so a sufficiently lopsided individual material can still
reverse things; the report says so.

On the letermovir benchmark this is the difference between a confident wrong
answer and a useful refusal. See `benchmarks/README.md`.
