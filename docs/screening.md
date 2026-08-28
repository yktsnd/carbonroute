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
arithmetic evaluation — the whole 263-reaction UDP-glucosyltransferase class
screens in about a second.

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

## What the shipped class actually found

Screening all 263 UDP-glucose-dependent glycosylations in Rhea against the
Helferich/BF₃ procedure of Cepanec & Litvić (ARKIVOC 2008):

| statistic | recovery threshold |
|---|---|
| minimum | 85.58% |
| median | 85.87% |
| maximum | 91.43% |

**None of the 256 decided reactions survives 99% solvent recovery**, and the
whole distribution sits at or below the 90–95% a real plant achieves. The
honest reading is not "enzymes win 256 times" but: *in this class, as
modelled from this bench procedure, the enzymatic advantage is real but
bounded, and it does not survive industrial solvent recycling.* That is a
falsifiable claim, and a much more useful one.

The mechanism the screen exists to measure does show up cleanly in the
spread. The threshold rises with the number of protectable groups on the
acceptor — 85.58% where the acceptor has one group or none, 91.43% for a
33-group oligosaccharide — because an enzyme's regioselectivity is worth
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
on chemistry, so that test is what gives the other 262 rows any standing.

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
```

Screening needs RDKit — it is what turns Rhea's molar stoichiometry into the
mass basis the rest of the tool uses, and what counts protectable groups
from a structure:

```bash
pip install -e ".[chem]"
```

## Adding a class

1. Pick a cofactor that recurs in `data/rhea/participants.csv`. Its
   `n_reactions` column is how many reactions one template would serve.
2. Find **one real, fully quantified published chemical procedure** for the
   same transformation. Every `sourced` amount in the template must come
   from a document actually retrieved and read — the same bar
   `data/processes/` holds.
3. Reduce it to amounts per mole of product, and mark anything you had to
   extend beyond that paper as `generalised`, with the extension stated.
4. Write bounds for whatever the template consumes that no public factor
   covers — including the cofactor, which is the entire enzymatic side and
   therefore where the verdict lives.
5. Calibrate: if any reaction in the new class already has a hand-built
   ledger, assert the screen agrees with it.
