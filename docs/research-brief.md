# Open data gaps: a brief for deep research

Four numbers this repository does not hold from a document it has actually
read. Each one is named in the code or template where it is missing, and each
is left as a stated gap rather than filled with a plausible value.

Paywalls closed several routes in-session: orgsyn.org and mdpi.com refuse
automated access, and the canonical enzyme-production LCA is behind Springer.
The prompt below is written to be pasted into a deep-research tool that can
reach those.

**The prompt is in English deliberately** — the literature is, and search
recall is materially better for it.

---

## The prompt

````text
You are helping fill precisely specified data gaps in an open-source
carbon-footprint screening tool. The tool refuses to use any number that has
not been read from a real document, so I need verifiable primary sources with
exact quantities — not summaries, not typical values, not your own estimates.

## Absolute rules

1. Every number you report MUST be accompanied by the verbatim sentence from
   the source that contains it, in quotation marks, plus the full citation
   and DOI.
2. If you cannot find a number, write "NOT FOUND" for that field. Do NOT
   substitute a typical value, an industry rule of thumb, a value from a
   different substance, or your own reasoning. A stated gap is more useful to
   me than a plausible number, and a plausible number is actively harmful.
3. Distinguish sharply between (a) a quantity actually CHARGED in a described
   experiment or process, and (b) a theoretical stoichiometric quantity, and
   (c) a value derived or scaled by the authors. Label every figure with
   which it is.
4. Report the OPEN-ACCESS STATUS and LICENCE of each source (CC BY 4.0, CC
   BY-NC, publisher copyright, preprint, etc.). I can only ship data whose
   licence permits redistribution, so this determines usability.
5. Prefer peer-reviewed literature. Patents and theses are acceptable if
   fully quantified — flag them as such. Vendor marketing material is not
   acceptable as a source for a number.
6. Where several sources disagree, report all of them with their values
   rather than picking one.

## Gap A — Cradle-to-gate GWP of industrial enzyme production

I need kg CO2-equivalent per kg of enzyme, cradle to gate.

The canonical source I could not access:
  Nielsen, P.H.; Oxenbøll, K.M.; Wenzel, H. "Cradle-to-gate environmental
  assessment of enzyme products produced industrially in Denmark by
  Novozymes A/S." Int. J. Life Cycle Assess. 2007, 12(6), 432–438.

Please retrieve it and any comparable later work, and report:
  - GWP value(s) and units, one row per enzyme product reported.
  - CRITICAL: what "1 kg of enzyme" means in that figure — kg of pure
    protein, kg of formulated/granulated commercial product, or kg of
    enzyme-protein-equivalent? These differ by an order of magnitude and the
    paper's own wording decides it. Quote the functional-unit definition.
  - The system boundary (does it include fermentation feedstock, downstream
    processing, formulation, packaging?).
  - Reference year, region, and electricity mix assumed.
  - Whether the figure is a lower bound, an average, or product-specific.

Also search for: any newer open-access enzyme-production LCA (2015–2026),
including simulation-based ones, and any figure for enzyme production in
ecoinvent, GaBi, Agri-footprint or a national LCI database that is publicly
quotable.

## Gap B — Immobilised enzyme: loading, carrier, and reuse

