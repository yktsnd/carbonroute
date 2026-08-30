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
arithmetic evaluation — the whole 478-reaction UDP-hexosyltransferase class
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

Running the frontier against the shipped class (478 matched, 451 decided at
every point):

| enzymatic conversion | min threshold | median | max |
|---|---|---|---|
| 100% | 84.56% | 86.42% | 91.54% |
| 90% | 82.80% | 84.87% | 90.54% |
| 80% | 80.61% | 82.94% | 89.30% |
| 70% | 77.79% | 80.44% | 87.70% |
| 60% | 74.02% | 77.12% | 85.57% |
| 50% | 68.76% | 72.47% | 82.59% |
| 40% | 60.86% | 65.50% | 78.11% |
| 30% | 47.69% | 53.87% | 70.65% |

The sharpest reading of that table is not the top row, it is a vertical
slice through it: at 90% solvent recovery — the rate a real distillation
actually achieves — only **25 of the 451** decided reactions are still
decided at *any* enzymatic conversion, and those 25 need conversions of
85.3% (minimum), 93.3% (median), up to 100.0% (maximum) to stay decided.
The other **426 lose their verdict at 90% recovery however well the enzyme
performs.** RHEA:12560, the beta-arbutin calibration case (see
"Calibration" below), is one of the 426: its threshold is 85.87%, below
90%, so its `min_enzymatic_yield` is `None` — no enzyme, however efficient,
saves that verdict at a recovery rate a real plant achieves.

## A declared process, instead of one paper's bench run

`explain_verdict` measured the problem: in all 451 decided reactions of the
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

Put side by side on the same 451 reactions, at the same published operating
point, the two chemical models say this:

| | paper template | declared process model |
|---|---|---|
| guaranteed saving, RHEA:12560 | 143.4 | **25.2** kg CO₂e/kg |
| median concentration | 80% | **60%** |
| reactions where ethyl acetate is the top term | 451 / 451 | **266 / 451** |
| reactions with a guaranteed saving | 451 | **451** |

Two things are worth separating there. The enzymatic advantage **shrinks by
about six-fold** — that is the size of the "which paper did you pick" effect,
measured rather than argued about. And the verdict **does not move**: all 451
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

> **In 451 of 451 decided reactions, one single material carries at least
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
as 1–451, because four chemical-side materials — acetic anhydride,
potassium carbonate, and two sugar reagents — are deliberately asserted with
no upper ceiling (`high: null`, an honest refusal to invent one). An
unbounded chemical side makes every enzymatic advantage unbounded above, and
nothing can outrank anything. Putting defensible ceilings on those four is
what would make this ranking bite, and the report names them so the gap is
actionable rather than mysterious.

What is available meanwhile is the **guaranteed floor** — the saving that
holds everywhere in the asserted bounds. Ordering on it is exact, because it
is a computed bound rather than an estimate, but it ranks the floor and not
the true saving. At 90% recovery only **25 of the 451** reactions have a
floor above zero at all; for the other 426 the interval straddles zero,
which is an absent verdict rather than a small advantage.

The floor ranking does reproduce the mechanism the screen exists to measure,
which is the check that it is measuring the same thing the threshold was.
The largest guaranteed savings all belong to heavily protected acceptors —
the top ten carry 27 to 34 protectable groups, led by an N-glycan at
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

Run that way, the enzymatic route stays ahead on all 451 reactions at every
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

