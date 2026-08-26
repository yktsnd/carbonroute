# Benchmarks

The spec (section 12) says the acceptance conditions are written before the
calculation code. This file is that commitment. It is deliberately explicit
about which benchmarks exist and which do not.

## B1 — Analytic case (implemented)

`benchmarks/analytic/` holds a ledger and a factor table small enough that the
correct answer can be worked out by hand. It pins the deterministic half of the
tool:

| Property | Acceptance condition |
| --- | --- |
| Functional-unit conversion | Adjusted masses equal the hand-computed `mass / prod(yields from this step on)` exactly, to 1e-12 relative |
| Solvent make-up | A solvent at recovery `r` contributes `mass * (1 - r)` |
| Zero cumulative yield | Raises `LedgerError`, does not return a number |
| Route total | Equals the hand-computed sum, to 1e-12 relative |
| Cancellation | A material with identical adjusted mass in both routes contributes exactly zero to the sampled difference, whatever its uncertainty class |
| Determinism | Two runs with the same seed produce identical `p_a_lower`, byte for byte |
| Unresolved handling | An unresolved material in the delta set produces a warning and appears in `delta_unresolved`; an unresolved material that cancels does not |

This benchmark tests the machinery, not agreement with the world. It cannot
tell you whether the tool's answers are true — only that they are the answers
the specification asks for.

## B2 — Published route comparison (NOT implemented)

The spec proposes the letermovir synthesis study (doi:10.1021/jacs.5c14470) as
the first real test set, and notes that whether the per-step primary data needed
to reproduce it is available in the public record was never confirmed.

It is still not confirmed. At v0 this benchmark is **absent, not failing**.
Nothing in this repository reproduces a published LCA, and no claim of
agreement with one is made anywhere in the documentation.

Acceptance conditions, fixed now so they cannot be relaxed later to fit
whatever the tool happens to produce:

1. **Ranking agreement is the pass condition.** The tool must place the two
   routes in the same order as the published study. Absolute agreement in
   kgCO2e is not required and must not be claimed.
2. **Provenance disclosure.** Every input in the benchmark ledger carries the
   table, page or SI section it came from. A value that cannot be pointed at
   in the published record does not go into the ledger.
3. **Sensitivity honesty.** If the published ranking is reproduced only for
   some settings of an assumption the study left open, the benchmark records
   the range over which it holds, rather than pinning the assumption to the
   value that happens to pass.
4. **Failure is reportable.** If the tool ranks the routes the other way round,
   that result is documented in this directory. It is not grounds for tuning
   the uncertainty configuration until it agrees.

To contribute B2: build the ledger from the public record, put it in
`benchmarks/letermovir/` with a `SOURCES.md` mapping every number to its
citation, and add the ranking assertion. If the data turns out not to be
available, record that finding here — a documented negative result is the
useful outcome.

## Regression

`tests/test_regression.py` freezes the output of the analytic case. It fails on
any change in the numbers, including changes caused by a different numpy
version's sampler. When a change to the numbers is intended, update the frozen
values in the same commit and say why in the message.
