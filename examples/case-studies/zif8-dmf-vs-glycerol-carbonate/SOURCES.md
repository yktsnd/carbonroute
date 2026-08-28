# ZIF-8 (DMF vs glycerol carbonate) — sources and provenance

## Citation

Sessa, A.; Rossi, E.; Prete, P.; Passarini, F.; Itatani, M.; Rossi, F.;
Lagzi, I. et al. "Life Cycle Assessment of Solvothermal Zeolitic
Imidazolate Framework-8 Synthesis: Is the Substitution of
N,N-Dimethylformamide with Glycerol Carbonate Environmentally
Sustainable?" *ChemSusChem* **2025**, 18(24), e202502019.
DOI: [10.1002/cssc.202502019](https://doi.org/10.1002/cssc.202502019),
PMC12703451. **Licence: CC BY 4.0** (verified — see `source-material/README.md`).

Retrieved 2026-08-28. Supporting Information fetched from Europe PMC:
`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12703451/supplementaryFiles`,
committed at `source-material/CSSC-18-e202502019-s001.pdf`.

## Why this case study

This is a same-process, single-variable comparison: one solvothermal ZIF-8
synthesis, run once in N,N-dimethylformamide (DMF) and once in glycerol
carbonate (GlyC), a bio-based solvent proposed as a "greener" substitute.
The paper's own conclusion is the interesting part: replacing a toxic
solvent with a bio-derived one does not, on their analysis, guarantee a
lower footprint — a genuinely useful case for a tool built to be honest
about that kind of surprise.

## What the ledger's numbers are, exactly

The paper's functional unit is already 1 g of ZIF-8 (Section 3.1, "cradle-to-gate
LCA referring to the synthesis of 1 g of ZIF-8 (FU)"), and every mass in its
own inventory tables is already expressed per that functional unit. This
ledger's masses are those table values divided by 1000 (g to kg), with no
further conversion — the same "already-normalized, so `yield: 1.0`" treatment
used for the letermovir benchmark.

| Ledger material | Route | Value | Source cell |
| --- | --- | --- | --- |
| zinc nitrate hexahydrate | z_dmf | 3.28 g | SI Table S2.1.1, "Zn(NO3)2·6H2O" row |
| 2-methylimidazole | z_dmf | 7.24 g | SI Table S2.1.1 |
| N,N-dimethylformamide | z_dmf | 51 g | SI Table S2.1.1, "DMF" row |
| methanol | z_dmf | 20 g | SI Table S2.1.1, "MeOH" row |
| electricity | z_dmf | 10.25 + 0.30 + 0.08 = 10.63 kWh | SI Table S2.1.1, the three "Energy" rows |
| glycerol | z_glyc_base | 176.07 g | SI Table S2.1.2, "glycerol (RO)" row |
| dimethyl carbonate | z_glyc_base | 517.07 g | SI Table S2.1.2, "DMC" row |
| sodium carbonate | z_glyc_base | 0.61 g | SI Table S2.1.2, "Na2CO3" row |
| zinc nitrate hexahydrate | z_glyc_base | 1.82 g | SI Table S2.1.2 |
| 2-methylimidazole | z_glyc_base | 1.36 g | SI Table S2.1.2 |
| methanol | z_glyc_base | 20 g | SI Table S2.1.2, "MeOH" row |
| electricity | z_glyc_base | 0.33 + 2.75 + 5.71 + 0.15 + 0.30 = 9.24 kWh | SI Table S2.1.2, the five "Energy" rows |

Both tables are on the same page of the SI (Section S2.1, "LCI of the main
scenarios"), immediately following the "S1" GlyC-synthesis-and-characterisation
section.

The paper models the glycerol carbonate route's solvent as synthesised
**in-house**, inside this route's own cradle-to-gate boundary, from glycerol
and dimethyl carbonate over a sodium carbonate catalyst — unlike DMF, which
is charged as a finished market chemical. That asymmetry is the paper's own
system-boundary choice; this ledger keeps it rather than smoothing it into
a single "solvent" line for either route.

The paper also reports three further GlyC variants (Z-GlyC-wco, using waste
cooking oil as the glycerol source; Z-GlyC-avp, crediting DMC and methanol
as avoided products; Z-GlyC-best, combining both). This ledger uses only the
baseline Z-GlyC-base, because carbonroute's schema has no way to express an
"avoided product" credit — modelling the other variants correctly would
require system-expansion accounting this tool does not support, not a
different set of input rows.

## Grid factor

The SI's own electricity entries cite a global-average background process
("Electricity, medium voltage {GLO} | market group for | APOS, U"), not a
specific country. No citable public GLO grid factor was found. This ledger
instead declares ADEME's verified France 2020 grid factor (0.0599
kgCO2e/kWh, Base Carbone element id 28333) as its `grid_factor` — a real,
citable number, but a different geography than the source paper's own
boundary. `carbonroute compare`'s electricity contribution therefore reflects
the French grid, not the paper's, and the ledger's `grid_factor.source` field
says so.

## Coverage, measured

```
carbonroute coverage examples/case-studies/zif8-dmf-vs-glycerol-carbonate/ledger.yaml --a z_dmf --b z_glyc_base
```

**6.8% of the differing mass resolves** (1 of 6 materials — methanol, 20 g in
both routes, cancels exactly and isn't even in the delta set). Dimethyl
carbonate (517 g/FU) dominates the unresolved mass; no openly licensed
cradle-to-gate factor for it was found in ADEME Base Carbone or ProBas/GEMIS
(checked 2026-08-28). `carbonroute compare` returns `indeterminate`, well
below the 80% ranking floor.

This is the lowest-coverage of the three case studies in this repository,
kept specifically because it shows the coverage gate doing its job on a real,
CC BY, peer-reviewed comparison — not just on the two harder pharmaceutical
cases.
