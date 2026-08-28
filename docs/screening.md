# Screening a reaction database

## The question

"Is the enzymatic route greener than the chemical one?" is asked one
molecule at a time and answered, at best, one paper at a time. Rhea holds
about 18,500 curated enzymatic reactions. Building a sourced ledger for
each — the way
[`examples/case-studies/beta-arbutin-chemical-vs-enzymatic/`](../examples/case-studies/beta-arbutin-chemical-vs-enzymatic/)
was built — is not a project anyone finishes.

`carbonroute screen` answers a narrower question across the whole database
instead: **for each enzymatic reaction, how much solvent would a chemical
plant have to recover before the enzyme stopped winning?**

## Why it is affordable

Not a shortcut — a structural property of the diff.

When two routes make the same product, everything common to both cancels
(spec section 7.4). For enzyme-versus-chemistry the part that cancels is the
expensive part to look up: the substrate and the product, different in every
one of the 18,500 reactions. What survives is

- **enzymatic side:** the cofactor — UDP-glucose, NADPH, SAM, acetyl-CoA
- **chemical side:** the protecting groups, activator, base and solvents

and both are small, closed, recurring vocabularies.
[`data/rhea/README.md`](../data/rhea/README.md) measures the first one
rather than assuming it: of 14,251 distinct participants, 63 appear in 100
reactions or more and 12 appear in over a thousand; the top 30 cover 47.8%
of all participant slots. The uncovered tail is precisely the part that
cancels.

So the factor work is bounded by the vocabulary, in the tens of substances,
not by the number of reactions. After that each reaction costs one
arithmetic evaluation — the whole 406-reaction UDP-hexosyltransferase class
screens in about a second.

**That "about a second" is the cost of screening reactions against a class
template that already exists — not the cost of building one.** A template
starts from one real, fully-quantified published chemical procedure, found
and verified by reading the actual paper, exactly as every row of
`data/factors/` is sourced. That step is not fast and is not claimed to be.
What scales for free is the number of *reactions* screened against a given
template; adding the *next* class still costs the same literature work
`data/processes/` and `data/factors/` always have.

**Nor does "bounded vocabulary" mean one cofactor is automatically one
clean reaction type.** UDP-glucose happens to be almost entirely
glycosylation, which is why it was the first class built — but it is not
representative. CoA (1,649 reactions, the single most common small-molecule
participant besides water/H⁺/O₂) covers acetylations *and* Claisen
condensations *and* redox steps that share nothing chemically; SAM (954
reactions) covers O-, N- and C-methylations that don't share one clean
"chemical counterpart" either. A cofactor only tells you the reaction
*consumes* it, not what it *does* — see `ClassTemplate.matches` and the
`expected_mass_delta` check below, which is what actually decides whether a
given reaction belongs in a class, checked from molecular structure rather
than assumed from which cofactor is present.

## Picking the next class: EC number, not raw frequency

Raw participant frequency (`data/rhea/participants.csv`, sorted by
`n_reactions`) is the wrong axis for choosing what to build next. It ranks
UDP-glucose around 20th, well behind CoA (1,649 reactions) and SAM (954) —
but those two are exactly the cofactors "Nor does bounded vocabulary..."
above shows are chemically mixed. A cofactor's total reaction count is a
population figure, not a homogeneity figure; picking the biggest one first
would have meant building a template for a class that is not actually one
transformation.

The EC (Enzyme Commission) number is the field's own answer to "what
transformation does this enzyme perform" — a classification maintained
since the 1960s specifically to separate reactions like these. Grouping
Rhea's reactions at the **third EC level** (`2.4.1`, not the full
`2.4.1.218`) gives 252 groups from the 41.1% of reactions that carry an EC
annotation at all (7,635 of 18,558) — fine enough to mean something
chemically, coarse enough that the biggest groups are worth building
against. The four largest:

| EC group | reactions | dominant participant | mass-delta clusters (top bins) | coverage |
|---|---|---|---|---|
| 1.1.1 | 526 | NAD(+) / NADP(+) | −2.0 (loses 2H: an oxidation) | 100% of 283 resolvable |
| 2.1.1 | 500 | SAM | +14.0, +15.0, +28.1, +42.1 (mono/di/tri-methylation, ±1 proton) | 99.5% of 431 |
| 2.3.1 | 382 | acetyl-CoA | +41.0, +42.0 (acetylation, ±1 proton) | 99.3% of 134 |
| 2.4.1 | 400 | UDP-glucose | +162.1, +163.1, +324.3 (hexosylation, ±1 proton, bis-transfer) | 100% of 131 |

