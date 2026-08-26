# Internal API contract (v0)

This file is the single source of truth for module boundaries. Modules already
written: `schema.py`, `ledger.py`, `resolve.py`. Read them before implementing
against this contract; the signatures below are binding.

Package root: `src/carbonroute/`. Python 3.11+. Dependencies are limited to
pydantic, numpy, PyYAML, click. RDKit must stay optional and unimported at
module import time.

## Already implemented

### `schema.py`
`SCHEMA_VERSION = "0.1"`, `Role`, `normalize_name(str) -> str`,
`cas_checksum_ok(str) -> bool`, `material_key(cas: str|None, name: str) -> str`
(returns `"cas:108-88-3"` or `"name:substrate a"`).

Models (pydantic v2, `extra="forbid"`): `FunctionalUnit(mass_kg, basis)`,
`GridFactor(id, value_kgCO2e_per_kWh, source, uncertainty_class="assumption")`,
`GWPMethod(name, horizon_years, feedbacks)`,
`MonteCarloSettings(iterations=10000, seed=20240101)`,
`IndeterminateBand(low=0.4, high=0.6)`,
`Assumptions(functional_unit, boundary, grid_factor, gwp_method,
solvent_recovery_default, solvent_recovery: dict[str,float], waste_treatment,
monte_carlo, indeterminate_band)`,
`MaterialInput(name, cas, mass_kg, role, recovery)` with `.key`,
`Step(id, yield_ [YAML key `yield`], inputs, electricity_kWh)`,
`Route(label, steps)`, `Ledger(schema_version, assumptions, routes: dict[str, Route])`.

Models are immutable-by-convention; to vary an assumption use
`assumptions.model_copy(deep=True, update={...})` or
`Assumptions.model_validate(dict)`.

### `ledger.py`
- `LedgerError(ValueError)`
- `load_ledger(path) -> Ledger`
- `step_factors(route) -> dict[str, float]` — key is `str(step.id)`
- `adjust_route(name, route, assumptions) -> AdjustedRoute`
- `adjust_all(ledger) -> dict[str, AdjustedRoute]`
- `MaterialAmount(key, name, cas, role, mass_kg, gross_mass_kg, recovery)`
- `AdjustedRoute(name, label, materials: list[MaterialAmount], electricity_kWh,
  step_factors, by_step)` with helpers `.masses()`, `.roles()`, `.names()`

All masses in an `AdjustedRoute` are per functional unit, with solvent make-up
already applied.

### `resolve.py`
- `FactorTableError(ValueError)`
- `Factor(key, identifier, name, gwp_kgCO2e_per_kg, source, database_version,
  region, retrieved_date, uncertainty_class, license, notes, table)` with
  property `.is_illustrative`
- `Resolution(key, name, factor: Factor|None, matched_by: str|None)` with `.resolved`
- `FactorTable.load(paths) -> FactorTable`, `.load_file(path)`,
  `.lookup(key, name) -> Resolution`, `.fingerprint() -> str`,
  attributes `.by_key`, `.by_name`, `.sources: dict[path, sha256]`
- `default_factor_paths(root=None) -> list[Path]`
- `resolve_materials(materials, table) -> dict[str, Resolution]`
- `ILLUSTRATIVE_MARKER = "ILLUSTRATIVE"`

## To implement

### `compute.py`

```python
@dataclass(frozen=True)
class ContributionRow:
    key: str; name: str; role: Role
    mass_kg: float
    factor: Factor | None
    gwp_kgCO2e: float | None          # None when unresolved

@dataclass(frozen=True)
class RouteResult:
    name: str; label: str
    materials: list[ContributionRow]  # sorted by gwp desc, unresolved last
    electricity_kWh: float
    electricity_gwp_kgCO2e: float
    material_gwp_kgCO2e: float        # resolved rows only
    total_kgCO2e: float               # material + electricity
    missing: list[str]                # unresolved material keys, sorted
    by_role: dict[str, float]         # role -> kgCO2e (resolved only)
    by_provenance: dict[str, float]   # uncertainty_class -> kgCO2e; electricity
                                      # counted under grid_factor.uncertainty_class

def route_result(adjusted: AdjustedRoute,
                 resolutions: dict[str, Resolution],
                 assumptions: Assumptions) -> RouteResult: ...
```
`total_kgCO2e` is computed from resolved rows only and is **never** the headline
of a report (spec section 13).

