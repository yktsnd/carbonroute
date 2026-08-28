# β-arbutin (chemical vs enzymatic) — sources and provenance

## Why this case study, and a correction made along the way

The request was "hydroquinone to β-arbutin, industrial (chemical) route vs
enzymatic route (glycosyltransferase)". Checking the literature before
building anything surfaced a real mismatch worth recording: essentially
every well-documented, industrially-optimized "hydroquinone + glycosyl-
transferase" route in the literature (amylosucrase, sucrose phosphorylase,
cyclodextrin glucanotransferase) produces **α-arbutin**, a different anomer,
because those enzymes are retaining glycosidases that act on **α**-configured
sugar donors (starch/sucrose-derived). β-arbutin — the naturally-occurring
anomer — is conventionally made either by plant extraction, by chemical
glycosylation, or by a much less industrially mature enzymatic route using a
genuinely β-selective glycosyltransferase. This was surfaced to the user
directly; the response was to keep β-arbutin as the target and use the real
(if less industrially mature) β-selective enzymatic route, and to treat the
enzymatic route's conversion efficiency as an open question to be answered
by the comparison itself rather than assumed.

## The chemical route: Cepanec & Litvić, ARKIVOC 2008

**Citation**: Cepanec, I.; Litvić, M. "Simple and efficient synthesis of
arbutin." *ARKIVOC* **2008** (ii), 19–24. Freely readable,
[arkat-usa.org/get-file/22982/](https://www.arkat-usa.org/get-file/22982/).
The full PDF was fetched and read directly (not summarized) for every
number below. ARKIVOC is a no-fee open-access journal that states articles
are freely reusable, but this session could not independently confirm the
exact licence terms in effect for a 2008 article against ARKAT USA's own
policy page (returned HTTP 503 when checked) — so, as with the ibuprofen
case study, **no copy of the PDF is committed to this repository**; every
number below is a citation to the paper, not a redistribution of it.

This is a **Helferich-variant, BF₃·Et₂O-catalysed glycosylation**, not a
disclosed industrial process — it is the only source found this session
with a **complete, fully quantitative** experimental procedure (every
reagent's exact mass/mmol, every solvent volume, every isolated yield) for
β-arbutin specifically. A modern microwave-accelerated variant using a
different (benzyl) protecting group exists in the literature (Xue, Yang,
Deng, He & Chen, *Bull. Korean Chem. Soc.* **2010**, 31, 1825, cited as
ref. [31] in the review below) and industrial patents almost certainly use
more concentrated, higher-throughput conditions than an academic bench
procedure — **neither was independently verified this session**, and this
is the single most important caveat on everything that follows: see
"What this comparison is not" below.

Scheme (3 stages, all in one paper, all quantities read directly from the
Experimental Section):

1. **Donor preparation** — acid-catalysed transesterification of
   hydroquinone diacetate with hydroquinone gives the aglycone donor,
   4-hydroxyphenyl acetate:
   hydroquinone diacetate (19.41 g, 0.1 mol) + hydroquinone (11.01 g,
   0.1 mol) + H₂SO₄ (0.1 mL, 184 mg, 1.9 mmol, 2 mol%) in toluene (60 mL),
   reflux 1 h → 30.18 g (**99.2%**) of donor.
2. **Glycosylation** — BF₃·Et₂O-catalysed reaction of penta-*O*-acetyl-
   β-D-glucopyranose with the donor from step 1:
   penta-*O*-acetyl-β-D-glucopyranose (3.90 g, 10 mmol, limiting) + donor
   (2.28 g, 15 mmol, 1.5 eq) + BF₃·Et₂O (50%, 2.5 mL, 10 mmol, 1.0 eq) in
   anhydrous CH₂Cl₂ (50 mL), reflux 72 h → 3.01 g (**62%**, based on the
   limiting reagent) of penta-*O*-acetyl-β-arbutin.
3. **Deprotection** — K₂CO₃/MeOH/H₂O saponification:
   penta-*O*-acetyl-β-arbutin (485 mg, 1 mmol) + K₂CO₃ (2.07 g, 15 mmol) in
   MeOH (50 mL) + water (10 mL), r.t./N₂/24 h, quenched with methanolic
   H₂SO₄ (0.4 mL, 0.74 g, 7.5 mmol), extracted with boiling EtOAc
   (3×50 mL) → 230 mg (**85%**) of pure β-arbutin.

The paper also reports an alternative 83–92% range for this step (via
aminolysis with methanolic ammonia as well as saponification); the 85%
figure used here is the one given full quantitative detail.

## The enzymatic route: arbutin synthase (AS)

The relevant enzyme is a UDP-glucose-dependent hydroquinone
glucosyltransferase from *Rauvolfia serpentina* ("arbutin synthase", AS,
EC 2.4.1.218), characterised in a recombinant whole-cell *E. coli* system by:

**Citation**: Arend, J.; Warzecha, H.; Hefner, T.; Stöckigt, J. "Utilizing
genetically engineered bacteria to produce plant-specific glucosides."
*Biotechnol. Bioeng.* **2001**, 76, 126–131. DOI:
[10.1002/bit.1152](https://doi.org/10.1002/bit.1152). **Paywalled** —
Wiley returned HTTP 403 to a direct fetch this session, and the exact
reaction quantities and conversion percentage reported in this paper could
**not** be independently verified. A review article ("Chemical and
Biocatalytic Routes to Arbutin", Cardoso et al., *Molecules* **2019**, 24,
3303, DOI 10.3390/molecules24183303, open access via PMC6766929) paraphrases
this and a related paper as achieving "95% conversion ... within 5 h", but
that figure's citation marker did not match up with either paper's actual
subject when checked directly — a fetch of the underlying article confirmed
the [36] reference the review attaches to that figure is actually a paper
about enzymatic hydroquinone *production* (from benzene), not the arbutin
synthase reaction. **That "95%" figure is therefore not used anywhere in
this ledger or its numbers.** This is the same discipline applied
throughout this project: a citation that cannot be verified against its
own source is discarded, not used with a caveat.

What this leaves is the reaction's own stoichiometry, which is real
chemistry and needs no citation beyond standard atomic weights:

```
hydroquinone + UDP-glucose --[arbutin synthase]--> beta-arbutin + UDP
```

one mole of each substrate for one mole of product. `ledger.yaml`'s
enzymatic route uses this 1:1 stoichiometric relationship
(`hydroquinone: 0.4045 kg/FU`, `UDP-glucose: 2.080 kg/FU`, both at the
theoretical 100%-yield amount) with `yield: 0.5` set as an **illustrative
placeholder only** — not a literature value — precisely so the real,
unresolved question (how efficient does this reaction need to be?) can be
answered by sweeping it, rather than asserted.

## What this comparison is not

**It is not a comparison of two industrial processes.** The chemical
route's numbers come from a first-generation academic bench procedure,
deliberately run dilute for a proof-of-concept synthesis, not an optimized
plant. The reagent masses below include over 870 kg of solvent (mostly
ethyl acetate and methanol) per 1 kg of final product — a ratio no real
manufacturer would tolerate; a real plant would run far more concentrated
and recycle the bulk of that solvent by distillation. This is disclosed,
not hidden, and its effect on the verdict is checked directly below rather
than assumed away.

**It is not a claim about how efficient the enzymatic route really is.**
No independently verifiable conversion percentage for the arbutin synthase
reaction on hydroquinone was found this session; the ledger's `yield: 0.5`
is a display placeholder, and the actual analysis below sweeps it.

## Coverage and the verdict

```
carbonroute coverage examples/case-studies/beta-arbutin-chemical-vs-enzymatic/ledger.yaml --a chemical --b enzymatic
carbonroute compare  examples/case-studies/beta-arbutin-chemical-vs-enzymatic/ledger.yaml --a chemical --b enzymatic
```

**97.9% of the delta mass resolves** (6 of 12 materials, dominated by the
chemical route's held solvent factors: toluene, dichloromethane, methanol,
ethyl acetate, water and sulfuric acid are all in `data/factors/`).
Unresolved: potassium carbonate, UDP-glucose, penta-*O*-acetyl-β-D-
glucopyranose, hydroquinone diacetate, boron trifluoride diethyl etherate,
and the *differential* in hydroquinone use between the two routes.

At the placeholder 50% enzymatic yield: **`enzymatic` is very likely lower
than `chemical` (P > 0.9999)**, resolved delta +1431 kgCO2e/FU, and — per
the tool's own break-even check — **no positive value for any of the
unresolved materials can reverse this**, because the unresolved mass at
this yield leans the same direction the resolved part already does.

## Sweeping what isn't known: yield and solvent recovery

Two real unknowns were swept directly rather than assumed:

**Enzymatic yield**, over `carbonroute compare`'s own reversal-threshold
scan, range [0.05, 1.0]: **no crossing**. The verdict does not change
across the entire range — `enzymatic` stays lower at every yield from 5% to
100%. Extending the sweep by hand below 5%: only below roughly 13–15% yield
does a mathematical break-even value for the unresolved materials even
start to exist, and even then it is implausibly low for a nucleotide sugar
(159 kgCO2e/kg at 10% yield, falling to under 1 kgCO2e/kg by 0.1% yield) —
lower yields make UDP-glucose's own required break-even *more* stringent,
not less, so this is not a realistic route to reversing the verdict.

**Chemical-route solvent recovery**, swept by hand from 0% to 99.99%
(`assumptions.solvent_recovery_default`, beyond the schema's own scan
range of [0, 0.95] to check the extreme case directly):

| solvent recovery | resolved delta (chemical − enzymatic), kgCO2e/FU |
|---|---|
| 0% | 1430.7 |
| 90% | 143.5 |
| 95% | 72.0 |
| 99% | 14.8 |
| 99.9% | 1.9 |
| 99.99% | 0.62 |

The verdict does not flip even at 99.99% recovery — and at that extreme
the tool's own break-even check still finds no positive value for the
unresolved materials that reverses it. This is a genuinely robust result
across the two largest sources of uncertainty in this comparison (how
efficient the enzymatic reaction is, and how much solvent the chemical
route actually loses to make-up), **conditional on the chemical route's
real reagent stoichiometry being roughly right even under industrial
optimization** — a condition this session could not independently verify
against a disclosed industrial process (see "What this comparison is not").

## CAS resolution

All CAS numbers were resolved live via PubChem PUG REST (name → CID →
synonyms, first CAS-shaped synonym validated against
`carbonroute.schema.cas_checksum_ok`), 2026-08-28. Molecular weights used
for the stoichiometric arithmetic above were computed from standard atomic
weights and cross-checked against the paper's own reported mass/mmol pairs
for every compound (all matched to within normal rounding).