Every one of these clusters tightly into 2–4 bins that are exact multiples
or ±1-proton offsets of one signature mass — the same pattern
`expected_mass_delta` already polices for UDP-glucose, reproduced
independently in three more groups. That is the mechanism this table
exists to demonstrate: restricting to an EC-3-level group turns "shares a
cofactor" into "shares a cofactor *and* a transformation," which raw
cofactor frequency cannot do — grouping by CoA alone (no EC restriction)
mixes exactly the acetylation and Claisen-condensation chemistry the
paragraph above warns about, but CoA reactions restricted to EC 2.3.1
*and* to its dominant participant, acetyl-CoA specifically, land in two
bins covering 99.3%.

**What this does and does not prove.** It confirms the `expected_mass_delta`
check will do its job on these groups — a new template's homogeneity
assumption is checkable in advance, from data already in this repository,
before spending research time on it. It does **not** mean one published
procedure is automatically the right chemical counterpart for a whole EC
group: EC 2.1.1's +14.0 cluster contains O-, N- and C-methylations alike,
which share a mass delta but not a bench procedure (different methylating
agent, different protecting-group strategy by site). Confirming mass-delta
homogeneity is step 1 of building a class, not a replacement for step 2 —
finding and reading one real paper for the transformation actually being
templated.

**The concrete result applied so far:** UDP-alpha-D-galactose (CHEBI:66914,
143 reactions) was added to the shipped class alongside UDP-glucose,
because it is glucose's C4 epimer — identical molecular formula, identical
MW (564.29), so identical 162.14 anhydrohexosyl mass delta, verified by
RDKit rather than assumed from the name. That is a genuinely free
extension: no new chemical procedure needed, because the existing one's
mass arithmetic already applies unchanged. UDP-N-acetylglucosamine
(CHEBI:57705, 41 reactions, the third-most-common EC 2.4.1 cofactor) was
deliberately **not** added the same way — it carries an extra acetamido
group, so its expected_mass_delta is not 162.14, and folding it into this
class without checking would have silently mis-templated 41 reactions. It
is a candidate for its *own* class, not a free line in this one.

## What a screen is, and is not

A `compare` run models two routes someone actually published. A screen
models one published route — the enzymatic one, from Rhea's curated
stoichiometry — against a **class template**: a single real chemical
procedure, taken from one cited paper, applied to every substrate in the
class.

That extrapolation is the method's central assumption, and it is the reason
a screen's output is a **ranked shortlist of reactions worth spending a
real `compare` on**, never a verdict about any individual reaction.

Every template material declares its own basis, the same way
`data/processes/` recipes declare `stated` vs `stoichiometric`:

| basis | meaning |
|---|---|
| `sourced` | the amount is read from the template's own cited paper |
| `generalised` | the amount is extended beyond that paper — a different substrate, or a standard reagent it did not itself use. The extension is spelled out in the material's `note`. |

The loader refuses a material with any other basis, or with no note.

## The output: a recovery threshold, not a verdict

A class template is built from a published **bench** procedure, and bench
procedures throw their solvent away — the shipped
UDP-glucosyltransferase template charges over 800 kg of solvent per kg of
product. A plant does not. A screen that only reported the verdict at zero
solvent recovery would mostly be reporting on laboratory glassware, and
would be emphatically, uselessly pro-enzyme.

So the headline number is the **solvent recovery threshold**: the rate at
which each verdict stops holding. Industrial distillation routinely recovers
90–95%, which gives the number an external yardstick:

- a reaction still decided at 99% recovery has an advantage that does not
  come from solvent at all
- one that turns over at 40% is one where the published chemistry, not the
  enzyme, was doing the work

## Enzymatic conversion is the other half of that same asymmetry

Every threshold above assumes the enzyme converts stoichiometrically — that
`cofactor_kg` equals the bare stoichiometric amount, no losses. Real
enzymatic routes do not run at 100% conversion. Meanwhile the chemical side
of the same ledger was never given that courtesy: a class template's
amounts are stated per mole of *product*, so the source paper's own real
yield is already baked into every `sourced` figure — for the shipped
UDP-hexosyltransferase template, 62% glycosylation times 85% deprotection,
52.7% overall. One side of the comparison was discounted for real chemistry;
the other was not. Every solvent-recovery threshold this document has
published — including the 85.58% / 86.42% / 91.54% below — is therefore an
**upper bound**: the recovery a plant would need if the enzyme were perfect.
A real enzyme, converting at less than 100%, needs less recovery to still
lose the comparison, or more recovery to still win it — the true break-even
point sits somewhere on a plane, not on a line.