```python
@dataclass(frozen=True)
class DeltaRow:
    key: str; name: str; role: Role
    mass_a_kg: float; mass_b_kg: float
    delta_mass_kg: float              # a - b
    factor: Factor | None
    resolved: bool

@dataclass(frozen=True)
class DiffResult:
    a_name: str; b_name: str
    rows: list[DeltaRow]              # |delta| > tol only, sorted by |delta*gwp| desc
    delta_electricity_kWh: float      # a - b
    common_unresolved: list[str]      # unresolved but cancelling: informational
    delta_unresolved: list[str]       # unresolved and NOT cancelling: warning

def diff_routes(a: AdjustedRoute, b: AdjustedRoute,
                resolutions: dict[str, Resolution],
                tol: float = 1e-9) -> DiffResult: ...
```
Spec section 7.4: a material whose adjusted masses match in both routes drops
out entirely and its resolution failure is informational, not a warning.

```python
@dataclass(frozen=True)
class Comparison:
    a: RouteResult; b: RouteResult
    diff: DiffResult
    stats: "ComparisonStats"
    assumptions: Assumptions
    factor_fingerprint: str
    factor_sources: dict[str, str]        # path -> sha256
    illustrative_keys: list[str]          # resolved via an ILLUSTRATIVE row
    resolutions: dict[str, Resolution]

def run_comparison(ledger: Ledger, a_name: str, b_name: str,
                   table: FactorTable, model: "UncertaintyModel",
                   iterations: int | None = None,
                   seed: int | None = None) -> Comparison: ...
```
`run_comparison` raises `KeyError` (wrapped as `ValueError` with a clear message)
if a route name is absent. `iterations`/`seed` override
`ledger.assumptions.monte_carlo` when given.

### `uncertainty.py`

```python
@dataclass(frozen=True)
class UncertaintyModel:
    classes: dict[str, float]        # class name -> GSD
    descriptions: dict[str, str]
    fallback_class: str
    path: str
    def gsd(self, uncertainty_class: str) -> float: ...

def load_uncertainty(path: str | Path | None = None) -> UncertaintyModel: ...
```
Default path: `src/carbonroute/config/uncertainty.yaml`, located relative to
`uncertainty.__file__` so it works from an installed package.

```python
@dataclass(frozen=True)
class ComparisonStats:
    p_a_lower: float                 # P(GWP_A < GWP_B)
    verdict: str                     # "A<B" | "B<A" | "indeterminate"
    delta_median: float              # median of GWP_A - GWP_B, kgCO2e
    delta_p05: float; delta_p95: float
    median_a: float; median_b: float
    iterations: int; seed: int
    excluded_keys: list[str]         # delta materials left out (unresolved)

def compare_monte_carlo(diff: DiffResult, assumptions: Assumptions,
                        model: UncertaintyModel,
                        iterations: int, seed: int) -> ComparisonStats: ...
```

Sampling rules, which are the heart of the tool:
- One draw per **material key**, applied to the *difference* in mass. A material
  present in both routes therefore uses the same factor sample on both sides, so
  its uncertainty cancels exactly. This is the DeltaLCA idea (arXiv:2311.09611).
- Factor `g_i` is lognormal with **median** equal to the tabulated value and
  `sigma = log(gsd)` for the row's `uncertainty_class`:
  `g = value * exp(sigma * z)`, `z ~ N(0,1)`. A GSD of 1.0 means no dispersion —
  use the point value, do not call the sampler.
- The grid factor gets one draw too, using
  `assumptions.grid_factor.uncertainty_class`, applied to `delta_electricity_kWh`.
