# Rhea: the enzymatic reaction database

Written by `scripts/ingest_rhea.py`. Re-run it to refresh, or with
`--offline` to rebuild these files from the frozen snapshot in
`data/raw/rhea/` without touching the network (see
[`docs/reproducibility.md`](../../docs/reproducibility.md)).

## Contents

| file | what it is |
|---|---|
| `reactions.tsv` | one row per Rhea reaction: id, equation, ChEBI participants, EC number |
| `participants.csv` | every ChEBI participant, ranked by how many distinct reactions it appears in, with its SMILES |

## Source and licence

[Rhea](https://www.rhea-db.org/) is an expert-curated database of
biochemical reactions from the SIB Swiss Institute of Bioinformatics with
EMBL-EBI, released under **CC BY 4.0**. Participants are
[ChEBI](https://www.ebi.ac.uk/chebi/) identifiers (EMBL-EBI, also CC BY 4.0),
so every reaction here is a fully specified balanced equation with
structures attached, not free text.

Retrieved from the REST API at `https://www.rhea-db.org/rhea` and the bulk
TSVs at `https://ftp.expasy.org/databases/rhea/tsv/`. The exact retrieval
timestamps are in `data/raw/rhea/manifest.json`.

Please cite Rhea and ChEBI if you use these files.

## The measurement that makes a database-wide screen affordable

`carbonroute compare` answers one question about two routes. Rhea holds
about 18,500 enzymatic reactions, and building a sourced ledger for each is
not a project, it is a career. What makes screening the whole database
tractable is not a shortcut — it is a structural property of the diff.

When two routes make the same product, everything common to both cancels
out of the delta set. For enzyme-versus-chemistry, the part that cancels is
exactly the part that would be expensive to look up: the substrate and the
product, which are different in every reaction. What survives is the
**cofactor** on one side and the **protecting groups, activator, base and
solvents** on the other — and both are small closed vocabularies.

That is a claim about the data, so the ingestion script counts it rather
than asserting it. From the current snapshot:

```
reactions:                                        18,558
distinct ChEBI participants:                      14,251
participant slots (reaction x distinct species):  87,367

how many species recur:
  in >=     5 reactions:   1,513
  in >=    10 reactions:     633
  in >=    25 reactions:     232
  in >=    50 reactions:     114
  in >=   100 reactions:      63
  in >=   500 reactions:      20
  in >=  1000 reactions:      12

cumulative coverage of all participant slots:
  top   10 species:  33.8%
  top   30 species:  47.8%
  top   60 species:  53.5%
  top  120 species:  58.2%
  top  300 species:  64.1%
```

Twelve species appear in a thousand reactions or more. The top thirty cover
almost half of every participant slot in the database, and they are exactly
the cofactor vocabulary a biochemist would name from memory: H₂O, O₂, CoA,
ATP, NADP⁺/NADPH, NAD⁺/NADH, diphosphate, phosphate,
S-adenosyl-L-methionine, ADP, FMN/FMNH₂, UDP, AMP, 2-oxoglutarate,
acetyl-CoA, UDP-glucose, FAD, malonyl-CoA.

The ~36% of slots the top 300 do *not* cover is the long tail of
one-reaction substrates and products — the part that cancels. So the factor
work a database-wide screen actually requires is bounded by the size of
those vocabularies, in the tens of substances, and each additional reaction
after that costs one arithmetic evaluation. Screening all 263 reactions of
the UDP-glucosyltransferase class takes about a second.

## What is not here

No emission factor for any cofactor. None of the recurring species above
has an openly licensed cradle-to-gate GWP that this project could find,
UDP-glucose included — which is why the screen treats the cofactor as a
bounded interval rather than a value, and why its output is a threshold
rather than a number. See [`docs/bounds.md`](../../docs/bounds.md) and
[`docs/screening.md`](../../docs/screening.md).

## Parsing coverage

Of 18,558 reactions, 16,855 parse cleanly into participants matched to
ChEBI ids. The remaining 1,703 use notation `screen.py` deliberately does
not model — compartment tags (`(out)`, `(in)` on transport reactions) and
generic redox placeholders (`A`/`AH2`) — and are skipped and counted rather
than guessed at.