Screening all 478 reactions in Rhea that consume UDP-glucose, UDP-galactose,
or one of six sibling hexose-nucleotide donors (GDP-mannose, ADP-glucose,
GDP-glucose, UDP-galactofuranose, dTDP-glucose, CDP-glucose — see "Picking
the next class" above), against the Helferich/BF₃ procedure of Cepanec &
Litvić (ARKIVOC 2008):

| statistic | recovery threshold |
|---|---|
| minimum | 84.56% |
| median | 86.42% |
| maximum | 91.54% |

These three are the top row of the frontier above — the enzyme held at 100%
conversion — and therefore upper bounds. Read them with "Enzymatic
conversion is the other half of that same asymmetry" in hand: at the 90%
recovery a real plant achieves, 426 of these 451 have no verdict left at
any conversion.

These figures assume a perfect enzyme (`enzymatic_yield=1.0`), so they are
an upper bound on the recovery a plant would actually need — see
"Enzymatic conversion is the other half of that same asymmetry" above for
how the threshold moves once that assumption is relaxed.

**None of the 451 decided reactions survives 99% solvent recovery**, and the
whole distribution sits at or below the 90–95% a real plant achieves. The
honest reading is not "enzymes win 451 times" but: *in this class, as
modelled from this bench procedure, the enzymatic advantage is real but
bounded, and it does not survive industrial solvent recycling.* That is a
falsifiable claim, and a much more useful one.

Not all 478 are glycosylations, and the screen does not pretend they are.
27 are excluded before a verdict is computed: 13 where the acceptor and
product could not be identified from Rhea's equation text, and 14 that
consume a class cofactor for a genuinely different transformation — the
cofactor's own hydrolysis, a sugar-nucleotide exchange, a hexose-1-phosphate
transfer onto a lipid carrier (undecaprenyl phosphate) rather than a
hydroxyl, oxidation of the sugar-nucleotide itself, or (among the six
sibling donors) chain elongation and isomerisation of the same kind — none
of which transfers a hexosyl group onto an external acceptor. That
exclusion is enforced by the `expected_mass_delta` check below, not by
hand-picking: a real member of this class adds one anhydrohexosyl unit
(162.14 g/mol, times how many the reaction transfers) to the acceptor,
allowing ±1 proton for ChEBI's own inconsistent charge-state bookkeeping
between an acceptor and its product (a carboxylate acceptor paired with a
neutral ester product shows up as exactly this, in 57 of the 478 — real
glycosylations, not exclusions, once that's accounted for). A reaction that
adds a different mass is not this transformation, whatever else it
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

**Coverage across all three classes: 1,442 of 18,558 Rhea reactions matched
(7.8%), 802 decided (4.3%).** The gap between those two figures is now
itself informative — it is exactly this class's 515 reactions, all
indeterminate.

## The fourth class: ATP-dependent phosphorylation, and a charge-state fix

`data/reaction-classes/atp-kinase.yaml` covers ATP-dependent transfer of the
γ-phosphate onto an acceptor hydroxyl, releasing ADP — EC 2.7.1, matched on
ATP specifically (not ADP or AMP, which mark different chemistry).

**The textbook mass delta is wrong for this class, and finding out why is
the interesting part.** A phosphate monoester, R-OH → R-O-PO₃H₂, adds HPO₃
net: 79.980 g/mol in vacuo. Measured against real Rhea reactions, the
observed delta clusters at 77.963 — short by almost exactly two protons.
The reason is not a different transformation but ChEBI's own charge-state
convention: it records the phosphorylated product as the **dianion**,
R-O-PO₃²⁻, not the neutral diacid, so the structure carries two fewer
explicit hydrogens than the textbook formula predicts. Verified directly
against RHEA:10224 (pyridoxal → pyridoxal 5′-phosphate, observed delta
77.963 exactly). This is the same phenomenon the glycosylation class
documents for a minority of its members (a carboxylate acceptor paired with
a neutral ester product, short by one proton) — here it is the *dominant*
convention rather than an exception, so `expected_mass_delta` is set to
what ChEBI actually records rather than the in-vacuo number.

| outcome | reactions |
|---|---:|
| matched (ATP + EC 2.7.1) | 209 |
| excluded — could not identify an acceptor/product pair | 4 |
| excluded — right transfer count, wrong mass (donor/acceptor pairing collides) | 3 |
| **decided** | **202** |

The 3 mass-delta exclusions are not a different transformation the way SAM's
C-methylations or NAD's oxidative decarboxylations are: RHEA:12260 (NADH
kinase), RHEA:18245 (dephospho-CoA kinase), and RHEA:18629 (NAD⁺ kinase) are
genuine single-phosphate transfers, but their donor and acceptor are both
large, similarly-sized cofactor molecules, and the simple by-elimination
pairing this project uses to identify "the acceptor" and "the product"
locks onto the wrong pair for them. The mass-delta check correctly refuses
to decide them rather than guessing — an honest limitation of the pairing
heuristic, not of the chemistry.

`transferred_bond_smarts: "[#15]"` (a new phosphorus atom) checks the class
anyway, on a signature that is simple and robust because acceptors in this
class carry zero phosphorus to start with. It excludes none of the 202
mass-delta-clean reactions — the mass-delta check alone already separates
the class, and the bond check confirms rather than does the discriminating
work here, unlike SAM's class where it is load-bearing.

**Unlike the NAD(P)+ class, every one of this class's 202 decided reactions
reaches a decisive verdict, and every one favours the enzyme.** The process
model (POCl₃/pyridine phosphorylation, pyridine doing double duty as both
solvent and base) is stoichiometric and comparatively bulky, the same shape
of chemical counterpart glycosylation and methylation have — not the small,
mostly-catalytic route NAD-oxidoreductase's class carries. Even at ATP's
most expensive assumed value within its unevidenced `[0.5, 100]` ceiling,
the chemical route's reagent burden is enough to keep the sign fixed over
the whole box of asserted bounds.

**Coverage across all four classes: 1,651 of 18,558 Rhea reactions matched
(8.9%), 1,004 decided (5.4%).**

## The fifth class: DMAPP-dependent prenylation, and two more confounds correctly excluded

`data/reaction-classes/dmapp-prenyltransferase.yaml` covers transfer of the
dimethylallyl group from DMAPP (dimethylallyl diphosphate, the smallest and
most common of Rhea's four allylic-diphosphate prenyl donors) onto a
nucleophilic acceptor, releasing diphosphate — EC 2.5.1. The other three
donors (GPP, FPP, GGPP, transferring two, three and four isoprene units
respectively) are not covered by this class: each adds a different mass, so
covering all four under one template would need a per-donor expected delta
this project's schema does not support, and DMAPP alone is the largest
single group among them.

Net mass added is the isoprenyl group, C₅H₈, 68.119 g/mol — verified
directly against RHEA:10852 (leachianone G → sophoraflavanone G: product
424.493 g/mol minus acceptor 356.374 g/mol = 68.119 exactly). Unlike the
ATP-kinase class, no charge-state offset applies here: DMAPP and its
diphosphate leaving group are drawn in the *same* charge state (both
trianions) in this pair, so the textbook and observed values agree.

| outcome | reactions |
|---|---:|
| matched (DMAPP + EC 2.5.1) | 47 |
| excluded — could not identify an acceptor/product pair | 6 |
| excluded — right transfer count, wrong mass (chain elongation) | 3 |
| **decided** | **38** |

Two genuinely different sub-chemistries share the DMAPP cofactor with real
prenylation, and both are correctly excluded rather than mis-decided. **Chain
elongation** (DMAPP condensing head-to-tail with two, three or five
isopentenyl diphosphate equivalents to build a longer allylic diphosphate —
RHEA:27810, RHEA:55520, RHEA:77975) leaves mass deltas of 136.24, 204.36 and
340.60 g/mol, which cluster tightly at exact multiples of 68.12 rather than
one unit — the same real chemistry (successive isoprene-unit addition)
confirmed rather than noise, and correctly excluded because this class
models DMAPP transferring onto a foreign nucleophile, not IPP chain
elongation. **DMAPP homodimerisation** (chrysanthemyl and lavandulyl
diphosphate synthase — RHEA:14009, RHEA:21676) consumes two DMAPP and no
foreign acceptor at all, so no acceptor/product pair resolves; correctly
excluded as "could not identify" rather than forced into a pairing that
does not exist.

No `transferred_bond_smarts` is declared, for the same reason the
NAD(P)+-oxidoreductase class carries none: many acceptors in this class are
natural products that already carry an unrelated isoprenyl-derived alkene
from the same biosynthetic family, so "one more C=C" is not a clean
discriminator. The mass-delta check alone is the whole class-purity test
here, and — like the ATP-kinase class — every one of the 38 decided
reactions reaches a decisive verdict favouring the enzyme: the process
model's stoichiometric prenyl bromide loading (the same Williamson-type
alkylation shape the SAM class uses, with the alkylating agent swapped)
keeps the sign fixed even at DMAPP's most expensive assumed value within its
wide, unevidenced `[0.5, 100]` cofactor ceiling.

**Coverage across all five classes: 1,698 of 18,558 Rhea reactions matched
(9.2%), 1,041 decided (5.6%).**

## The sixth class: acetyl-CoA-dependent acetylation, and a second charge-state unification

`data/reaction-classes/acetyl-coa-acyltransferase.yaml` covers transfer of
the acetyl group from acetyl-CoA onto a nucleophilic acceptor (an alcohol
or an amine), releasing CoA — EC 2.3.1. That EC group is a real grab-bag:
it also covers acyl-CoA-to-acyl-CoA Claisen condensations (ketosynthase-type
chemistry building a new C–C bond, not simple acyl transfer to a small
acceptor), so this class leans on the mass-delta check to separate the two,
the same way the NAD(P)+ class separates 2H-loss oxidation from oxidative
decarboxylation.

**The two halves of "simple acetylation" turn out to be one mass delta, not
two, once a charge-state artifact is accounted for.** O-acetylation
(R-OH → R-O-COCH₃) and N-acetylation (R-NH₂ → R-NH-COCH₃) are chemically the
same net addition — C₂H₂O, 42.037 g/mol — and the O-acetylated members
cluster there exactly (RHEA:10456, D-maltose → 1-O-acetylmaltose: 384.334 −
342.297 = 42.037). The N-acetylated members initially looked like a
*different* mass, 41.03, short by almost exactly one proton — the same kind
of ChEBI charge-state convention the ATP-kinase class found, on the other
side of the reaction this time: ChEBI draws amino-acid-type acceptors as
the zwitterion (RHEA:10060's D-tryptophan is one proton heavier than the
neutral form), while the acetylated product is drawn with a neutral amide
nitrogen — so the *acceptor* carries the extra proton here, not the
product. `expected_mass_delta` is set to the true value, 42.037, with
`mass_delta_tolerance` widened to 1.1 specifically to catch this — unifying
both halves as one real chemistry rather than silently splitting it in two
for a drawing convention.

| outcome | reactions |
|---|---:|
| matched (acetyl-CoA + EC 2.3.1) | 138 |
| excluded — could not identify an acceptor/product pair | 10 |
| excluded — right transfer count, wrong mass (Claisen condensation) | 4 |
| **resolved within tolerance** | **124** |

The 4 mass-delta exclusions (RHEA:31555, RHEA:47044, RHEA:79655,
RHEA:79651) cluster at +704 or −57 g/mol — Claisen-type condensations
building a new C–C bond to another CoA thioester, a genuinely different
transformation this class does not model — and are correctly excluded
rather than folded in as noise. No `transferred_bond_smarts` is declared:
the mass-delta check alone already separates real acetylation from the
Claisen confound by three orders of magnitude in delta.

**The verdict, honestly: all 124 resolved reactions currently screen as
indeterminate — a second honest non-result, for a related reason to the
NAD(P)+ class's.** This class's acceptors are typically small (median
product 221 g/mol), so acetyl-CoA's cost per kilogram of product is
comparatively large even at the cofactor's cheapest plausible value within
its wide, unevidenced `[0.5, 100]` ceiling — enough to erase the process
model's modest acetic-anhydride/pyridine burden for every member. The
honest options are the same ones already used for the NAD(P)+ class:
narrow the cofactor bound with real evidence, or strengthen the process
model with a stage this one omits. Neither has been done yet.

**Coverage across all six classes: 1,836 of 18,558 Rhea reactions matched
(9.9%), 1,041 decided (5.6%).** The gap between those two figures now spans
two classes' worth of matched-but-indeterminate reactions (515 + 124 = 639)
rather than one.

## The seventh class: UDP-glucuronate-dependent glucuronidation, and a third charge-state split

`data/reaction-classes/udp-glucuronosyltransferase.yaml` covers transfer of
a glucuronosyl unit from UDP-glucuronate onto an acceptor hydroxyl,
releasing UDP — the UGT (UDP-glucuronosyltransferase) family, the same
real-world drug-metabolism chemistry that conjugates phenols, alcohols and
carboxylic acids in the liver. Matching is on mass delta rather than EC
prefix: the donor's chemistry alone is specific enough to separate real
glucuronosylation from this cofactor's other reactions.

**A third charge-state split, the same kind of finding as the ATP-kinase
and acetyl-CoA classes.** Real glucuronosylation reactions cluster at two
mass deltas exactly one proton apart, not one — verified directly against
RHEA:10568 (luteolin → luteolin 7-O-β-D-glucuronide: 460.347 − 285.231 =
175.116) and RHEA:28314 (baicalein → baicalin: 445.356 − 269.232 =
176.124). Both are real, structurally confirmed glucuronosylations; the
difference is which of the acceptor's *other* hydroxyls ChEBI happens to
draw protonated versus anionic in that particular entry, not a different
transformation. `expected_mass_delta` is set to the midpoint, 175.62, with
`mass_delta_tolerance` widened to 1.0 to cover both real clusters without
also catching this cofactor's genuinely different chemistry, which sits
far outside that window.

| outcome | reactions |
|---|---:|
| matched (UDP-glucuronate) | 102 |
| excluded — could not identify an acceptor/product pair | 3 |
| excluded — right transfer count, wrong mass (4 other transformations) | 4 |
| **decided** | **95** |

Three reactions have no separate acceptor at all: RHEA:11404
(UDP-glucuronate 4-epimerase, a pure isomerisation to UDP-galacturonate)
and RHEA:23916/RHEA:70523 (UDP-glucuronate decarboxylase to UDP-xylose or
UDP-apiose, releasing CO₂) — the latter two only resolve to "could not
identify" once a proton on the left of their equations is correctly
excluded from the acceptor search the same way one on the right already
was (see "Three more siblings" below); before that fix they were
mis-bucketed as a wrong mass rather than a missing acceptor, though
correctly excluded either way. The 4 remaining mass-delta exclusions are
genuinely different UDP-glucuronate chemistry, not glucuronosylation gone
wrong: hyaluronan/proteoglycan chain elongation (2, written with Rhea's
"(n)"/"(n+1)" polymer notation), a further NAD⁺-dependent oxidative
decarboxylation (1), and hydrolysis to glucuronate 1-phosphate rather
than transfer to a foreign acceptor (1) — all correctly excluded rather
than folded in as noise.

No `transferred_bond_smarts` is declared: the mass-delta check alone
already separates real glucuronosylation from this cofactor's other
chemistry by at least two orders of magnitude in delta. Like the
ATP-kinase and DMAPP-prenyltransferase classes, every one of the 95
decided reactions reaches a decisive verdict favouring the enzyme: the
process model (a Koenigs-Knorr coupling with a pre-formed glycosyl bromide
donor and a silver promoter, then saponification) is bulky enough to keep
the sign fixed even at UDP-glucuronate's most expensive assumed value
within its wide, unevidenced `[0.5, 100]` cofactor ceiling.

**Coverage across all seven classes: 1,938 of 18,558 Rhea reactions
matched (10.4%), 1,136 decided (6.1%).**

## Three more siblings: GPP, FPP and GGPP prenylation

DMAPP is one of four allylic-diphosphate prenyl donors in Rhea; the other
three transfer two, three and four isoprene units respectively rather than
one, so each needs its own `expected_mass_delta` and its own class:
`data/reaction-classes/gpp-prenyltransferase.yaml`,
`fpp-prenyltransferase.yaml` and `ggpp-prenyltransferase.yaml`. Same
transformation as DMAPP (a nucleophile displaces diphosphate at C1 of the
allylic system), same process-model shape (a prenyl bromide analogue —
geranyl, farnesyl or geranylgeranyl bromide, each CAS verified by web
search rather than memory given how obscure the longer-chain reagents
are — with a mild base), no `transferred_bond_smarts` for the same reason
DMAPP carries none.

**Building them surfaced a real, general bug in `_identify`, the function
every class uses to pick out the acceptor and product.** It already
excluded a bare proton from the right-hand side of an equation ("H(+)" is
never the product), but not from the left — so any reaction needing a
proton as a genuine co-reactant (2,673 of Rhea's 18,558, 14.4%, most
oxidoreductases and several prenylations among them) silently failed
identification, or worse, occasionally let a lone proton stand in as a
fake "acceptor". Fixed symmetrically, and checked to be purely additive
before landing — it can only shrink `others_left`'s count, never grow it,
so no reaction that matched before can stop matching — verified empirically
against all ten already-shipped classes: seven were unaffected, DMAPP
gained one decided reaction (37 → 38, RHEA:79231), UDP-glucuronate kept
its 95 decided but reclassified two reactions from a wrong mass to the
honester "could not identify" (they were only failing the mass check
because a lone proton had been mistaken for their acceptor), and GPP and
GGPP each gained one, below.

| class | matched | decided | decided as % of matched |
|---|---:|---:|---:|
| GPP (two units, 136.24 g/mol) | 11 | 10 | 90.9% |
| FPP (three units, 204.36 g/mol) | 13 | 2 | 15.4% |
| GGPP (four units, 272.48 g/mol) | 9 | 4 | 44.4% |

**FPP is the honest finding here, and it runs the opposite direction from
DMAPP's.** DMAPP decides 38 of 47 matched reactions (80.9%) because most of
its real EC 2.5.1 chemistry really is transfer onto a foreign nucleophile.
FPP decides only 2 of 13 (15.4%) because most of *its* real EC 2.5.1
chemistry is something else entirely: 6 reactions are chain elongation
(FPP condensing with 3–10 more isopentenyl diphosphate equivalents to
build a longer polyprenyl diphosphate — RHEA:27551/27559/27794/27798/
27802/53008, mass deltas at exact multiples of 68.12, the same confound
DMAPP's class documents), and 3 more are FPP **homodimerisation** — two
FPP molecules condensing head-to-head with no foreign acceptor at all
(RHEA:22672 → presqualene diphosphate, RHEA:31547 → diapophytoene,
RHEA:32295/32299 → squalene, all genuine terpenoid biosynthesis, none of
it this class's transformation). GGPP shows the same two confounds in
smaller numbers, plus one prenylation-with-decarboxylation
(RHEA:38003) that loses CO₂ alongside diphosphate and one reaction
(RHEA:58176) that consumes a second cofactor (NADPH) alongside GGPP,
both adding a different net mass. Every excluded reaction is correctly
separated by the mass-delta check rather than folded in as noise — a
smaller class is not the same thing as a wrong one.

Every decided reaction across all three classes is decisive and favours
the enzyme, the same shape DMAPP, ATP-kinase and the UGT class show.

**Coverage across all ten classes: 1,971 of 18,558 Rhea reactions matched
(10.6%), 1,153 decided (6.2%).**

## The eleventh class: O2/NAD(P)H-dependent monooxygenation, and a first two-cofactor class

`data/reaction-classes/o2-monooxygenase.yaml` covers EC 1.14.13 —
flavin/pyridine-nucleotide monooxygenases: aromatic and aliphatic
hydroxylases, Baeyer-Villiger oxidations, sulfoxidations, N-oxidations.
These enzymes insert one atom of O2 into the product; the other leaves as
water, reduced by NAD(P)H, which the enzyme oxidises in the same step —
mechanistically a genuine second cofactor, not a byproduct. Every earlier
class in this project consumes exactly one cofactor identity per
reaction, so nothing in the architecture could express this until now.

**This is the class that motivated `unpriced_co_cofactor_chebi`.**
`_identify`'s acceptor search now also excludes NAD(P)H
(`CHEBI:57945`/`CHEBI:57783`), the same way it excludes the priced
cofactor and a bare proton — but NAD(P)H is never charged as a material.
That is a stated, deliberate gap, not an invented zero: this class's
enzymatic side is genuinely understated by whatever NAD(P)H's own
regeneration costs, in the same direction every other unpriced
assumption in this project understates it, and `render_screen` prints a
standing warning on every report against this class saying so.

**A fourth charge-state split**, independently discovered from the
ATP-kinase, acetyl-CoA and UDP-glucuronate ones. A genuine member adds
one oxygen atom, 15.999 g/mol — verified directly against RHEA:11440
(2,3,5,6-tetrachlorophenol → 2,3,5,6-tetrachlorohydroquinone). But the
observed delta is 14.991, short by almost exactly one proton: ChEBI
draws the acceptor as a phenol**ate** (one hydroxyl already deprotonated)
and the product as a bis-phenolate (both hydroxyls deprotonated,
including the newly-installed one), so the new OH is drawn without its
proton. `expected_mass_delta` is set to the true value, 15.999, with
`mass_delta_tolerance` widened to 1.1 to unify both clusters.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.14.13) | 198 |
| excluded — right transfer count, wrong mass (64 other transformations) | 64 |
| **decided** | **134** |

Notably, **zero** of the 198 fail to resolve to a single acceptor/product
pair at all — this class's reactions are consistently written as
`acceptor + O2 + NAD(P)H = product + NAD(P)+ + H2O`, exactly the shape
`unpriced_co_cofactor_chebi` exists to handle. Of the 134 decided, the
majority cluster at the textbook 16.0 g/mol (RHEA:11420, senecionine
N-oxidation, among them); the phenolate-shifted minority clusters at
14.99. The 64 mass-delta exclusions split into several genuinely
different EC 1.14.13 sub-chemistries the mass-delta check correctly
keeps out: oxidative **decarboxylation** (RHEA:21628 and others,
clustering near −27 to −44 — the same discipline the
NAD(P)+-oxidoreductase class's own decarboxylation confound already
established) and oxidative **O-demethylation** (18 reactions clustering
at −14.03, `Ar-O-CH3 + O2 + NAD(P)H → Ar-OH + HCHO + NAD(P)+ + H2O` — the
mirror image of the SAM class's own +14.03 methylation, correctly not
mistaken for a hydroxylation).

Every one of the 134 decided reactions reaches a decisive verdict
favouring the enzyme, even with NAD(P)H's real cost left entirely
unpriced: an mCPBA-based process model (the textbook stoichiometric
chemical counterpart for this whole transformation family) is bulky
enough on its own to keep the sign fixed.

**Coverage across all eleven classes: 2,169 of 18,558 Rhea reactions
matched (11.7%), 1,287 decided (6.9%).**

## The twelfth class: cytochrome P450 monooxygenation

`data/reaction-classes/p450-monooxygenase.yaml` covers EC 1.14.14 —
cytochrome P450s and related heme-thiolate monooxygenases, Rhea's single
largest O2-consuming EC group (257 reactions, larger even than EC
1.14.13's 198). Same net transformation as the `o2-monooxygenase` class:
insert one atom of O2, reduce the other to water. The electron donor
differs by biological context rather than by chemistry — `CHEBI:57618`
is the *same* ChEBI entity Rhea's equation text variously labels "reduced
[NADPH--hemoprotein reductase]" (226 of 257 reactions), "FMNH2" (16) or
"reduced [flavodoxin]" (3); FADH2 (`CHEBI:58307`, 11 reactions) covers
most of the rest. Both are declared `unpriced_co_cofactor_chebi`, the
same mechanism `o2-monooxygenase` introduced, with the same stated gap:
the electron donor's own regeneration cost is real and unpriced.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.14.14) | 256 |
| excluded — could not identify an acceptor/product pair | 4 |
| excluded — right transfer count, wrong mass (several sub-chemistries) | 76 |
| **decided** | **176** |

The 4 unresolved reactions genuinely need a *third* reactant beyond O2
and the electron donor: three consume glutathione alongside an oxime
substrate, and one (RHEA:12312) uses FMNH2 and NADH as two separate
simultaneous reactants rather than the single reduced-donor shape this
class's co-cofactor list handles. This EC group is more chemically
diverse than EC 1.14.13's: 12 of the 76 mass-delta exclusions cluster
near −2.02, real dehydrogenation (the same 2H-loss signature the
NAD(P)+-oxidoreductase class's own `expected_mass_delta` targets, a
genuinely different transformation from oxygen insertion); 11 more
cluster near −30.03, consistent with a CH₂O leaving group; the remainder
is a long tail of rarer P450 chemistries (epoxidation, ring contraction,
oxidative C–C cleavage) this class does not attempt to enumerate — all
correctly kept out rather than folded in as noise.

Every one of the 176 decided reactions reaches a decisive verdict
favouring the enzyme, the same shape `o2-monooxygenase` shows, even with
the electron donor's real cost left entirely unpriced.

**Coverage across all twelve classes: 2,425 of 18,558 Rhea reactions
matched (13.1%), 1,463 decided (7.9%).**

## The thirteenth class: O2-dependent fatty acyl desaturation

`data/reaction-classes/o2-desaturase.yaml` covers EC 1.14.19 — fatty
acyl-CoA/-ACP/-lipid desaturases. Same O2 cofactor as the two
monooxygenase classes, but the *opposite* mass signature: this EC
group's dominant chemistry removes two hydrogens to form a new C=C
double bond (octadecanoyl-[ACP] → (9Z)-octadecenoyl-[ACP]), reducing O2
fully to two water molecules with four electrons from a co-substrate,
rather than inserting an oxygen atom. Net mass change: −2.016 g/mol, the
same signature the NAD(P)+-oxidoreductase class targets for 2H-loss
oxidation — this class is really "the same dehydrogenation chemistry,
powered by O2 instead of NAD(P)+", not a third sibling of the two
monooxygenase classes despite sharing their cofactor. Its process model
is reused directly from `nad-oxidoreductase.yaml` for the same reason:
the chemical route (TEMPO/NaOCl/KBr) does not know or care which
cofactor the enzyme used to drive the same net dehydrogenation.

Five co-cofactor identities cover the large majority of this class's
electron donors: Fe(II)-[cytochrome b5] (45 reactions), reduced
[NADPH--hemoprotein reductase] (23 — the same `CHEBI:57618` entity the
p450-monooxygenase class already declares), reduced
[2Fe-2S]-[ferredoxin] (22), NADPH (10) and FADH2 (8). Several reactions
consume *two* equivalents of a donor for the four-electron reduction of
O2 to two waters; since none of these five is priced, the doubled
stoichiometry needs no special handling.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.14.19) | 115 |
| excluded — could not identify an acceptor/product pair | 19 |
| excluded — right transfer count, wrong mass (3 other transformations) | 4 |
| **decided** | **92** |

The 19 unresolved reactions pair the acceptor with a further
small-molecule reactant (chloride, bromide, L-tryptophan) this class's
co-cofactor list does not cover — correctly, because those *are*
genuinely different chemistry (halogenases, not desaturases) rather than
something safe to also declare unpriced. The 4 mass-delta exclusions are
each a different confound: oxidative **dimerisation**
(RHEA:26031/RHEA:26035, two flaviolin molecules coupling to a
biflaviolin, +202.12 — a new C–C bond between two acceptor molecules,
not a desaturation of one), a complex multi-O2 reaction losing HCN and
CO2 (RHEA:52776, −75.07), and an oxidative decarbonylation-type loss of
formate (RHEA:58520, −29.02) — none folded in as noise.

Every one of the 92 decided reactions reaches a decisive verdict
favouring the enzyme, even with every electron donor's real cost left
entirely unpriced.

**Coverage across all thirteen classes: 2,540 of 18,558 Rhea reactions
matched (13.7%), 1,555 decided (8.4%).**

## The fourteenth class: O2-dependent dioxygenation, and a graded charge-state pattern

`data/reaction-classes/o2-dioxygenase.yaml` covers EC 1.13.11 —
dioxygenases that incorporate *both* atoms of O2 into the product
directly, with no separate electron-donor cofactor at all. Architecturally
the simplest of the four O2-consuming classes this project has built: no
`unpriced_co_cofactor_chebi` is declared, because none is needed.

**A charge-state pattern found four times before this class, but graded
rather than binary.** A genuine member adds both oxygen atoms, 31.998
g/mol — confirmed against RHEA:10428 (a lipoxygenase forming a
hydroperoxide, the cleanest possible member). But real members cluster at
*three* deltas, not one: 32.0, 30.99 (short one proton, RHEA:14409) and
29.98 (short two protons, RHEA:10084, a ring-cleaving catechol
dioxygenase that installs a new carboxylate ChEBI draws with mixed
protonation). `expected_mass_delta` is set to the midpoint of the two
extremes, 30.99, with `mass_delta_tolerance` widened to 1.1 — the same
"expected = true midpoint, tolerance = span the charge states" strategy
the UDP-glucuronosyltransferase class already uses, here spanning a
three-way rather than two-way split.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.13.11) | 102 |
| excluded — could not identify an acceptor/product pair | 2 |
| excluded — right transfer count, wrong mass (several sub-chemistries) | 41 |
| **decided** | **59** |

EC 1.13.11 is the most heterogeneous O2-consuming EC group this project
has templated: beyond simple O2 incorporation it also contains reactions
that split the acceptor into two separate products (a genuinely different
shape this project's single-acceptor/single-product resolver correctly
refuses to force into one pairing), oxidative ring cleavage releasing CO
or CO2, and carotenoid-cleaving dioxygenases that split one large acceptor
into two roughly-equal fragments. The 2 unresolved reactions each
genuinely require H2O as a third reactant beyond O2 (sulfur/thiol
oxidation to sulfite) — a different shape again, correctly left
unresolved rather than mis-decided.

Every one of the 59 decided reactions reaches a decisive verdict
favouring the enzyme, even though the chemical route's real stoichiometric
burden here — a catalytic photosensitiser (methylene blue, 2 mol%) plus
solvent — is genuinely small: the isolation solvent alone is enough.

**Coverage across all fourteen classes: 2,642 of 18,558 Rhea reactions
matched (14.2%), 1,614 decided (8.7%).**

## The fifteenth class: Fe(II)/2-oxoglutarate-dependent dioxygenation

`data/reaction-classes/2og-dioxygenase.yaml` covers EC 1.14.11 --
Fe(II)/2-oxoglutarate-dependent dioxygenases (prolyl and lysyl
hydroxylases, and many plant/microbial tailoring enzymes — the
gibberellin and clavulanic acid pathways among them). Mechanistically the
same net transformation as the two monooxygenase classes — insert one
oxygen atom into the acceptor — but the second oxygen atom oxidatively
decarboxylates the co-substrate 2-oxoglutarate to succinate + CO2, rather
than reducing NAD(P)H's family to water. 2-oxoglutarate
(`CHEBI:16810`) is declared `unpriced_co_cofactor_chebi`, a real, required
co-reactant this class does not price, the same mechanism with a very
different co-cofactor identity.

Unusually consistent equation shape across the whole EC group: every
resolvable member is written `acceptor + 2-oxoglutarate + O2 = product +
succinate + CO2`, with the real product always listed first on the right
— so the existing "first non-proton right-hand species" resolver needs no
change to pick it out correctly, even though succinate and CO2 are not
excluded from the search the way 2-oxoglutarate is on the left.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.14.11) | 101 |
| excluded — could not identify an acceptor/product pair | 1 |
| excluded — right transfer count, wrong mass (several sub-chemistries) | 40 |
| **decided** | **60** |

