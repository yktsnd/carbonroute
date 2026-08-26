# Limitations

## Three layers of automation difficulty

The specification (`docs/spec-ja.md` section 1.3) identifies three separate
reasons full automation of a route's carbon footprint is not possible
today, and locates this tool deliberately within only one of them.

**Layer one: data gaps.** Novel materials are absent from background
databases, and lab records of what was actually charged in a step are
scattered across free-text notebooks rather than structured data. This
layer is mostly mechanical — looking a material up, converting units,
carrying a value through an accounting sum — and is where automation has
the most leverage, because the work does not require a judgment call, only
consistent execution.

**Layer two: scale extrapolation.** A bench-scale reaction's solvent
loading and heating efficiency bear little relationship to the same
reaction run at plant scale, and there is no standardized method for
correcting one to the other. Getting this right needs a model of its own —
one this tool does not attempt to provide.

**Layer three: choice of assumptions.** System boundary, allocation rules,
the grid electricity emission factor, the GWP time horizon, the solvent
recovery rate assumed. None of these are facts to be looked up; they are
conventions that require a judgment call specific to the situation, and
that judgment call cannot be automated away without hiding it.

`carbonroute` automates layer one and explicitly refuses to automate layer
three: every assumption that belongs in that layer is pushed into the
ledger's `assumptions` block, stated in full at the top of every report,
and never defaulted silently. Layer two — lab-to-plant scale-up — is out of
scope for v0 entirely; the tool takes ledger masses at face value and does
not attempt to correct them for scale (spec section 5.2). This division is
also why the tool's central operation is a route-to-route diff rather than
an absolute calculation: differencing shrinks how much of layer one's data
gap you actually have to close, since materials and steps common to both
routes cancel before their missing data would ever need to be resolved.

## The accuracy ceiling of public-data-only work

The default configuration resolves factors only against redistributable,
citable public data — no ecoinvent, no other commercial background
database, unless a user explicitly supplies one as an adapter (spec
section 2, `docs/data.md`). Public LCI/LCIA sources are real and useful,
but they are also sparser and, for many specialty materials, systematically
less matched to a specific process than a commercial database curated for
exactly that purpose. Two consequences follow directly:

- Some materials that a commercial database would resolve will be reported
  as unresolved here. That is intended behavior — an unresolved material is
  reported as a gap, never silently filled (spec section 13) — but it means
  the tool's coverage, out of the box, is narrower than what a
  fully-provisioned LCA practice would have.
- Where a public factor does resolve, it may differ systematically from
  what the same material would score in a commercial database, for the
  same reasons background databases differ from each other in general:
  different underlying processes, different regional mixes, different
  vintages. `docs/uncertainty.md` lists this systematic public-vs-commercial
  gap as an explicitly open, unmeasured item (spec section 14) — the
  uncertainty model propagates dispersion *within* a source's stated
  values, not a correction for bias *between* sources.

This is a real ceiling on how accurate an absolute number produced this way
can be, and no amount of software polish removes it — it is a property of
what data is available to cite, not of how the data is used once found.

## Verifiability instead of accuracy as the design goal

Given that ceiling, the tool's stated goal is not to push accuracy as high
as possible within it — it is to make whatever accuracy is achieved
independently checkable (spec section 2: "compete on verifiability, not
accuracy"). Concretely, this shows up as:

- Every value's provenance class is retained and reported after
  aggregation, not just used and discarded (spec section 2, section 9).
- A report opens with the full text of the assumptions applied, the exact
  factor table versions and their hashes, and the resolution's provenance
  breakdown, before it states any conclusion — so a reader can check the
  inputs before trusting the output (spec section 9).
- `carbonroute lock` pins everything needed to reproduce a result byte-for-
  byte: schema version, tool version, ledger hash, factor table paths and
  hashes, the uncertainty config's path and hash, every resolved factor
  value and its provenance, and the RNG seed and iteration count.
- The Monte Carlo sampler is deterministic given its seed, specifically so
  that "reproduce this result" means exactly that, not "get something
  similar" (spec section 10).
- When the evidence does not support a ranking, the tool says so
  (`"indeterminate"`) instead of forcing out a number that looks more
  confident than it is (spec section 2).

None of this raises the accuracy ceiling described above. What it does is
let a third party — a reviewer, a colleague, a future version of the
person who ran the comparison — check the same inputs and arrive at the
same output, and argue about the assumptions rather than about whether the
arithmetic can be trusted. That is the trade this tool is built around: it
gives up the appearance of a precise absolute footprint in exchange for a
comparison whose basis can actually be audited.

## Measured: how far public data actually reaches

The specification listed, as an open question, what fraction of a real delta
set a factor table limited to solvents and common reagents could cover. The
letermovir benchmark answers it for one real case, and the answer is small.

Of the 43 materials whose charged mass differs between the two published routes,
openly licensed factors resolve **2 — 8.9% of the differing mass**. Catalysts,
which that same study showed can dominate a step's footprint at a fraction of a
percent by mass, resolve at zero.

This is not a defect in the ingestion scripts. It is what the openly licensed
LCI landscape contains for fine chemicals. Most of the numbers a process
chemist would need sit inside commercial databases that cannot be redistributed,
which is the constraint this project accepted at the outset and continues to
accept.

The consequence for a user is concrete: expect `carbonroute compare` to return
`indeterminate` on a real pharmaceutical route until you supply factors of your
own. `carbonroute coverage` tells you how far you are from a usable comparison
before you spend time on one, and the break-even calculation in the report tells
you how much the gap would have to be worth to matter. Those are the honest
deliverables at this level of data availability; a ranking would not be.
