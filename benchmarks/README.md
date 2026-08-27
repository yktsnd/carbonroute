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

## B2 — Published route comparison (implemented)

`benchmarks/letermovir/` holds a ledger for the two synthetic routes compared in

> Sorgenfrei et al., "Integrated Life Cycle Assessment Guides Sustainability in
> Synthesis: Antiviral Letermovir as a Case Study", *J. Am. Chem. Soc.* **2025**,
> 147, 40944. doi:10.1021/jacs.5c14470 — open access, PMC12593353.

The masses were extracted from the paper's supplementary workbook by
`scripts/extract_letermovir_ledger.py`; `benchmarks/letermovir/SOURCES.md` maps
every number back to the cell it came from. The authors scored those masses with
ecoinvent 3.10, which this project may not redistribute, so **the ledger travels
and the factors do not**. That is the whole shape of this benchmark.

### What the published study reports

| | Merck route | De novo route |
| --- | --- | --- |
| GWP, kgCO2e/kg (50% catalyst recovery) | 382 | 369 |
| GWP at 80% / 90% recovery | 350 / 342 | 323 / 311 |
| PMI, kg/kg | 147 | 127 |

The published ranking is **de novo below Merck, by about 3%** — a near-tie.

### Acceptance conditions

These were fixed before the assertions were written, and they deliberately do
**not** include reproducing 382 and 369.

1. **No absolute-agreement claim.** The tool resolves a small fraction of these
   routes from public data. `test_absolute_agreement_is_not_claimed` asserts the
   accounted total stays far below the published figure, so nobody can quietly
   start reading our number as theirs.
2. **The tool must not report a ranking it cannot support.** This is the
   condition that matters. On the fraction it can resolve, the Monte Carlo is
   overwhelmingly confident — *and confident in the direction opposite the
   published result*. A tool that printed that as its conclusion would be worse
   than no tool. The verdict must be `indeterminate`, with the coverage stated
   as the reason.
3. **Coverage is measured, not asserted.** The share of the differing mass that
   openly licensed factors reach is pinned as a regression bound, so adding a
   factor source visibly moves it.
4. **The break-even analysis must be reported and must be informative.** Rather
   than assume a value for the unresolved materials, the tool computes what they
   would have to average for the ranking to reverse, and reports it.
5. **Failure is reportable.** If a future factor table pushes coverage over the
   threshold and the tool then ranks the routes the *other* way from the
   published study, that result is documented here. It is not grounds for tuning
   the uncertainty configuration until it agrees.

### What the benchmark found

The numbers move as `data/factors/` grows; the current run is recorded in
`benchmarks/letermovir/RESULTS.json`, regenerated deliberately by
`scripts/record_letermovir_result.py`. The tests assert against that record and
against invariants, so an improvement in coverage shows up as a diff to review
rather than a failing assertion.

Two runs are worth keeping side by side, because the progression is the
argument for the design:

| | 9 substances (ADEME + USLCI) | 18 substances (+ ProBas/GEMIS, published PCFs) |
| --- | --- | --- |
| Delta materials resolved | 2 of 43 | 4 of 43 |
| Share of differing mass | 8.9% | 41.4% |
| Which way the resolved part leans | **Merck lower — against the paper** | **de novo lower — with the paper** |
| Break-even for the unresolved mass | 0.19 kgCO2e/kg | 3.59 kgCO2e/kg |
| Verdict | indeterminate | indeterminate |

At 8.9% the resolved fraction pointed the wrong way and the break-even was
0.19 kgCO2e/kg — below every organic solvent in the project's own table, so
the lean was worth nothing. Adding water and toluene, the two largest differing
materials, flipped it. The tool refused to rank in both cases, which is the
behaviour under test: the first refusal avoided publishing a wrong answer, and
the break-even statistic tracked the truth before the coverage did.

### What this benchmark caught

Before it existed, the tool treated an unresolved material as absent rather than
unknown, and reported `P > 0.9999` for the wrong ranking on 9% of the data. The
coverage gate in `Assumptions.min_delta_coverage` and the break-even calculation
in `compute.unresolved_flip_factor` both exist because this benchmark ran first
and failed. That is the argument for building the test set before the
calculation, and it is the reason section 12 of the spec puts it second.

### Known gaps

- Process energy is not in the ledger: the published inventory is material-only,
  so every step charges zero electricity. Any comparison here is a materials
  comparison.
- The published masses were already back-calculated to 1 kg of letermovir, so
  every step carries `yield: 1.0` and this benchmark does not exercise the
  functional-unit conversion. B1 covers that.
- Seven materials could not be resolved to a CAS from their names as written in
  the workbook, and are keyed by name. `SOURCES.md` lists them.
- The two source sheets classify materials by role with different granularity;
  `SOURCES.md` records the asymmetry rather than smoothing it over.

## Regression

`tests/test_regression.py` freezes the output of the analytic case. It fails on
any change in the numbers, including changes caused by a different numpy
version's sampler. When a change to the numbers is intended, update the frozen
values in the same commit and say why in the message.
