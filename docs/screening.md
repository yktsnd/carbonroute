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

## A declared process, instead of one paper's bench run

`explain_verdict` measured the problem: in all 388 decided reactions of the
shipped class, at least half the delta comes from one number, the same one
every time — the source paper's 150 mL of boiling ethyl acetate per
millimole. Every verdict is, to first order, a statement about one author's
isolation habits.

Choosing a different paper does not fix that. It substitutes a different
author's habits with no principled way to pick between them. What fixes it is
to stop claiming a paper and start declaring a model: reagents at stated
equivalents, solvent from a stated reaction concentration, workup as stated
multiples of that volume. A template may now carry a `process_model` block
doing exactly that, and `--process-model` screens against it.

**This is less precise about any one procedure and more honest about what the
tool is doing**, because the alternative was arbitrariness wearing the costume
of rigour. Every figure it produces is `generalised` by construction — nothing
is read from a paper — and a process chemist who disagrees edits one line
instead of arguing with a citation.

It is also what makes coverage possible. The parameters are
chemistry-independent: concentration, workup volumes, stage yield. A new class
supplies its own reagents and inherits the process. That matters because three
rounds of literature search produced zero new paper-sourced templates, so the
paper-per-class route does not scale and is not going to.

Put side by side on the same 388 reactions, at the same published operating
point, the two chemical models say this:

| | paper template | declared process model |
|---|---|---|
| guaranteed saving, RHEA:12560 | 143.4 | **25.2** kg CO₂e/kg |
| median concentration | 80% | **60%** |
| reactions where ethyl acetate is the top term | 388 / 388 | **232 / 388** |
| reactions with a guaranteed saving | 388 | **388** |

Two things are worth separating there. The enzymatic advantage **shrinks by
about six-fold** — that is the size of the "which paper did you pick" effect,
measured rather than argued about. And the verdict **does not move**: all 388
reactions still have a saving that holds everywhere inside the asserted
bounds. A conclusion that survives having its own dominant assumption
replaced is worth considerably more than one that was never tested that way,
and until the model existed there was no way to test it.

Where the two disagree is instructive. The glycosyl donor agrees to within
15% — that is real chemistry, and both routes have to charge it. The
isolation solvent differs six-fold and the deprotection base differs
six-fold. Those are the terms that were never chemistry in the first place.

## What a verdict is made of, which provenance cannot tell you

This project is scrupulous about where every number came from. Until
`explain_verdict` existed it was entirely silent about which of them the
answer rests on, and those are different questions. A heroically-sourced
figure carrying 0.1% of the delta and a casually-looked-up one carrying 80%
receive identical ceremony from a provenance discipline alone.

That gap has cost this repository three published results. Each was
withdrawn one step later, and each shared a signature: **one term dominated
the delta while its value came from an assumption rather than a
measurement.** The enzyme billed at 100% yield, the co-substrate charged at
theoretical stoichiometry, sucrose capped at an unevidenced 10 kgCO2e/kg. All
three were caught by hand, late, by looking. All three were mechanically
detectable from the start.

`explain_verdict` is that detector. It ranks a delta set by how much of the
verdict each material carries, valuing every material at whichever end of its
interval is *least* favourable to the verdict, and labels each as
**measured** (a factor from a table), **bounded** (an asserted interval) or
**unbounded** (no ceiling asserted).

Run over the shipped class at the published operating point, it says
something the rest of this document had not:

> **In 388 of 388 decided reactions, one single material carries at least
> half the delta — and it is the same material every time.** Median
> concentration 80%; the material is ethyl acetate, the template's 159 kg/mol
> bench isolation.

So every verdict in this class is, to first order, a statement about one
paper's choice of extraction volume. That does not make the verdicts wrong.
It makes them narrower than they read, and it is the strongest argument yet
for replacing a single-paper template with a declared process model.

**The effort here has been close to inversely correlated with leverage**,
which is the sharpest form of the same point. Measuring documentation length
as a proxy for research effort, at the published operating point:

