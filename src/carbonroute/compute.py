"""Emission accounting, route diffing, and top-level comparison (spec section 7.3-7.4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import AdjustedRoute, adjust_route
from .resolve import Factor, FactorTable, Resolution, resolve_materials
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
    # median_a/median_b are the deterministic resolved totals, not MC outputs;
    # compare_monte_carlo only sees the diff, so fill them in here.
    stats = ComparisonStats(
        p_a_lower=stats.p_a_lower,
        verdict=stats.verdict,
        delta_median=stats.delta_median,
        delta_p05=stats.delta_p05,
        delta_p95=stats.delta_p95,
        median_a=result_a.total_kgCO2e,
        median_b=result_b.total_kgCO2e,
        iterations=stats.iterations,
        seed=stats.seed,
        excluded_keys=stats.excluded_keys,
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
        resolutions=resolutions,
    )
