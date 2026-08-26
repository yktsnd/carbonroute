# Monte Carlo convergence

## Status: unverified

`assumptions.monte_carlo.iterations` defaults to 10,000
(`src/carbonroute/schema.py::MonteCarloSettings`). This number is a
provisional default carried over from the specification (spec section 7.5)
and has **no convergence study behind it in this codebase.** Nobody has yet
run the procedure below and recorded the result. Until that happens, treat
10,000 iterations as "probably enough for a rough answer," not as a value
chosen because it was shown to be enough.

This matters because the headline outputs of `compare` —
`p_a_lower`, the verdict, the median and 90% interval of the difference,
and the reversal thresholds in `sensitivity.py` — are all Monte Carlo
estimates. Every one of them carries sampling noise that shrinks as the
iteration count grows and never fully disappears. An iteration count that
is too low for a given decision can flip `p_a_lower` across the
indeterminate band, or across 0.5, purely from RNG noise on a re-run with a
different seed, without anything about the routes or the factor table
changing.

## The procedure

The check is a stability check on the statistic that matters
(`p_a_lower`), not a formal proof of convergence:

1. Fix the routes, the factor table, and the assumptions — use the actual
   comparison you care about, not a synthetic stand-in.
2. Run the comparison at each of 1e3, 1e4, 1e5, and 1e6 iterations.
3. At each iteration count, repeat with several different seeds (`--seed`)
   rather than running once. A single run at a large iteration count can
   still land on an unlucky seed; what you want is the *spread* of
   `p_a_lower` across seeds at each count, not a single point estimate.
4. Plot or tabulate `p_a_lower` (and, if the decision depends on it, the
   delta median and 90% interval) against iteration count, with the
   across-seed spread shown at each count.
5. Find the iteration count where that spread becomes small relative to
   the precision the decision actually needs. If the decision only cares
   whether `p_a_lower` is above 0.6, below 0.4, or in between, "small
   relative to the decision" can be a fairly wide tolerance. If the
   decision hinges on whether `p_a_lower` is 0.52 or 0.58, it needs to be
   much tighter, and 10,000 iterations may not be enough.
6. Use the smallest iteration count that clears that bar as the default
   for that class of comparison — not necessarily 10,000, and not
   necessarily the same number for every comparison. A route pair with a
   short delta-material list and modest GSDs will converge faster than one
   with many uncertain, non-cancelling materials.
7. Record the seeds, iteration counts, and the resulting spread alongside
   the conclusion, the same way any other part of a reproducible
   comparison is recorded (a `carbonroute lock` file captures the seed and
   iteration count actually used, but not a convergence study — that is a
   separate artifact you keep yourself).

## What "enough" means here

There is no universal iteration count that is "enough." The right count
depends on:

- **How close `p_a_lower` is to 0.5 or to the edges of the indeterminate
  band.** A comparison that lands at `p_a_lower = 0.95` needs far fewer
  iterations to confidently clear the band than one that lands at 0.62.
- **How many non-cancelling materials are in the delta set**, since each
  contributes its own sampling noise; a longer, more uncertain delta list
  generally needs more iterations to settle.
- **How fine a distinction the decision requires.** Screening ("is A
  probably better than B, roughly?") tolerates more noise than a
  publication appendix where a specific `p_a_lower` value is quoted and
  will be read precisely.

Because of this, the practical recommendation is not "always use N
iterations" but "run the four-point-times-several-seeds check above for
the specific comparison you are about to rely on, at least once, before
trusting its `p_a_lower` to the precision you need." Reusing that
comparison's iteration count for closely related re-runs (same routes,
adjusted assumptions) is reasonable; carrying it over to a structurally
different comparison is not.

## What this file is not

This is a description of the procedure, not a report of having run it.
No convergence data for any real comparison currently ships with this
repository. If you run the procedure above, consider contributing the
result (which comparison, which seeds, what the spread looked like) so the
10,000 default in `schema.py` can eventually be replaced by a justified
one, per spec section 14.