`expected_mass_delta` is identical to the two monooxygenase classes for
the identical reason: a genuine member adds one oxygen atom, 15.999
g/mol, verified directly against RHEA:10316 (thymine →
5-hydroxymethyluracil). The single unresolved reaction (RHEA:35975)
consumes a *second* cofactor (AH2) and two equivalents of O2 — a more
complex mechanism this class's simple two-reactant shape does not cover.
The 40 mass-delta exclusions cover oxidative ring formation and
desaturation among other confounds, correctly kept out rather than folded
in as noise.

Every one of the 60 decided reactions reaches a decisive verdict
favouring the enzyme, even with 2-oxoglutarate's real cost left entirely
unpriced.

**Coverage across all fifteen classes: 2,743 of 18,558 Rhea reactions
matched (14.8%), 1,674 decided (9.0%).**

## The sixteenth class: O2/ferredoxin-dependent monooxygenation

`data/reaction-classes/ferredoxin-monooxygenase.yaml` covers EC 1.14.15
— ferredoxin/rubredoxin-dependent monooxygenases: steroid and bile acid
hydroxylases, camphor 5-monooxygenase, alkane hydroxylases. Same net
transformation as the two earlier monooxygenase classes, with a third
family of electron-donor identity: reduced [2Fe-2S]-ferredoxin
(`CHEBI:33738`, which in Rhea's own text also covers "reduced
[adrenodoxin]" and "reduced [2Fe-2S]-[putidaredoxin]" — the same
underlying entity playing different named biological roles, the same
convention already found on `p450-monooxygenase`), reduced
2[4Fe-4S]-ferredoxin (`CHEBI:33723`) and reduced rubredoxin
(`CHEBI:29033`, already declared on `o2-desaturase`). All three are
declared `unpriced_co_cofactor_chebi`, covering all 72 of this EC
group's O2-consuming reactions.