| material | share of delta | characters written about it |
|---|---|---|
| ethyl acetate | 82.7% | 991 |
| sucrose | 2.6% | 2,024 |
| UDP-alpha-D-glucose | 0.6% | 1,082 |

The bounds file described UDP-glucose as "where the screen's verdict actually
lives". It carries 0.6%. That claim has been corrected in place rather than
deleted, because the failure it illustrates is the reason this section
exists: a rule that says *invent no numbers* is necessary and not
sufficient. Its missing complement is *say which number the answer is made
of*.

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

## The fair fight: both routes have an effort dial, and only one was ever turned

Every result above this section sweeps the chemical route's solvent recovery
while the enzymatic route pays fresh cofactor on every cycle. That is not a
comparison of two technologies. It is a comparison of a chemical process
someone optimised against an enzymatic process nobody did, and it flatters
whichever side is being swept.

The asymmetry was easy to miss because the two routes do not have the same
dial. A chemical plant's lever is solvent: distil it back and charge only the
make-up. A biocatalytic plant's lever is not solvent — it already runs in
water — it is the **cofactor**, regenerated in situ so that one charge of it
turns over many times. Recovering 90% of solvent and regenerating 90% of
cofactor are the same amount of engineering ambition pointed at each route's
own dominant burden.

So the selection rule this repository now works to is: **compare a chemical
route that is as serious about solvent as anyone knows how to be against an
enzymatic route that is as serious about cofactor as anyone knows how to be.**
Not a lazy one against an optimised one, in either direction.

`cofactor_recycling` is that second dial, and `fair_fight_frontier` moves
both together.

Recycling is not free and the code refuses to let it look free, but *how* it
is paid for varies by system, so a template declares the measures its process
actually uses rather than the code assuming one shape. Each measure states
how it is charged, and the two shapes behave oppositely as a process is
pushed harder:

| charge | meaning | example |
|---|---|---|
| `per_turnover` | consumed on every catalytic cycle, so recycling never buys it down | sucrose for sucrose synthase; formate or glucose for a dehydrogenase |
| `amortised` | bought once and reused over `reuse_cycles` batches, so its burden divides | an immobilised enzyme preparation and its carrier |

That second shape is the one generalisation matters for. Immobilisation is
how a real process makes an enzyme affordable, and it is not expressible as a
discount on a co-substrate — it is a fixed charge divided by the number of
batches one purchase serves, which is precisely the number immobilisation
exists to raise. A screen may claim no recycling at all unless some declared
measure is marked `enables_recycling`; what wears that mark is the template's
business, because it might be a co-substrate, an electrode or a whole cell.

The shipped class declares one measure: sucrose, `per_turnover`, at the
amount a published cascade actually charges. That is not the 1:1 SuSy
stoichiometry, and the difference matters. Liu, Tegl & Nidetzky
(*Adv. Synth. Catal.* 2021, 363(8), 2157-2169, doi:10.1002/adsc.202001549,
CC BY 4.0) charge 500 mM sucrose and 0.5 mM UDP against a 120 mM acceptor
and reach ~52 g/L of product, which works out at **4.196 mol of sucrose per
mole of product** — 4.2x the theoretical figure this template previously
carried, in the direction that had been flattering the enzyme. Two checks on
that arithmetic come out of the paper's own numbers: 52 g/L at MW 436.41 is
119.2 mM against a 120 mM acceptor, or 99.3% conversion, and 0.5 mM UDP
against 119.2 mM product implies 238 turnovers against the 240 the authors
state.

Two corrections followed, in opposite directions, and the sequence is worth
recording because it shows what each was actually measuring.