- `delta_j = sum_i(delta_mass_i * g_ij) + delta_elec * grid_j`
- `p_a_lower = mean(delta < 0)`.
- `median_a` / `median_b` are the deterministic resolved totals of each route
  (take them from the `RouteResult`s; `compare_monte_carlo` receives only the
  diff, so `run_comparison` fills these fields — implement it however is
  cleanest but keep the dataclass shape).
- `verdict` is `"indeterminate"` when
  `band.low <= p_a_lower <= band.high` (spec section 7.6), else `"A<B"` when
  `p_a_lower > 0.5`, else `"B<A"`.
- RNG: `numpy.random.default_rng(seed)`. Draw all materials in **sorted key
  order** so results are byte-reproducible. The same seed and inputs must give
  identical output (spec section 10).

### `sensitivity.py`

```python
@dataclass(frozen=True)
class Threshold:
    variable: str          # e.g. "solvent_recovery_default", "grid_factor", "yield:legacy:1"
    label: str             # human-readable
    low: float; high: float          # range searched
    baseline: float                  # current value
    crossing: float | None           # value where P crosses 0.5, None if no crossing
    p_at_low: float; p_at_high: float
    message: str

def reversal_thresholds(ledger: Ledger, a_name: str, b_name: str,
                        table: FactorTable, model: UncertaintyModel,
                        iterations: int = 2000,
                        seed: int | None = None) -> list[Threshold]: ...
```
Variables to scan (spec section 7.7): `solvent_recovery_default` over
`[0.0, 0.95]`, the grid factor over `[0.0, max(1.0, 2*baseline)]`, and each step
yield of both routes over `[0.05, 1.0]`. Vary one at a time from the baseline
ledger, rebuild the comparison, and bisect for `P = 0.5` (30 iterations or
`1e-4` bracket width). If `P` does not straddle 0.5 across the range, set
`crossing=None` and a message saying the ranking does not change over that range.
Use a reduced iteration count for speed and a **fixed** seed per evaluation so
the bisection sees a smooth, deterministic function of the variable.

### `report.py`

```python
def render_report(comparison: Comparison, thresholds: list[Threshold] | None,
                  ledger_path: str) -> str: ...        # Markdown

def render_resolution_table(routes: dict[str, RouteResult],
                            table: FactorTable, show_missing: bool) -> str: ...

def build_lock(ledger: Ledger, ledger_path: str, table: FactorTable,
               resolutions: dict[str, Resolution],
               comparison: Comparison | None = None) -> dict: ...
```
Report must open with, in this order (spec section 9):
1. a statement that the result is **not** an ISO 14067-conformant calculation
2. the full text of the applied assumptions
3. the factor table versions and their sha256 hashes
4. the provenance breakdown of the resolution
Then the conclusion **as a ranking and a probability**, never a single absolute
number as a heading. If any consumed factor is illustrative, or if
`diff.delta_unresolved` is non-empty, put a prominent warning above the
conclusion. `build_lock` returns a JSON-serialisable dict pinning:
schema version, tool version (`carbonroute.__version__`), ledger sha256,
factor table paths + hashes, uncertainty config path + hash, the resolved
factor value and provenance for every key, and the RNG seed and iteration count.

### `cli.py`

Click group `main`, four commands (spec section 8):

```
carbonroute validate route.yaml
carbonroute resolve  route.yaml [--show-missing]
carbonroute compare  route.yaml --a legacy --b denovo -o report.md
carbonroute lock     route.yaml -o route.lock.json
```
Shared options: `--factors PATH` (repeatable; defaults to
`default_factor_paths()`), `--uncertainty PATH`, and for `compare`
`--iterations`, `--seed`, `--no-thresholds`. A `--fetch` flag exists on
`resolve`/`compare` and currently exits with a clear "no network fetchers are
implemented in v0" error — **network access is off by default and there is no
code path that opens a socket**. The only side effects permitted are writes to
the paths given by `-o`; without `-o`, print to stdout. Non-zero exit codes:
2 for validation/loading failures, 3 when `resolve` finds missing factors in a
requested comparison's delta set. Errors go to stderr as plain text, never a
traceback.