| outcome | reactions |
|---|---:|
| matched (O2 + EC 1.14.15) | 72 |
| excluded — could not identify an acceptor/product pair | 2 |
| excluded — right transfer count, wrong mass (several sub-chemistries) | 20 |
| **decided** | **50** |

Every one of the 50 decided reactions reaches a decisive verdict
favouring the enzyme, the same shape every O2-consuming class this
project has built shows.

**Coverage across all sixteen classes: 2,815 of 18,558 Rhea reactions
matched (15.2%), 1,724 decided (9.3%).**

### Correction: ec_prefix removed, the ceiling re-derived, coverage updated

Everything above this line describes each class as it was built and
verified with `ec_prefix` restricting every one of them to a single EC
group. That restriction turned out to be unnecessary for ten of the
sixteen classes (SAM-methyltransferase, ATP-kinase, all four
prenyltransferase siblings, and all six O2-consuming classes): Rhea's own
EC annotation covers only 41.1% of its reactions, and `expected_mass_delta`
/ `transferred_bond_smarts` (plus, for the six O2 classes, the new
`required_co_cofactor_chebi` / `excluded_co_cofactor_chebi` fields) already
verify class membership structurally, without needing an EC number Rhea
does not always provide.

Two real bugs were found and fixed while testing this, both now part of
`screen.py`'s `_identify` and each class's own file header:

- **Water was never excluded from the acceptor search**, only the proton
  was. Invisible under the original EC-restricted classes (verified: zero
  previously-decided reactions had water as their acceptor), but it
  surfaced immediately once `ec_prefix` was removed from the
  prenyltransferase classes — DMAPP/GPP/FPP/GGPP diphosphate hydrolysis
  and terpene-cyclisation reactions (e.g. geranyl diphosphate + H2O =
  linalool + diphosphate) were passing the mass-delta check by
  coincidence of arithmetic, not real chemistry. Fixing it the same way
  the proton already was fixed three more false positives already live in
  the shipped glycosylation and glucuronidation classes (their own
  cofactor's hydrolysis, wrongly counted as a decided transfer) and
  recovered one true positive (an ATP-driven phenol phosphorylation,
  previously blocked by an ambiguous acceptor pairing with water).
- **All four prenyltransferase classes were treating a single
  isopentenyl-diphosphate (IPP) chain-elongation hop as a genuine transfer.**
  DMAPP/GPP/FPP/GGPP condensing with exactly one IPP equivalent (e.g.
  DMAPP + IPP = GPP + diphosphate, GPP synthase) is chain elongation, not
  prenylation of a foreign acceptor -- but it is arithmetically
  indistinguishable from a real transfer by mass delta alone, because the
  resolver picks IPP as "the acceptor" and the elongated product as "the
  product", and that delta always equals the donor's own transferred-group
  mass regardless of what it actually reacted with. This was already live
  in the shipped, EC-restricted classes (fpp-prenyltransferase's own
  header had claimed "both of the 2 decided reactions are genuine,
  real single-nucleophile prenylations" -- half of that 2 was this bug).
  Fixed with a new `excluded_co_cofactor_chebi` field that excludes IPP
  from matching entirely.

With both fixed, `ec_prefix` was removed from the ten classes above, each
now disambiguated by which co-cofactor it actually requires or excludes —
for the six O2 classes this meant reusing each class's own
`unpriced_co_cofactor_chebi` list as a `required_co_cofactor_chebi`
matching gate, and giving `o2-dioxygenase` (defined by the ABSENCE of any
other O2 class's co-cofactor) an `excluded_co_cofactor_chebi` list
covering the union of the other five. Several of those required lists
deliberately overlap (o2-desaturase and o2-monooxygenase both accept
NADPH; o2-desaturase and ferredoxin-monooxygenase both accept Fe(2+) and
reduced [2Fe-2S]) — verified this does not cause double-counting, because
each class's own `expected_mass_delta` is mutually exclusive by
construction (+15.999 for four of the six O2 classes, -2.016 for the
desaturase), so the mass-delta check is the real tiebreaker and zero
reactions ever decide for two classes at once (a dedicated test,
`test_no_rhea_reaction_decides_for_more_than_one_o2_class`, verifies this
directly against the real Rhea data).

Verified against all ten changed classes with zero reactions lost from
any class's previous decided set, and every newly decided reaction
spot-checked against its real equation. Corrected per-class numbers
(old ec_prefix-restricted matched/decided → new):

| class | old (EC-restricted) | new (ec_prefix removed) |
|---|---:|---:|
| sam-methyltransferase | 449 / 351 | 946 / 672 |
| atp-kinase | 209 / 203 | 1,059 / 369 |
| dmapp-prenyltransferase | 42 / 36 | 73 / 62 |
| gpp-prenyltransferase | 8 / 8 | 60 / 12 |
| fpp-prenyltransferase | 6 / 1 | 178 / 9 |
| ggpp-prenyltransferase | 6 / 3 | 55 / 5 |
| o2-monooxygenase | 198 / 134 | 441 / 262 |
| p450-monooxygenase | 256 / 176 | 920 / 623 |
| o2-desaturase | 115 / 92 | 1,534 / 267 |
| o2-dioxygenase | 102 / 59 | 932 / 197 |
| 2og-dioxygenase | 101 / 60 | 284 / 125 |
| ferredoxin-monooxygenase | 72 / 50 | 357 / 159 |

(The dmapp/gpp/fpp/ggpp "old" figures above already include the IPP fix;
before that fix they were 47/38, 11/10, 13/2, 9/4 — see each template's
own CORRECTION note.) acetyl-coa-acyltransferase and nad-oxidoreductase
were also measured with `ec_prefix` removed (138→347 and 515→1,659
matched) but both decide 0 reactions either way — a chemical-baseline-data
gap unrelated to `ec_prefix`, left untouched.

Because several O2 classes' "matched" candidate pools now overlap by
design, summing "matched" across classes overcounts unique reactions;
"decided" never does (verified: the sum of all sixteen classes' decided
counts equals the count of unique decided Rhea reactions, with zero
double-decided). The honest, unique-reaction total across all sixteen
classes: 6,505 of 18,558 Rhea reactions matched (35.1%), 3,305 decided
(17.8%) — up from 2,815/1,724 (15.2%/9.3%).

A seventeenth class, `paps-sulfotransferase.yaml` (3'-phosphoadenylyl
sulfate-dependent sulfation, built EC-free from the start -- see its own
file header), added 130 matched / 128 decided, all decisive: the mass-
delta check alone (net +79.056 g/mol, one proton's tolerance) separates
128 of 130 PAPS-consuming reactions with zero confounds found, the
tightest signal-to-noise ratio of any class this project has built.
Updated unique-reaction total: 6,635 of 18,558 Rhea reactions matched
(35.8%), 3,433 decided (18.5%).

An eighteenth class, `coa-ligase.yaml` (ATP/GTP-dependent CoA thioester
formation, the acid-thiol ligase mechanism), added 156 matched / **0
decided** -- a second honest non-result alongside NAD(P)+-oxidoreductase
and acetyl-CoA-acyltransferase, more extreme than either: CoA's own
transferred mass (746.502 g/mol, forming the whole acyl-CoA thioester) is
the largest of any class this project has built, and applied to the same
wide, unevidenced `[0.5, 100]` cofactor bound every unpriced cofactor
here uses, the enzymatic side's own uncertainty span alone (`[0.37,
74.6]` kgCO2e per functional unit) is wide enough to straddle any
plausible chemical-route footprint -- structurally undecidable at these
bounds, not merely close. All 156 matches resolve cleanly (zero excluded
by mass delta), and the class's marginal contribution to *unique* matched
coverage is small (+4, not +156) because most of its matches already fall
inside `atp-kinase`'s own widened matched set (both require ATP; they
never double-decide, since `atp-kinase`'s own mass-delta check correctly
rejects a ~746 g/mol addition as nowhere near its 77.963 target). Final
unique-reaction total: 6,639 of 18,558 Rhea reactions matched (35.8%),
3,433 decided (18.5%) -- unchanged from the seventeen-class figure at
this precision.

A systematic recovery across three existing classes, not a new one:
CHEBI:17499 ("AH2") is Rhea's own generic placeholder for "some
unspecified reduced donor," used wherever curators knew a
monooxygenase-type reaction needed one but not its specific identity.
169 reactions across every class this project has built were blocked
from resolving to a single acceptor by AH2 sitting unexcluded in the
acceptor search -- found the same way the water and IPP false-positive
fixes were, by inspecting what was actually blocking "could not
identify" cases in aggregate rather than per class. Genuine only for two
classes, verified per-class rather than applied globally, because AH2 is
a different confound on different classes: `sam-methyltransferase` (40
occurrences, radical-SAM chemistry, correctly left excluded) and
`atp-kinase` (13, tRNA sulfur-relay and cobalamin biosynthesis,
correctly left excluded) were checked and rejected; `o2-monooxygenase`
(+64 decided, zero lost) and `2og-dioxygenase` (+1) were verified
genuine. `o2-dioxygenase`'s exclusion list gained AH2 too, dropping its
matched count from 932 to 819 (decided unaffected at 197) so its
"matched" stays an honest count of bare-O2 candidates rather than
reactions that were never going to decide there.

One bug caught before landing: an initial attempt added AH2 to BOTH
classes' `required_co_cofactor_chebi`, which briefly made
`o2-monooxygenase` and `2og-dioxygenase` double-decide the same 64
reactions -- `required_co_cofactor_chebi` is OR logic, so a reaction with
AH2 present satisfied `2og-dioxygenase`'s gate even without
2-oxoglutarate. Fixed by declaring AH2 required only where it is a
genuine alternative donor identity (`o2-monooxygenase`, alongside
NAD(P)H) and unpriced-only, not required, where a different cofactor
already does the real gating (`2og-dioxygenase` stays gated on
2-oxoglutarate alone; AH2 there only helps `_identify` exclude it from
the acceptor search). Verified with
`test_no_rhea_reaction_decides_for_more_than_one_o2_class`: zero
double-decided across all six O2 classes after the fix.

Total after this fix, all eighteen classes: 6,639 of 18,558 Rhea reactions
matched (35.8%), 3,498 decided (18.8%).

A nineteenth class, `gdp-fucosyltransferase.yaml` (GDP-fucose-dependent
fucosylation), was found differently from every class before it: rather
than inspecting one EC group at a time, a script surveyed every
not-yet-covered cofactor with >=15 left-side reactions directly, computing
the real acceptor/product mass delta for each candidate the same way
`_identify` does, and ranking by what fraction of each cofactor's
reactions cluster on one signature mass. GDP-fucose came back the
cleanest of the whole survey: 76 of 77 reactions land within one proton
of 146.14 g/mol (the fucosyl group), the other 1 being GDP-fucose
SYNTHASE (the biosynthetic route that *makes* GDP-fucose, correctly
excluded as a different transformation). 77 matched, 76 decided, all
decisive -- including RHEA:14257, the human-milk-oligosaccharide
fucosylation this project's own Q3 target list already names. Its process
model is Koenigs-Knorr fucosylation with a real, commercially catalogued
glycosyl bromide donor (CAS 16741-27-8, verified via web search), the
same mechanism `udp-glucuronosyltransferase`'s own donor uses. The same
survey surfaced an even cleaner-looking sialyltransferase candidate
(CMP-N-acetyl-beta-neuraminate, 122 reactions, 97%+ purity including a
genuine 2-cofactor di-sialylation cluster) -- not built yet, because
standard sialylation donors are custom-synthesized per publication rather
than sold with one simple, verifiable commercial CAS number the way the
fucosyl bromide is; left as a documented candidate for a future session
rather than guessed at.

Total after this class, all nineteen: 6,715 of 18,558 Rhea reactions
matched (36.2%), 3,574 decided (19.3%).

A twentieth class, `udp-acetylhexosaminyltransferase.yaml` (UDP-GlcNAc /
UDP-GalNAc-dependent glycosylation), merges the two donors the same way
`udp-glucosyltransferase` merges UDP-glucose/UDP-galactose: C4 epimers,
identical transferred mass (203.194 g/mol, verified against RHEA:12588,
ganglioside GM3 -> GM2). 152 reactions match, 130 (85.5%) decide, all
decisive -- the least clean of the survey's top candidates, and reported
at that real number rather than rounded toward the 95%+ the flagship
glycosylation classes reach, because this cofactor pair has genuine
competing chemistry to separate out: GlcNAc-1-phosphate transfer onto
dolichyl phosphate (RHEA:13289, EC 2.7.8.15 -- a different enzyme family
transferring the whole phosphosugar, not just GlcNAc, at a different net
mass) and oxidation of the donor itself to the uronate (RHEA:13325,
NAD+-dependent), both correctly excluded by mass delta. Process model
uses a glycosyl CHLORIDE donor (CAS 3068-34-6, verified via web search)
rather than the bromide the other sugar-donor classes use, because the C2
acetamido group's neighbouring-group participation favours the more
stable chloride for this specific sugar.

Total after this class, all twenty: 6,863 of 18,558 Rhea reactions matched
(37.0%), 3,704 decided (20.0%) -- crossing 20% decided for the first
time this session.

`gdp-fucosyltransferase.yaml` was then extended rather than a twenty-first
class built: fucose and rhamnose are both L-configured 6-deoxyhexoses --
different stereochemistry, identical formula, identical transferred mass
(146.14 g/mol, verified against RHEA:61160, quercetin -> quercitrin) --
so UDP-beta-L-rhamnose (CHEBI:83836) was added to the class's own
`cofactor_chebi` list, the same merge already used twice (UDP-glucose/
UDP-galactose in `udp-glucosyltransferase`; UDP-GlcNAc/UDP-GalNAc in
`udp-acetylhexosaminyltransferase`). 14 of 15 rhamnose-consuming
reactions land on the identical delta (rhamnosylation of flavonoids and
saponins); the other 1 is chain elongation of a growing
rhamnogalacturonan, correctly excluded. The class was renamed
"6-deoxyhexose-nucleotide-dependent glycosylation" to reflect the merge.
One bug caught before landing: the bounds file needed a new entry for
UDP-rhamnose's own resolve key (`name:chebi:83836`) -- missing it left
all 15 newly-matched reactions indeterminate for an uninteresting reason
(a missing-bound gap, not the real economics), the same class of mistake
as coa-ligase's own missing THF bound earlier this session; fixed and
re-verified before the final numbers below.

Total after this merge, still twenty classes: 6,878 of 18,558 Rhea
reactions matched (37.1%), 3,718 decided (20.0%).

A twenty-first class, `udp-xylosyltransferase.yaml` (UDP-xylose-dependent
xylosylation), is the third and final class from the mass-delta survey's
clean-candidate tier. Xylose is a pentose, not a hexose, so it cannot
merge with `udp-glucosyltransferase` or `udp-acetylhexosaminyltransferase`
despite the identical Koenigs-Knorr mechanism -- it transfers a different
net mass, 132.12 g/mol, verified against RHEA:22244 (kaempferol ->
kaempferol 3-O-beta-D-xyloside: 417.346 - 285.231 = 132.115 exactly).
24 reactions match, 22 (91.7%) decide, all decisive -- including protein
O-xylosylation on EGF-like domains (RHEA:50192) alongside the more
familiar flavonoid/saponin xylosylation. The 2 excluded: a phosphoxylosyl
transfer at a different net mass (+211.09), and chain elongation of a
growing proteoglycan linkage region (-175.12), both correctly excluded by
mass delta rather than folded in.

Final total, all twenty-one classes: **6,902 of 18,558 Rhea reactions
matched (37.2%), 3,740 decided (20.2%)**.

See ["How far coverage can actually go"](../README.md#how-far-coverage-can-actually-go-and-why-not-further)
in the README for a related correction: an earlier version of that
section claimed a 43.5% structural ceiling and a 30–40% honest target,
both wrong for a reason unrelated to this section (it counted only
sixteen hand-picked cofactors rather than measuring true structural
reachability). The real ceiling is 88.6%, and O2 — described there as
untemplatable as a single class, which is still true of O2 *alone* — is
templatable as six classes once each one's actual electron-donor identity
is used as the discriminator instead of EC prefix, exactly as the six O2
classes in this document now do.

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