Charging the real amount first made the 99% column collapse to no verdict at
all. But that turned out to be a statement about a **bound**, not about
chemistry: sucrose's ceiling was an unevidenced 10 kg CO2e/kg. ADEME Base
Carbone — the same openly licensed database several shipped factors come from
— gives Agribalyse 3.1 figures for white sugar of 0.614 and 0.754 kg CO2e/kg.
Neither is used as a factor, because both carry the perimeter comment
"Livraison : Ambiant (long) - Materiau d'emballage : Papier": they are retail
packaged sugar, not the bulk technical sucrose a bioreactor is fed. That
mismatch is why it stays a bound — and why the higher of them makes a good
*ceiling*, since stripping packaging and retail distribution can only reduce
it. The interval narrows 13x, and the 99% verdict comes back.

Both corrections were right and they cancelled. What holds the result up at
99% is worth knowing, because it is **not solvent**. At that recovery the
chemical side is dominated by reagents that do not recover at all — 8.9 kg of
potassium carbonate per kg of product, the peracetylated donor, sulfuric acid
— while essentially the whole enzymatic burden regenerates. The enzymatic
delta is nearly fully recyclable and the chemical delta floors out at its
stoichiometry. That asymmetry, not the isolation solvent, is what this class
turns on once both routes are pushed hard.

It also reprioritises the open gaps. At Liu's 240 turnovers the cofactor
contributes 0.004-0.87 kg CO2e per kg of product and sucrose 0.53-3.98, while
an enzyme at a realistic 1-10 g per kg of product would contribute 0.001-0.11
against a decision margin of ~95. **The enzyme loading that was blocking an
immobilisation measure turns out to be three orders of magnitude away from
mattering here.**

**It declares no immobilisation measure, and that omission is stated in the
template rather than hidden.** Two of the three figures such a measure needs
now exist. `reuse_cycles`: Yue et al. (*ACS Appl. Mater. Interfaces* 2024,
16(45), 61725-61738, doi:10.1021/acsami.4c14661) co-immobilise UGT and SuSy
on a NiCo metal-organic framework and report 10 cycles at 68.97% residual
activity, loading 115.9 mg of enzyme per gram of support; Trobo-Maseda et al.
(2020, doi:10.1016/j.ijbiomac.2020.04.120) independently report up to 10
batch cycles. Enzyme GWP: bounded in the bounds file at 1 to 10.6 kg CO2e per
kg, spanning Nielsen et al. 2007 (1-10 per kg *final product*) and Gilpin &
Andrae 2017 (7.9-10.6 per kg *full broth*) — two different functional units,
which is precisely why it is a bound and not a factor.

The one still missing is the bridge: enzyme mass per mole of **product**. Yue
gives enzyme per gram of carrier and Liu gives a product titre, but neither
states a loading on a per-product basis and it cannot be derived from what
they do state. Without it a per-kg-enzyme GWP cannot become a per-kg-product
charge, so no measure is written and the enzyme stays absent from the diff —
understating the enzymatic route, in the same direction as every other gap
here, and left as a gap rather than filled.

Run that way, the enzymatic route stays ahead on all 388 reactions at every
effort from 0% to 99%. **That result is not yet worth much, and the report
says so on the same page it prints it.** The template's largest term is
159 kg of ethyl acetate per mole of product — a bench isolation of 150 mL per
millimole — and it dominates the chemical side at every effort. Recovery only
ever divides that number; it cannot un-choose it.

Which is the real lesson, and it is a limit on the method rather than a
finding about enzymes: **solvent recovery and solvent avoidance are different
levers.** A chemical process that were itself serious about solvent would not
recover 99% of a bench isolation, it would replace the isolation —
crystallise, use an antisolvent, run the extraction continuously. The fair
fight as currently instrumented puts a genuinely solvent-lean enzymatic route
against a chemical route that is merely tidying up after a wasteful one. The
table is therefore an upper bound on the enzymatic advantage, and the class
needs a template built from a solvent-lean published procedure before it is
anything more.

## The confound that decides whether a cross-class ranking means anything

Ranking two classes against each other compares two *templates*, and a
template is one paper someone chose. That choice is a free parameter, and
searching for the second class's source made it obvious how large a one.

