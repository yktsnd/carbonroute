<!-- markdownlint-disable MD013 -->
# carbonroute

Comparative cradle-to-gate greenhouse-gas screening for synthetic routes.

`carbonroute` does not answer "what is the carbon footprint of this
synthesis?" It answers a narrower, cheaper-to-answer question: **given two
candidate routes to the same product, which one is lower, and how sure are
we?** The output is a ranking and a probability, with an explicit
"indeterminate" verdict when the evidence does not support one, never a
single absolute number presented as the answer.

This is v0. Read [`docs/limitations.md`](docs/limitations.md) and
["What this tool does not do"](#what-this-tool-does-not-do) below before
relying on it for anything.

## 概要

`carbonroute` は、2つの合成ルートの温室効果ガス排出量を比較し、「どちらが低いか、
どのくらい確からしいか」を返すツールである。「排出量はいくつか」という絶対値の
問いには答えない。両ルートに共通する原料・工程は差分をとることで相殺されるため、
解決すべきデータを大幅に減らせるという設計になっている（DeltaLCA の発想を合成
ルートに応用したもの、arXiv:2311.09611）。

前提（システム境界、電力の排出係数、GWP の時間地平、溶媒回収率など）はすべて
台帳ファイルの `assumptions` 節に集約し、それ以外の計算は決定論的である。値の
出所（一次データ／供給者値／背景データベース／構造推定／類似物代替）は個々に
保持し、集計後も追跡できる。不確実性が大きく順位が決まらない場合は、無理に結論
を出さず「判定不能」を返す。

本ツールは公開データのみで既定動作が完結するよう設計されている。ecoinvent の
ような商用データベースは同梱せず、`data/factors/` は v0 時点で数値を含まない
（理由は下記「What this tool does not do」参照）。出力は ISO 14067 準拠の
カーボンフットプリント算定結果ではない。詳細は本書の英語部分および
`docs/` 以下の各文書を参照。

## Why rank instead of measure

Most of a route's emissions come from the upstream manufacture of its inputs
and from grid electricity, not from anything a reaction equation tells you.
Getting an absolute number right therefore requires background data for
every input in both routes. Getting a *ranking* right only requires data for
the inputs that differ between the two routes — materials and process steps
common to both cancel out when you take the difference. That is why the
tool's central operation is a diff between two route inventories, not a
sum over one (spec `docs/spec-ja.md` sections 2 and 7.4; the diff idea is
borrowed from DeltaLCA, arXiv:2311.09611, which applies it to electronics
hardware).

Every assumption a human has to supply — system boundary, GWP time horizon,
grid emission factor, solvent recovery rate, Monte Carlo settings, the
probability band treated as a tie — lives in one place: the ledger's
`assumptions` block. Everything downstream of that block is deterministic:
the same ledger and the same factor tables always produce the same output.

## Install

Python 3.11 or later.

```bash
pip install -e .
```

Dependencies are limited to `pydantic`, `numpy`, `PyYAML`, and `click`.
RDKit is an optional extra (`pip install -e ".[chem]"`) used only to assist
material identification; it is never required to run the tool.

## The ledger

A route ledger is one YAML file. Its canonical shape is defined by
`src/carbonroute/schema.py` (pydantic models) and mirrored in
[`schemas/route-ledger.schema.json`](schemas/route-ledger.schema.json) for
external validation.

```yaml
schema_version: "0.1"

assumptions:
  functional_unit: {mass_kg: 1.0, basis: product}
  boundary: cradle-to-gate
  grid_factor:
    id: JP-2024
    value_kgCO2e_per_kWh: 0.43
    source: "Analyst-declared placeholder; replace with the grid factor you can cite."
    uncertainty_class: assumption
  gwp_method: {name: IPCC-AR6, horizon_years: 100, feedbacks: false}
  solvent_recovery_default: 0.0
  waste_treatment: excluded
  monte_carlo: {iterations: 10000, seed: 20240101}
  indeterminate_band: {low: 0.4, high: 0.6}

routes:
  legacy:
    label: "Published route"
    steps:
      - id: 1
        yield: 0.82
        inputs:
          - {name: toluene, cas: "108-88-3", mass_kg: 12.0, role: solvent}
          - {name: "substrate A", cas: null, mass_kg: 1.0, role: reactant}
        electricity_kWh: 30.0
  denovo:
    label: "New route"
    steps: [...]
```

Points worth knowing:

- `mass_kg` on an input is what was actually charged in that step. The tool
  scales it to the functional unit by dividing by the cumulative yield of
  every downstream step (spec section 7.1); you never do that arithmetic
  yourself.
- `role` is one of `solvent`, `reactant`, `reagent`, `catalyst`, `auxiliary`,
  used for the contribution breakdown by role.
- `cas` should be filled in whenever known — it is the primary join key
  against the factor table and against the same material appearing in a
  different route or step. A material without a CAS falls back to a
  normalized-name key, which is a weaker match and reported as such.
- `assumptions.solvent_recovery_default` (and the per-material
  `solvent_recovery` override) sets how much of a solvent's charged mass is
  treated as make-up rather than fresh input (spec section 7.2). The
  default is 0 — no recovery is assumed unless you say so.
- `routes` must be linear step lists. v0 has no way to express a route
  where two branches converge; see below.

The complete route ledger is the only place assumptions are allowed to
live. There is no other configuration surface for them.

## The five commands

```
carbonroute validate route.yaml
carbonroute resolve  route.yaml [--show-missing]
carbonroute coverage route.yaml --a <route> --b <route>
carbonroute compare  route.yaml --a <route> --b <route> -o report.md
carbonroute lock     route.yaml -o route.lock.json
```

- **`validate`** checks the ledger against the schema only. No factor
  lookup, no computation.
- **`resolve`** looks every material up in the factor table(s) and reports
  what matched and what did not. It does not compute any emissions.
- **`coverage`** reports how much of the A-versus-B delta set the loaded
  factor tables can actually resolve, by count and by mass, broken down by
  role. Mass coverage is not impact coverage — a catalyst charged at a
  fraction of a percent by mass can dominate a footprint — so the two numbers
  are meant to be read together. Exits 3 when anything in the delta set is
  unresolved.
- **`compare`** runs the full comparison — diff, Monte Carlo ranking,
  reversal thresholds — and writes the report.
- **`lock`** pins the factor table version(s), the resolved value and
  provenance for every material, and the RNG seed and iteration count, so
  that someone else can reproduce the exact numbers later.

`resolve`, `compare` and `lock` accept `--factors PATH` (repeatable;
defaults to every CSV under `data/factors/`). `compare` and `lock` accept
`--uncertainty PATH` (defaults to the bundled `config/uncertainty.yaml`);
`resolve` does not, because it never touches the uncertainty model.
`compare` additionally takes `--iterations`, `--seed` and `--no-thresholds`.
`validate` takes no options: it reads the ledger and nothing else. A `--fetch` flag exists on `resolve` and
`compare` for a future network-backed factor lookup; in v0 it exits with an
error, because **network access is off by default and there is no code path
in this tool that opens a socket.** The only side effect any command has is
writing the file named by `-o`; without `-o`, output goes to stdout.

### Worked example

`data/factors/` now ships a small table of real, citable factors (see
["What is in `data/factors/`"](#what-is-in-datafactors)), but it covers only
a handful of substances, so the example below points explicitly at the
placeholder table in `examples/` to keep every material resolvable.
`examples/route.yaml` defines two illustrative routes, `legacy` and
`denovo`, to the same (invented) product.

```bash
# 1. Structural check only.
carbonroute validate examples/route.yaml

# 2. See what resolves against the illustrative factor table, and what
#    would be missing if it were the only table available.
carbonroute resolve examples/route.yaml \
  --factors examples/factors_illustrative.csv \
  --show-missing

# 3. Compare the two routes and write a Markdown report.
carbonroute compare examples/route.yaml \
  --a legacy --b denovo \
  --factors examples/factors_illustrative.csv \
  -o report.md

# 4. Pin the exact factor values, versions, and RNG seed used, for
#    someone else to reproduce.
carbonroute lock examples/route.yaml \
  --factors examples/factors_illustrative.csv \
  -o route.lock.json
```

`report.md` opens with a statement that the result is not an ISO
14067-conformant calculation, the full text of the assumptions applied, the
factor table versions and their SHA-256 hashes, and the provenance
breakdown of the resolution — in that order — before it states any
conclusion. Because every row in `examples/factors_illustrative.csv` is
marked `ILLUSTRATIVE`, the report also carries a prominent warning that its
conclusion is not usable for anything beyond exercising the pipeline. The
conclusion itself is always a ranking and a probability
(`P(GWP_legacy < GWP_denovo)`, a verdict of `"A<B"` / `"B<A"` /
`"indeterminate"`, and the median and 90% interval of the difference) —
never a single absolute footprint presented as the headline result.

## What this tool does not do

This list is deliberate, not an oversight, and it is unlikely to shrink
quickly (see `docs/spec-ja.md` section 5.2 and `docs/limitations.md`).
v0 does not:

- **Handle convergent routes.** Only linear step sequences are supported.
  A route where two synthesis branches merge into one cannot be expressed
  in the ledger schema at all.
- **Extrapolate from lab scale to plant scale.** Inputs are taken at face
  value from the ledger; there is no model for how solvent use, heating
  efficiency, or yield change between a bench reaction and an industrial
  process.
- **Model the use phase or end-of-life.** The boundary is fixed at
  cradle-to-gate. Nothing downstream of the product leaving the gate is in
  scope.
- **Cover impact categories beyond climate change.** The only output
  quantity is GWP (kg CO2e). Water use, toxicity, land use, and every other
  ISO 14044 impact category are out of scope.
- **Use a language model anywhere in the calculation path.** No factor
  value, no resolution decision, and no number in a report is ever produced
  or adjusted by a language model. This is a deliberate response to
  measured unreliability of general-purpose LLMs on LCA-adjacent tasks
  (arXiv:2510.19886 found 37% of answers across 11 models and 22 LCA tasks
  contained inaccurate or misleading content, with fabricated-citation
  rates up to 40% for some models).
- **Generate routes by retrosynthesis.** `carbonroute` compares routes you
  give it; it does not propose or search for candidate syntheses.

And separately from the list above: **the output of this tool is not an
ISO 14067-conformant product carbon footprint.** It is a screening
comparison meant to help decide which route deserves a full assessment, not
a substitute for one. Every report says so explicitly, as required by spec
section 9.

## What is in `data/factors/`

`data/factors/` ships real emission factors, every one of them fetched from
an openly licensed source by a script in `scripts/` that you can re-run to
regenerate the table. Each row names the dataset and the record it came
from, the licence it is distributed under, the date it was retrieved, and —
where the source published one — its own uncertainty.

**The coverage is small.** Openly licensed, independently citable,
per-kilogram cradle-to-gate factors for fine-chemical solvents and reagents
are genuinely scarce; most of what the field uses day to day sits in
commercial databases this project may not redistribute. Expect a real
comparison to leave materials unresolved. That is what `carbonroute
coverage` is for: it tells you how much of your delta set the tables reach,
by count and by mass, so the gap is a number in front of you rather than a
silent omission. Adding a source means writing another ingestion script —
see [`docs/data.md`](docs/data.md) and
[`docs/sources-investigated.md`](docs/sources-investigated.md), which
records the sources that were checked and why each was or was not used.

Nothing here is estimated, interpolated, or recalled from memory. That is a
consequence of the "public data only, nothing invented" rule (spec sections
2 and 13): a table of plausible-looking numbers nobody can check would
defeat the entire purpose of the tool.

`examples/factors_illustrative.csv` exists purely so the pipeline can be
run end to end. Every value in it is an obviously-fake round number, every
row's `source` column starts with `ILLUSTRATIVE`, and any report built from
it says so prominently. Do not cite it, and do not use it for anything but
exercising the commands above.

## Benchmarks

Two test sets, both with their acceptance conditions written before the
assertions (`benchmarks/README.md`).

**B1, the analytic case**, is small enough to check by hand. It pins the
functional-unit conversion, solvent make-up, the exact cancellation of
materials common to both routes, and bit-for-bit reproducibility from a seed.

**B2, the letermovir comparison**, is real. The ledger comes from the
supplementary workbook of an open-access study
([doi:10.1021/jacs.5c14470](https://doi.org/10.1021/jacs.5c14470)) that
compared a published Merck route against a de novo route and reported 382
against 369 kgCO2e/kg — a 3% gap. Those figures were computed with ecoinvent,
so this project cannot reproduce them and does not try; the masses travel, the
factors do not.

What B2 measures instead is what happens when the data runs out, which is the
normal case. Openly licensed factors resolve **2 of the 43 materials that
differ between the routes, 8.9% of the differing mass**. That is the measured
answer to the question the specification left open, and it is not a flattering
one.

The benchmark earned its place immediately. Before it existed the tool treated
an unresolved material as absent rather than unknown, and on that 9% it
reported `P > 0.9999` — for the ranking opposite the published one. Two things
came out of the failure: a coverage floor below which no ranking is reported at
all, and a break-even calculation that asks what the missing materials would
have to average for the ranking to flip. Here the answer is about 0.19
kgCO2e/kg against 30 kg/FU of unresolved mass, which is below every organic
solvent in this project's own table. So the tool argues for the published
ranking without ever asserting it, and hands you the condition instead of a
guess.

## Further reading

- [`docs/data.md`](docs/data.md) — the factor-table format and how to build
  a table you can cite.
- [`docs/uncertainty.md`](docs/uncertainty.md) — how the Monte Carlo model
  works and the status of its parameters.
- [`docs/convergence.md`](docs/convergence.md) — how many Monte Carlo
  iterations are enough, and what has not yet been checked.
- [`docs/limitations.md`](docs/limitations.md) — what this tool can and
  cannot be expected to get right.
- [`docs/spec-ja.md`](docs/spec-ja.md) — the full design specification
  (Japanese), the authority on intent for everything above.
- [`docs/internal-api.md`](docs/internal-api.md) — the module-level
  contract for contributors.

## License

Apache License 2.0. See [`LICENSE`](LICENSE). Code and data have separate
licensing: the code in `src/` is Apache-2.0; any factor table you add to
`data/factors/` carries whatever license its own source imposes, tracked
per row (see `docs/data.md`).
