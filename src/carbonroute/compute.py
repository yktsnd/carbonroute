"""Emission accounting, route diffing, and top-level comparison (spec section 7.3-7.4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import AdjustedRoute, adjust_route
from .resolve import Conflict, Factor, FactorTable, Resolution, resolve_materials
from .schema import Assumptions, Ledger, Role
from .uncertainty import ComparisonStats, UncertaintyModel, compare_monte_carlo


@dataclass(frozen=True)
class ContributionRow:
    key: str
    name: str
    role: Role
    mass_kg: float
    factor: Factor | None
    gwp_kgCO2e: float | None  # None when unresolved


@dataclass(frozen=True)
class RouteResult:
    name: str
    label: str
    materials: list[ContributionRow]  # sorted by gwp desc, unresolved last
    electricity_kWh: float
    electricity_gwp_kgCO2e: float
    material_gwp_kgCO2e: float  # resolved rows only
    total_kgCO2e: float  # material + electricity
    missing: list[str]  # unresolved material keys, sorted
    by_role: dict[str, float]  # role -> kgCO2e (resolved only)
    by_provenance: dict[str, float]  # uncertainty_class -> kgCO2e; electricity
    # counted under grid_factor.uncertainty_class


def route_result(
    adjusted: AdjustedRoute,
    resolutions: dict[str, Resolution],
    assumptions: Assumptions,
) -> RouteResult:
    rows: list[ContributionRow] = []
    missing: list[str] = []
    by_role: dict[str, float] = {}
    by_provenance: dict[str, float] = {}
    material_gwp = 0.0

    for m in adjusted.materials:
        res = resolutions.get(m.key)
        factor = res.factor if res is not None else None
        if factor is None:
            missing.append(m.key)
            gwp: float | None = None
        else:
            gwp = m.mass_kg * factor.gwp_kgCO2e_per_kg
            material_gwp += gwp
            by_role[m.role] = by_role.get(m.role, 0.0) + gwp
            by_provenance[factor.uncertainty_class] = (
                by_provenance.get(factor.uncertainty_class, 0.0) + gwp
            )
        rows.append(
            ContributionRow(
                key=m.key, name=m.name, role=m.role, mass_kg=m.mass_kg, factor=factor, gwp_kgCO2e=gwp
            )
        )

    # Unresolved rows sort last; among resolved rows, largest contribution first.
    rows.sort(key=lambda r: (r.gwp_kgCO2e is None, -(r.gwp_kgCO2e or 0.0)))
    missing.sort()

    electricity_gwp = adjusted.electricity_kWh * assumptions.grid_factor.value_kgCO2e_per_kWh
    by_provenance[assumptions.grid_factor.uncertainty_class] = (
        by_provenance.get(assumptions.grid_factor.uncertainty_class, 0.0) + electricity_gwp
    )

    return RouteResult(
        name=adjusted.name,
        label=adjusted.label,
        materials=rows,
        electricity_kWh=adjusted.electricity_kWh,
        electricity_gwp_kgCO2e=electricity_gwp,
        material_gwp_kgCO2e=material_gwp,
        total_kgCO2e=material_gwp + electricity_gwp,
        missing=missing,
        by_role=by_role,
        by_provenance=by_provenance,
    )


@dataclass(frozen=True)
class DeltaRow:
    key: str
    name: str
    role: Role
    mass_a_kg: float
    mass_b_kg: float
    delta_mass_kg: float  # a - b
    factor: Factor | None
    resolved: bool


@dataclass(frozen=True)
class DiffResult:
    a_name: str
    b_name: str
    rows: list[DeltaRow]  # |delta| > tol only, sorted by |delta*gwp| desc
    delta_electricity_kWh: float  # a - b
    common_unresolved: list[str]  # unresolved but cancelling: informational
    delta_unresolved: list[str]  # unresolved and NOT cancelling: warning


def diff_routes(
    a: AdjustedRoute,
    b: AdjustedRoute,
    resolutions: dict[str, Resolution],
    tol: float = 1e-9,
) -> DiffResult:
    a_masses = a.masses()
    b_masses = b.masses()
    a_roles = a.roles()
    b_roles = b.roles()
    a_names = a.names()
    b_names = b.names()

    all_keys = sorted(set(a_masses) | set(b_masses))

    rows: list[DeltaRow] = []
    common_unresolved: list[str] = []
    delta_unresolved: list[str] = []

    for key in all_keys:
        mass_a = a_masses.get(key, 0.0)
        mass_b = b_masses.get(key, 0.0)
        delta = mass_a - mass_b
        res = resolutions.get(key)
        factor = res.factor if res is not None else None

        if abs(delta) <= tol:
            # Spec 7.4: identical adjusted mass cancels out of the delta set
            # entirely; an unresolved material here is merely informational.
            if factor is None:
                common_unresolved.append(key)
            continue

        if factor is None:
            delta_unresolved.append(key)

        role = a_roles.get(key) or b_roles.get(key)
        name = a_names.get(key) or b_names.get(key)
        rows.append(
            DeltaRow(
                key=key,
                name=name,
                role=role,
                mass_a_kg=mass_a,
                mass_b_kg=mass_b,
                delta_mass_kg=delta,
                factor=factor,
                resolved=factor is not None,
            )
        )

    def _sort_key(row: DeltaRow) -> float:
        gwp = row.factor.gwp_kgCO2e_per_kg if row.factor is not None else 0.0
        return -abs(row.delta_mass_kg * gwp)

    rows.sort(key=_sort_key)

    return DiffResult(
        a_name=a.name,
        b_name=b.name,
        rows=rows,
        delta_electricity_kWh=a.electricity_kWh - b.electricity_kWh,
        common_unresolved=sorted(common_unresolved),
        delta_unresolved=sorted(delta_unresolved),
    )


@dataclass(frozen=True)
class Comparison:
    a: RouteResult
    b: RouteResult
    diff: DiffResult
    stats: ComparisonStats
    assumptions: Assumptions
    factor_fingerprint: str
    factor_sources: dict[str, str]  # path -> sha256
    illustrative_keys: list[str]  # resolved via an ILLUSTRATIVE row
    factor_conflicts: list[Conflict]  # substances the loaded tables disagree about
    derived_keys: list[str]  # resolved via a model, not a measurement
    resolutions: dict[str, Resolution]


def run_comparison(
    ledger: Ledger,
    a_name: str,
    b_name: str,
    table: FactorTable,
    model: UncertaintyModel,
    iterations: int | None = None,
    seed: int | None = None,
) -> Comparison:
    try:
        route_a = ledger.routes[a_name]
        route_b = ledger.routes[b_name]
    except KeyError as exc:
        raise ValueError(f"unknown route name: {exc}") from exc

    assumptions = ledger.assumptions
    adjusted_a = adjust_route(a_name, route_a, assumptions)
    adjusted_b = adjust_route(b_name, route_b, assumptions)

    materials = list(adjusted_a.materials) + list(adjusted_b.materials)
    resolutions = resolve_materials(materials, table)

    result_a = route_result(adjusted_a, resolutions, assumptions)
    result_b = route_result(adjusted_b, resolutions, assumptions)
    diff = diff_routes(adjusted_a, adjusted_b, resolutions)

    mc = assumptions.monte_carlo
    use_iterations = iterations if iterations is not None else mc.iterations
    use_seed = seed if seed is not None else mc.seed

    stats = compare_monte_carlo(diff, assumptions, model, use_iterations, use_seed)

    # A tight interval over the resolved fraction is not a tight interval over
    # the comparison. When most of the differing mass never reached a factor,
    # the Monte Carlo is measuring the dispersion of a subset and saying nothing
    # about the rest, so the ranking is withheld rather than reported with a
    # confidence the data does not support. This is what the benchmark in
    # benchmarks/letermovir exists to catch.
    cov = coverage(diff)
    verdict = stats.verdict
    reason = ""
    if cov.mass_fraction < assumptions.min_delta_coverage:
        verdict = "indeterminate"
        reason = (
            f"only {cov.mass_fraction * 100:.1f}% of the differing mass "
            f"({cov.resolved_count} of {cov.delta_material_count} materials) resolved to a "
            f"factor, below the declared minimum of "
            f"{assumptions.min_delta_coverage * 100:.0f}%"
        )

    # median_a/median_b are the deterministic resolved totals, not MC outputs;
    # compare_monte_carlo only sees the diff, so fill them in here.
    stats = ComparisonStats(
        p_a_lower=stats.p_a_lower,
        verdict=verdict,
        delta_median=stats.delta_median,
        delta_p05=stats.delta_p05,
        delta_p95=stats.delta_p95,
        median_a=result_a.total_kgCO2e,
        median_b=result_b.total_kgCO2e,
        iterations=stats.iterations,
        seed=stats.seed,
        excluded_keys=stats.excluded_keys,
        coverage_mass_fraction=cov.mass_fraction,
        indeterminate_reason=reason,
    )

    from .bootstrap import is_derived

    derived_keys = sorted(
        {
            key
            for key, res in resolutions.items()
            if res.resolved and res.factor is not None and is_derived(res.factor)
        }
    )

    illustrative_keys = sorted(
        {
            key
            for key, res in resolutions.items()
            if res.resolved and res.factor is not None and res.factor.is_illustrative
        }
    )

    return Comparison(
        a=result_a,
        b=result_b,
        diff=diff,
        stats=stats,
        assumptions=assumptions,
        factor_fingerprint=table.fingerprint(),
        factor_sources=dict(table.sources),
        illustrative_keys=illustrative_keys,
        factor_conflicts=list(table.conflicts),
        derived_keys=derived_keys,
        resolutions=resolutions,
    )


@dataclass(frozen=True)
class Coverage:
    """How much of a comparison the available factor tables can actually reach.

    This measures the last open question in the specification (section 14):
    what fraction of a real delta set does a table limited to solvents and
    common reagents cover? The answer is reported in two units because they
    disagree, and the disagreement is the point.
    """

    delta_material_count: int
    resolved_count: int
    delta_mass_kg: float
    resolved_mass_kg: float
    unresolved: list[tuple[str, str, Role, float]]
    by_role: dict[Role, tuple[float, float]]

    @property
    def unresolved_count(self) -> int:
        return self.delta_material_count - self.resolved_count

    @property
    def count_fraction(self) -> float:
        if not self.delta_material_count:
            return 1.0
        return self.resolved_count / self.delta_material_count

    @property
    def mass_fraction(self) -> float:
        if self.delta_mass_kg == 0.0:
            return 1.0
        return self.resolved_mass_kg / self.delta_mass_kg


def coverage(diff: DiffResult) -> Coverage:
    """Coverage of the delta set by the loaded factor tables.

    Mass coverage is a proxy for impact coverage, and a poor one. The study
    this project benchmarks against found that a catalyst charged at 1 mol %
    dominated a step's footprint, which no mass-based measure could see. A
    high mass coverage with a catalyst missing is not good coverage; the
    per-role breakdown is there so that case stays visible.
    """
    total_mass = 0.0
    resolved_mass = 0.0
    resolved_count = 0
    unresolved: list[tuple[str, str, Role, float]] = []
    by_role: dict[Role, list[float]] = {}

    for row in diff.rows:
        magnitude = abs(row.delta_mass_kg)
        total_mass += magnitude
        slot = by_role.setdefault(row.role, [0.0, 0.0])
        slot[1] += magnitude
        if row.resolved:
            resolved_count += 1
            resolved_mass += magnitude
            slot[0] += magnitude
        else:
            unresolved.append((row.key, row.name, row.role, magnitude))

    unresolved.sort(key=lambda item: -item[3])
    return Coverage(
        delta_material_count=len(diff.rows),
        resolved_count=resolved_count,
        delta_mass_kg=total_mass,
        resolved_mass_kg=resolved_mass,
        unresolved=unresolved,
        by_role={role: (vals[0], vals[1]) for role, vals in sorted(by_role.items())},
    )


def resolved_delta_gwp(diff: DiffResult, assumptions: Assumptions) -> float:
    """The part of GWP_A - GWP_B that the factor tables can actually account for."""
    total = sum(
        row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg
        for row in diff.rows
        if row.resolved and row.factor is not None
    )
    total += diff.delta_electricity_kWh * assumptions.grid_factor.value_kgCO2e_per_kWh
    return total


@dataclass(frozen=True)
class FlipFactor:
    """What the unresolved part of a delta set would have to be to reverse the ranking.

    No factor is invented here. The question asked is the inverse one: given the
    signed mass that could not be resolved, what single average kgCO2e/kg would
    it need to carry for the two routes to tie? A small answer means the ranking
    rests on the missing data; a large one means it survives most of what the
    gap could plausibly hold. Either way the reader gets a number instead of a
    silent assumption that the gap is zero.
    """

    resolved_delta_kgCO2e: float
    unresolved_delta_mass_kg: float          # signed, a - b
    breakeven_kgCO2e_per_kg: float | None    # None when no positive value flips it
    note: str


def unresolved_flip_factor(diff: DiffResult, assumptions: Assumptions) -> FlipFactor:
    resolved = resolved_delta_gwp(diff, assumptions)
    signed_mass = sum(row.delta_mass_kg for row in diff.rows if not row.resolved)

    if not diff.delta_unresolved:
        return FlipFactor(resolved, 0.0, None, "Every material in the delta set resolved.")
    if signed_mass == 0.0:
        return FlipFactor(
            resolved,
            0.0,
            None,
            "The unresolved masses cancel in the difference, so a uniform factor over "
            "them cannot change the ranking. A non-uniform one still could.",
        )

    breakeven = -resolved / signed_mass
    if breakeven <= 0.0:
        return FlipFactor(
            resolved,
            signed_mass,
            None,
            "No positive average factor over the unresolved mass reverses the ranking, "
            "because that mass leans the same way the resolved part already does. "
            "Individual materials could still differ enough to reverse it.",
        )
    return FlipFactor(
        resolved,
        signed_mass,
        breakeven,
        f"The ranking reverses if the {abs(signed_mass):.4g} kg/FU of unresolved "
        f"material averages more than {breakeven:.4g} kgCO2e/kg. Compare that against "
        "the factors you do have before treating the ranking as settled.",
    )