The shipped glycosylation template comes from a classical bench procedure
that discards over 800 kg of solvent per kg of product. Searching for an
acetylation counterpart turns up procedures spanning the full range: the
same classical Ac₂O-in-pyridine at 8-10 mL of pyridine per small-scale run,
and also deliberately green ones — acetylation in water with sodium
bicarbonate, or catalysed solvent-free. Both are real, published, fully
quantified chemistry for the same transformation.

Pair the 2008 classical glycosylation with a 2013 green acetylation and the
ranking will report that acetylation's enzymatic advantage is smaller. That
would be true of those two papers and false of the chemistry: what the
number would actually be measuring is how hard each set of authors tried to
cut solvent. A cross-class saving is only comparable if the templates are
comparable, and "same operating point" — the thing `reference_recovery`
fixes — does not give that on its own.

So a second class needs a stated selection rule before it needs a paper.
The defensible one is to hold template vintage and intent constant: take the
procedure a synthetic chemist would have run for that transformation without
setting out to minimise solvent, which is what the glycosylation template
is, and record the alternative green procedure separately as a scenario
rather than folding it into the class. The rule has to be written down and
applied the same way in every class, because the ranking is only as
comparable as the least principled template choice in it.

**This is what `process_model` actually resolves, not just what it was built
for.** A declared process applies the identical rule — the same reaction
concentration, the same isolation-volume multiplier, the same per-stage
yield — to every class by construction, because those parameters are
chemistry-independent. There is no "which paper did the second class use"
question to answer, because there is no paper. `sam-methyltransferase.yaml`
is the second class, screened only against its `process_model` for exactly
this reason: pairing it with the glycosylation class's paper-sourced
template would reintroduce the confound this section describes, and pairing
it with the glycosylation class's *own* `process_model` run does not.

That still leaves a real limit. The two classes' reagents (methyl iodide and
acetic anhydride, say) are not modelled on the same evidential footing as
each other — each is a declared equivalents figure, not derived from a
shared physical constant the way the isolation-volume rule is — so a
cross-class ranking built from them inherits whatever spread exists between
"1.1 equivalents of acetic anhydride" and "1.5 equivalents of methyl
iodide" as a genuine source of incomparability, smaller than the one this
section opened with but not zero.

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

## The second class: SAM-dependent methylation

`data/reaction-classes/sam-methyltransferase.yaml` covers SAM-dependent
O-, N- and S-methylation — EC 2.1.1, the second-largest EC-3 group in Rhea.
It has no `chemical_counterpart.materials` at all; it ships with only a
`process_model` and must be run with `--process-model`. That is not a
placeholder — see "A declared process, instead of one paper's bench run"
above for why.

**Matching needed two filters, not one, and the second is worth naming
because it repeats the acetyl-CoA/Claisen lesson in a new shape.** Of Rhea's
18,558 reactions, 946 consume SAM at all; restricting to EC 2.1.1 and a
single resolvable acceptor narrows that to 449. Checking `expected_mass_delta`
(14.027 g/mol per methyl, CH₃ replacing H, times however many the reaction's
own SAM stoichiometry says it transfers) excludes 6 more. What is left still
contains 74 reactions that add *exactly* the right mass without being this
class's chemistry: C-methyltransferases in steroid and terpene biosynthesis
(cycloartenol → cyclolaudenol), tetrapyrrole biosynthesis (the precorrin
series), and — notably — cytosine C5 methylation in DNA. All are genuine
methylations; none is O-, N- or S-alkylation, because the new methyl lands on
a ring or alkene carbon rather than a heteroatom, which a methyl halide and a
mild base cannot plausibly reach. `transferred_bond_smarts` (`[CH3][#7,#8,#16]`,
verified against real Rhea pairs: `trans-resveratrol → pterostilbene` and
`glycine → N,N-dimethylglycine` both show a bond-count delta equal to their
SAM stoichiometry; `cycloartenol → cyclolaudenol` shows zero) is what tells
them apart. Without it those 74 would have been silently mis-templated as
alkylations they are not.