Enzymatic conversion is now a first-class, declared variable rather than an
implicit assumption. `screen_reaction` takes `enzymatic_yield` (default
`1.0`) and `reference_recovery` (default `0.90`); `cofactor_kg` becomes
`stoichiometric / enzymatic_yield`, and `screen_all` takes and records the
same two arguments. Two questions follow from making it explicit:

- `minimum_enzymatic_yield(diff_at_yield, assumptions, bounds)` — bisection,
  mirroring `solvent_recovery_threshold` above. Holding the chemical plant
  at `reference_recovery`, what is the *lowest* conversion at which the
  verdict still holds? `0.0` means the verdict holds at any conversion;
  `None` means it is not decided at that recovery even with a perfect
  enzyme.
- `break_even_frontier(reactions, template, structures, table, assumptions,
  bounds, yields=(...))` — re-screens the whole class at each conversion in
  `yields`, returning one `FrontierPoint(enzymatic_yield, decided,
  min_threshold, median_threshold, max_threshold)` per point. This is the
  verdict's boundary on the (conversion, solvent recovery) plane, not a
  single number.

`ScreenResult` gained `enzymatic_yield`, `min_enzymatic_yield` and
`reference_recovery` to carry this through to the report. From the CLI:
`carbonroute screen --enzymatic-yield 0.5 --reference-recovery 0.90
--frontier`.

Running the frontier against the shipped class (406 matched, 388 decided at
every point):

| enzymatic conversion | min threshold | median | max |
|---|---|---|---|
| 100% | 85.58% | 86.42% | 91.54% |
| 90% | 83.94% | 84.87% | 90.54% |
| 80% | 81.89% | 82.94% | 89.30% |
| 70% | 79.25% | 80.44% | 87.70% |
| 60% | 75.73% | 77.12% | 85.57% |
| 50% | 70.80% | 72.47% | 82.59% |
| 40% | 63.41% | 65.50% | 78.11% |
| 30% | 51.10% | 53.87% | 70.65% |

The sharpest reading of that table is not the top row, it is a vertical
slice through it: at 90% solvent recovery — the rate a real distillation
actually achieves — only **25 of the 388** decided reactions are still
decided at *any* enzymatic conversion, and those 25 need conversions of
85.3% (minimum), 93.3% (median), up to 100.0% (maximum) to stay decided.
The other **363 lose their verdict at 90% recovery however well the enzyme
performs.** RHEA:12560, the beta-arbutin calibration case (see
"Calibration" below), is one of the 363: its threshold is 85.87%, below
90%, so its `min_enzymatic_yield` is `None` — no enzyme, however efficient,
saves that verdict at a recovery rate a real plant achieves.

## Comparing across classes: the threshold cannot, a saving can

A recovery threshold is stated against the solvent load of one template. The
shipped glycosylation template charges over 800 kg of solvent per kg of
product; a methylation template built from a different paper will charge
something else. So 86% in one class and 86% in another are not the same
claim, and putting them in one ranked list would be comparing two different
measuring sticks. That matters as soon as there is a second class, which is
the point of building one.