For glycosyltransferases, sucrose synthase, or — failing those — any
well-documented immobilised industrial biocatalyst, I need the numbers that
let an immobilised preparation be amortised over the batches it serves:

  - ENZYME LOADING: mass of enzyme (or of immobilisate) per mass or per mole
    of product. State the basis exactly as the paper does; if it is given as
    g/L plus a titre, give both and I will convert.
  - CARRIER: its chemical identity (methacrylate resin, epoxy-functionalised
    polymer, chitosan, silica, magnetic particle, etc.), and the mass ratio
    of carrier to enzyme.
  - REUSE: the number of batches or cycles the preparation is reported to
    survive, and at what retained activity (e.g. "10 cycles at >80% residual
    activity"). Also report operational half-life or total turnover number
    (TTN) of the ENZYME if given.
  - Whether the reported reuse is laboratory batch recycling or a genuine
    continuous/packed-bed operation, and for how long.

Prioritise: immobilised sucrose synthase, immobilised UDP-glycosyltransferase
(UGT), enzymatic glycosylation with cofactor recycling, and immobilised
biocatalysts used at pilot or production scale.

## Gap C — UDP-glucose regeneration with sucrose synthase: charged amounts

The 1:1 stoichiometry (sucrose + UDP -> UDP-glucose + fructose) is already
known. What I need is what a real process CHARGES, which is not the
stoichiometry:

  - Sucrose EQUIVALENTS actually charged relative to acceptor (systems drive
    the equilibrium with excess).
  - The catalytic loading of UDP or UDP-glucose — mol% relative to acceptor —
    which is the actual cofactor turnover number of the system.
  - Reported total turnover number (TTN) for the UDP/UDP-glucose cycle.
  - Final product titre (g/L) and reaction volume, so a per-kg-product basis
    can be computed.
  - Any reported downstream separation of the fructose co-product.

Search terms to try: "sucrose synthase UDP-glucose regeneration", "UGT
sucrose synthase cascade", "one-pot glycosylation cofactor regeneration",
"rebaudioside sucrose synthase UDP-glucose recycling".

## Gap D — A genuinely solvent-lean chemical glycosylation

I hold one chemical glycosylation template — Cepanec & Litvić, ARKIVOC 2008
(ii) 19–24, a Helferich/BF3·Et2O procedure — whose product isolation charges
150 mL of boiling ethyl acetate per millimole (159 kg per mole of product).
That single term dominates every comparison I run, and recovering 99% of it
is not the same thing as not using it.

I need one real, fully quantified published chemical O-glycosylation whose
authors were themselves trying to minimise solvent — mechanochemical/
ball-mill, solvent-free, aqueous, continuous-flow, or a process-scale (not
bench-scale) isolation using crystallisation or antisolvent rather than bulk
extraction.

For that procedure report, per step:
  - Substrate, glycosyl donor, promoter/activator, base: name, mass or
    volume, mmol, equivalents.
  - EVERY solvent, in the reaction AND in workup, extraction, washing and
    chromatography: name and volume in mL, and how many times each was
    repeated. This is the number I actually need — a procedure reported
    without workup solvent volumes is useless to me, so please say so
    explicitly if the volumes are absent.
  - Temperature, time, isolated product mass, mmol, and percentage yield.
  - Scale (mmol or g of product), and whether the authors report any
    green-chemistry metric (E-factor, PMI, atom economy).

## Gap E — Cradle-to-gate GWP of sucrose

A publicly quotable, openly licensed cradle-to-gate GWP for sucrose (cane or
beet, food or technical grade), in kg CO2e per kg. Report region, reference
year, whether land-use change is included, and the licence. National LCI
databases, government datasets and CC-licensed publications are all fine.

## Output format

For every gap, produce a table with one row per source:

| field | value |
|---|---|
| citation | authors, title, journal, volume(issue), pages, year |
| DOI | |
| open access / licence | |
| how I can retrieve it | direct URL, repository, or "paywalled" |
| the number(s) | value + unit |
| verbatim quote | the exact sentence containing the number |
| charged / stoichiometric / derived | |
| caveats | scale, basis, anything that would make me misuse it |

End with an explicit list titled "NOT FOUND", naming every field above that
you could not fill, so I know what remains open rather than having to infer
it from silence.
````

---

## Why each gap matters, for whoever reads the answer

- **A and B together** are what put the enzyme itself into the comparison.
  It is currently absent entirely, which understates the enzymatic route.
  B's `reuse_cycles` is the number immobilisation exists to raise, and the
  template's `amortised` charge shape already accepts it.
- **C** replaces the theoretical one-sucrose-per-turnover figure — which
  understates the co-substrate burden, and so still flatters the enzyme —
  with what a real system charges.
- **D** is the larger of the two. Until the chemical side is represented by a
  procedure that is itself solvent-lean, `--fair-fight` is comparing a
  serious enzymatic process against a wasteful chemical one that is merely
  distilling its mistakes back, and the enzyme wins by construction.
- **E** would turn a bound into a factor, narrowing every verdict that
  involves regeneration.