| statistic | value |
|---|---|
| SAM-consuming reactions in Rhea | 946 |
| restricted to EC 2.1.1, single acceptor | 449 (`matched`) |
| excluded — mass delta does not fit any multiple of 14.027 | 6 |
| excluded — could not identify an acceptor/product pair | 18 |
| excluded — right mass, wrong bond (C-methylation) | 74 |
| **decided** | **351** |

Every excluded reaction was checked by hand against its equation text before
this table was written, the same discipline the glycosylation class's
exclusion buckets follow.

## The third class: NAD(P)+-dependent oxidation, and an honest non-result

`data/reaction-classes/nad-oxidoreductase.yaml` covers NAD(P)+-dependent
oxidation of a CH-OH group — EC 1.1.1, the *largest* EC-3 group in Rhea.
Matching on the *oxidised* cofactor forms specifically (NAD+, NADP+, not
NADH/NADPH) is what fixes the direction: those reactant ChEBI ids only
appear on reactions written as oxidations, so `expected_mass_delta` can be a
single signed number (−2.016 g/mol, H₂ lost) rather than needing to handle
both signs.

**515 reactions match; 492 resolve to a single acceptor; 466 of those
(94.7%) land within one proton of a clean multiple of −2.016.** The other 26
cluster tightly at −45.02 — oxidative *de*carboxylation (malate
dehydrogenase, isocitrate dehydrogenase, 6-phosphogluconate dehydrogenase
and relatives: −2.016 for the hydride loss plus −43.99 for the CO₂ that
leaves with it), a genuinely different transformation a stoichiometric
oxidant alone does not perform, and correctly excluded rather than folded
in as noise.

**This class ships no `transferred_bond_smarts`, and the reason is worth
recording as a caution about the bond-check mechanism itself.** The natural
structural signature of an oxidation is a new C=O appearing
(`[CX3]=[OX1]`), and it works cleanly on open-chain acceptors — but it fails
on a real and common case in this class: ChEBI draws reducing sugars in
their *cyclic hemiketal* form, so `D-mannitol + NAD+ = D-fructose + NADH` shows
zero carbonyl matches on either side of the equation, because the "new"
ketone is masked as a ring C–OH. Applying the check as written would have
silently excluded dozens of genuine hexitol/pentitol dehydrogenase
reactions for a drawing convention, not a chemical reason — precisely the
kind of mistake this project's own methodology exists to catch, not commit.
The mass-delta check alone is sufficient here (94.7% purity, one cleanly
identified confound), so a bond check that would do more harm than good is
left out, and that decision is itself the finding worth keeping: **a
structural check is a tool for a specific failure mode, not a reflex to
apply everywhere.**

**The verdict, honestly: all 515 matched reactions currently screen as
indeterminate.** Not a bug — the same wide, unevidenced `[0.5, 100]`
cofactor ceiling the other two classes carry for their own cofactors, paired
here with a *process model* that is genuinely small (a mostly catalytic
TEMPO/NaOCl oxidation has nothing like glycosylation's paper-scale solvent
burden or methylation's stoichiometric alkylating agent). `explain_verdict`
on any one reaction shows why directly: at the cofactor's cheapest
plausible value the enzymatic route can still cost far more than this
process model's chemical route, so the interval straddles zero for every
member. Padding the process model's reagent equivalents to force a
decision would be exactly the thumb-on-the-scale this project refuses
elsewhere. The honest options are the ones already used elsewhere in this
repository: narrow the cofactor bound with real evidence (the way sucrose's
ceiling was narrowed from an unevidenced 10 to ADEME/Agribalyse's 0.754), or
strengthen the process model with a stage this one omits. Neither has been
done yet, so the class ships as matched-but-undecided rather than with a
number invented to make it look otherwise.

**Coverage across all three classes: 1,370 of 18,558 Rhea reactions matched
(7.4%), 739 decided (4.0%).** The gap between those two figures is now
itself informative — it is exactly this class's 515 reactions, all
indeterminate.

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