What does survive leaving a class is an absolute quantity: **kg CO₂e saved
per kg of product**, read at the same operating point in every class.
`bounded_verdict` already computes it — `delta_min_kgCO2e` and
`delta_max_kgCO2e` bracket `GWP_chemical - GWP_enzymatic` over the whole box
of asserted intervals — so the screen now evaluates it at
`reference_recovery` (the 90% a plant achieves, not the bench's zero) and
carries it on every row as `advantage_min_kgCO2e` / `advantage_max_kgCO2e`.

It is an interval, so ranking on it cannot be a total order.
`rank_by_advantage` returns a rank *range* per reaction instead: a reaction
is outranked only by reactions whose worst case still beats its best case.
`best_rank` and `worst_rank` are equal only where the intervals genuinely
separate. Sorting by interval midpoint and printing 1, 2, 3 would
manufacture exactly the precision this project refuses to manufacture
anywhere else.

Run against the shipped class, that machinery reports something worth
knowing about the *bounds*, not the chemistry. Every rank range comes back
as 1–388, because four chemical-side materials — acetic anhydride,
potassium carbonate, and two sugar reagents — are deliberately asserted with
no upper ceiling (`high: null`, an honest refusal to invent one). An
unbounded chemical side makes every enzymatic advantage unbounded above, and
nothing can outrank anything. Putting defensible ceilings on those four is
what would make this ranking bite, and the report names them so the gap is
actionable rather than mysterious.

What is available meanwhile is the **guaranteed floor** — the saving that
holds everywhere in the asserted bounds. Ordering on it is exact, because it
is a computed bound rather than an estimate, but it ranks the floor and not
the true saving. At 90% recovery only **25 of the 388** reactions have a
floor above zero at all; for the other 363 the interval straddles zero,
which is an absent verdict rather than a small advantage.

The floor ranking does reproduce the mechanism the screen exists to measure,
which is the check that it is measuring the same thing the threshold was.
The largest guaranteed savings all belong to heavily protected acceptors —
the top ten carry 20 to 34 protectable groups, led by an N-glycan at
+4.15 kg CO₂e per kg — because sparing a chemical route that much masking
and unmasking is precisely what an enzyme's regioselectivity is worth.

## What the shipped class actually found

Screening all 406 reactions in Rhea that consume UDP-glucose or its
diastereomer UDP-galactose (see "Picking the next class" above), against the
Helferich/BF₃ procedure of Cepanec & Litvić (ARKIVOC 2008):

| statistic | recovery threshold |
|---|---|
| minimum | 85.58% |
| median | 86.42% |
| maximum | 91.54% |

These three are the top row of the frontier above — the enzyme held at 100%
conversion — and therefore upper bounds. Read them with "Enzymatic
conversion is the other half of that same asymmetry" in hand: at the 90%
recovery a real plant achieves, 363 of these 388 have no verdict left at
any conversion.

These figures assume a perfect enzyme (`enzymatic_yield=1.0`), so they are
an upper bound on the recovery a plant would actually need — see
"Enzymatic conversion is the other half of that same asymmetry" above for
how the threshold moves once that assumption is relaxed.

**None of the 388 decided reactions survives 99% solvent recovery**, and the
whole distribution sits at or below the 90–95% a real plant achieves. The
honest reading is not "enzymes win 388 times" but: *in this class, as
modelled from this bench procedure, the enzymatic advantage is real but
bounded, and it does not survive industrial solvent recycling.* That is a
falsifiable claim, and a much more useful one.

Not all 406 are glycosylations, and the screen does not pretend they are.
18 are excluded before a verdict is computed: 9 where the acceptor and
product could not be identified from Rhea's equation text, and 9 that
consume a class cofactor for a genuinely different transformation — the
cofactor's own hydrolysis, a sugar-nucleotide exchange, a hexose-1-phosphate
transfer onto a lipid carrier (undecaprenyl phosphate) rather than a
hydroxyl, or oxidation of the sugar-nucleotide itself — none of which
transfers a hexosyl group onto an external acceptor. That exclusion is
enforced by the `expected_mass_delta` check below, not by hand-picking: a
real member of this class adds one anhydrohexosyl unit (162.14 g/mol, times
how many the reaction transfers) to the acceptor, allowing ±1 proton for
ChEBI's own inconsistent charge-state bookkeeping between an acceptor and
its product (a carboxylate acceptor paired with a neutral ester product
shows up as exactly this, in 55 of the 406 — real glycosylations, not
exclusions, once that's accounted for). A reaction that adds a different
mass is not this transformation, whatever else it
shares with one.

The mechanism the screen exists to measure does show up cleanly in the
spread. The threshold rises with the number of protectable groups on the
acceptor — 85.58% where the acceptor has one group or none, 91.54% for a
34-group oligosaccharide — because an enzyme's regioselectivity is worth
more the more sites a chemical route would have to mask and unmask. That is
the enzymatic advantage, quantified, and it is computed from the acceptor's
own structure.

## Calibration

RHEA:12560 — hydroquinone + UDP-α-D-glucose = β-arbutin + UDP + H⁺ — is both
a member of the shipped class and the subject of a fully hand-sourced ledger
in
[`examples/case-studies/beta-arbutin-chemical-vs-enzymatic/`](../examples/case-studies/beta-arbutin-chemical-vs-enzymatic/).
The screen reproduces that case's product mass, acceptor, cofactor charge
and direction, and a test asserts it. A screen that disagreed with the one
case it was derived from would be reporting on its own template rather than
on chemistry, so that test is what gives the other 387 rows any standing.

## Running one

```bash
# 1. Build (or refresh) the reaction database. --offline replays the
#    frozen snapshot in data/raw/rhea/ instead of fetching.
python3 scripts/ingest_rhea.py

# 2. Screen a class.
carbonroute screen \
  --template data/reaction-classes/udp-glucosyltransferase.yaml \
  --bounds   data/reaction-classes/udp-glucosyltransferase.bounds.yaml \
  --assumptions-from examples/case-studies/beta-arbutin-chemical-vs-enzymatic/ledger.yaml \
  -o screen-report.md

# 3. Price a real enzyme instead of a perfect one, and sweep the
#    conversion axis to get the break-even frontier rather than one
#    threshold. --reference-recovery sets the plant the minimum-conversion
#    figures are evaluated against; it defaults to 0.90.
carbonroute screen \
  --template data/reaction-classes/udp-glucosyltransferase.yaml \
  --bounds   data/reaction-classes/udp-glucosyltransferase.bounds.yaml \
  --assumptions-from examples/case-studies/beta-arbutin-chemical-vs-enzymatic/ledger.yaml \
  --enzymatic-yield 0.5 \
  --reference-recovery 0.90 \
  --frontier \
  -o screen-frontier.md
```

Screening needs RDKit — it is what turns Rhea's molar stoichiometry into the
mass basis the rest of the tool uses, and what counts protectable groups
from a structure:

```bash
pip install -e ".[chem]"
```

## Adding a class

1. Pick by **EC-3-level group, not raw cofactor frequency** — see "Picking
   the next class" above for why (CoA and SAM outrank UDP-glucose in raw
   `n_reactions` but are chemically mixed). Group `data/rhea/reactions.tsv`
   by the first three EC fields, find the group's dominant participant, and
   check the group's mass-delta homogeneity before writing anything: pull
   every reaction whose left side contains that participant, identify
   acceptor/product positionally the way `_identify` does, and look at
   how `product_mw - acceptor_mw` clusters. A group where that clusters
   into 2-4 bins that are exact multiples or ±1-proton offsets of one
   signature mass (as all four largest EC-3 groups do) is a real candidate;
   one that scatters is not, whatever its raw reaction count.
   **Check first whether an existing template's cofactor list can simply
   grow** instead of writing a new class: if the dominant participant is a
   diastereomer of a cofactor a template already uses (same molecular
   formula, verified by RDKit, not assumed from the name — UDP-galactose
   next to UDP-glucose is the shipped example), its reactions are a free
   addition to `cofactor_chebi`, no new research required. A participant
   that adds a *different* group (a different formula, therefore a
   different `expected_mass_delta`) needs its own class.
2. Find **one real, fully quantified published chemical procedure** for the
   same transformation. Every `sourced` amount in the template must come
   from a document actually retrieved and read — the same bar
   `data/processes/` holds. This is the step that does not get faster with
   practice; budget for it like any other primary-source research in this
   project.
3. Reduce it to amounts per mole of product, and mark anything you had to
   extend beyond that paper as `generalised`, with the extension stated.
   **State the paper's own overall yield in the template's header while you
   are doing it**, and say which steps it multiplies. Reducing to a
   per-mole-of-product basis silently folds that yield into every amount,
   which is correct — but it also means the chemical side of the comparison
   arrives pre-discounted for real losses while the enzymatic side does not,
   unless someone passes `--enzymatic-yield`. That asymmetry always favours
   the enzyme, it is invisible in the numbers once folded in, and writing
   the yield down is what keeps the next class from reintroducing it.
4. Set `reaction_class.expected_mass_delta`: the mass (g/mol) a genuine
   member of the class adds to the acceptor — +14.03 for a methylation,
   +42.04 for an acetylation, +162.14 for a hexosylation, computed from the
   group's own formula and standard atomic weights, not guessed. This is
   what actually keeps the class honest: `matches()` only checks that the
   cofactor is consumed, and plenty of reactions that share a cofactor are
   not the transformation the template models (the cofactor's own
   hydrolysis, an unrelated condensation, a sugar-nucleotide exchange).
   `screen_reaction` computes the acceptor's and product's real molecular
   weight from Rhea's own structures and excludes anything whose delta
   doesn't match — within one proton's mass either side, to tolerate
   ChEBI recording an acceptor and its product at different, arbitrary
   protonation states, which is bookkeeping, not chemistry.
5. Write bounds for whatever the template consumes that no public factor
   covers — including every cofactor in `cofactor_chebi` (it accepts a
   single ChEBI id or a list of interchangeable ones), which is the entire
   enzymatic side and therefore where the verdict lives.
6. Calibrate: if any reaction in the new class already has a hand-built
   ledger, assert the screen agrees with it. Then look at what
   `expected_mass_delta` actually excluded — every exclusion bucket should
   have a chemical explanation you can state in one sentence, the way the
   UDP-glucosyltransferase class's are documented above. An exclusion you
   can't explain is a bug, not a filtered-out reaction, until you've
   checked which.
