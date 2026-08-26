"""Reversal-threshold search over key assumptions (spec section 7.7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .compute import diff_routes
from .ledger import adjust_route
from .resolve import FactorTable, resolve_materials
from .schema import Ledger
from .uncertainty import UncertaintyModel, compare_monte_carlo

_BISECT_MAX_ITER = 30
_BISECT_TOL = 1e-4


@dataclass(frozen=True)
class Threshold:
    variable: str  # e.g. "solvent_recovery_default", "grid_factor", "yield:legacy:1"
    label: str  # human-readable
    low: float
    high: float  # range searched
    baseline: float  # current value
    crossing: float | None  # value where P crosses 0.5, None if no crossing
    p_at_low: float
    p_at_high: float
    message: str


def _bisect(f: Callable[[float], float], low: float, high: float) -> tuple[float | None, float, float]:
    """Bisect for P == 0.5 in [low, high]. Returns (crossing, p_low, p_high)."""
    p_low = f(low)
    p_high = f(high)
    if (p_low - 0.5) * (p_high - 0.5) > 0.0:
        return None, p_low, p_high  # both endpoints on the same side: no crossing

    lo, hi, p_lo = low, high, p_low
    for _ in range(_BISECT_MAX_ITER):
        if hi - lo <= _BISECT_TOL:
            break
        mid = (lo + hi) / 2.0
        p_mid = f(mid)
        if (p_lo - 0.5) * (p_mid - 0.5) <= 0.0:
            hi = mid
        else:
            lo, p_lo = mid, p_mid
    return (lo + hi) / 2.0, p_low, p_high


def _threshold(
    variable: str,
    label: str,
    low: float,
    high: float,
    baseline: float,
    evaluate: Callable[[float], float],
) -> Threshold:
    crossing, p_low, p_high = _bisect(evaluate, low, high)
    if crossing is None:
        side = "A<B" if p_low > 0.5 else ("B<A" if p_low < 0.5 else "indeterminate")
        message = (
            f"Ranking does not change over [{low:g}, {high:g}] for {variable}; "
            f"stays {side} (P ranges {min(p_low, p_high):.3f}-{max(p_low, p_high):.3f})."
        )
    else:
        message = (
            f"P(GWP_A<GWP_B) crosses 0.5 near {variable}={crossing:.4g} "
            f"(baseline {baseline:.4g})."
        )
    return Threshold(
        variable=variable,
        label=label,
        low=low,
        high=high,
        baseline=baseline,
        crossing=crossing,
        p_at_low=p_low,
        p_at_high=p_high,
        message=message,
    )


def reversal_thresholds(
    ledger: Ledger,
    a_name: str,
    b_name: str,
    table: FactorTable,
    model: UncertaintyModel,
    iterations: int = 2000,
    seed: int | None = None,
) -> list[Threshold]:
    try:
        route_a = ledger.routes[a_name]
        route_b = ledger.routes[b_name]
    except KeyError as exc:
        raise ValueError(f"unknown route name: {exc}") from exc

    use_seed = seed if seed is not None else ledger.assumptions.monte_carlo.seed

    # Resolutions are keyed by material identity, which none of the scanned
    # variables change (only masses/factors), so they are computed once.
    base_a = adjust_route(a_name, route_a, ledger.assumptions)
    base_b = adjust_route(b_name, route_b, ledger.assumptions)
    resolutions = resolve_materials(list(base_a.materials) + list(base_b.materials), table)

    def p_for(modified: Ledger) -> float:
        adjusted_a = adjust_route(a_name, modified.routes[a_name], modified.assumptions)
        adjusted_b = adjust_route(b_name, modified.routes[b_name], modified.assumptions)
        diff = diff_routes(adjusted_a, adjusted_b, resolutions)
        stats = compare_monte_carlo(diff, modified.assumptions, model, iterations, use_seed)
        return stats.p_a_lower

    thresholds: list[Threshold] = []

    # 1. Default solvent recovery rate.
    baseline_recovery = ledger.assumptions.solvent_recovery_default

    def eval_recovery(v: float) -> float:
        new_assumptions = ledger.assumptions.model_copy(update={"solvent_recovery_default": v})
        return p_for(ledger.model_copy(update={"assumptions": new_assumptions}))

    thresholds.append(
        _threshold(
            "solvent_recovery_default",
            "Default solvent recovery rate",
            0.0,
            0.95,
            baseline_recovery,
            eval_recovery,
        )
    )

    # 2. Grid electricity factor.
    baseline_grid = ledger.assumptions.grid_factor.value_kgCO2e_per_kWh
    grid_high = max(1.0, 2.0 * baseline_grid)

    def eval_grid(v: float) -> float:
        new_grid = ledger.assumptions.grid_factor.model_copy(update={"value_kgCO2e_per_kWh": v})
        new_assumptions = ledger.assumptions.model_copy(update={"grid_factor": new_grid})
        return p_for(ledger.model_copy(update={"assumptions": new_assumptions}))

    thresholds.append(
        _threshold(
            "grid_factor",
            f"Grid electricity factor ({ledger.assumptions.grid_factor.id})",
            0.0,
            grid_high,
            baseline_grid,
            eval_grid,
        )
    )

    # 3. Each step yield of both routes.
    for route_name, route in ((a_name, route_a), (b_name, route_b)):
        for idx, step in enumerate(route.steps):
            baseline_yield = step.yield_

            def eval_yield(v: float, route_name=route_name, idx=idx) -> float:
                target_route = ledger.routes[route_name]
                new_steps = list(target_route.steps)
                new_steps[idx] = new_steps[idx].model_copy(update={"yield_": v})
                new_route = target_route.model_copy(update={"steps": new_steps})
                new_routes = dict(ledger.routes)
                new_routes[route_name] = new_route
                return p_for(ledger.model_copy(update={"routes": new_routes}))

            thresholds.append(
                _threshold(
                    f"yield:{route_name}:{step.id}",
                    f"Yield of step {step.id} in route {route_name!r} ({route.label})",
                    0.05,
                    1.0,
                    baseline_yield,
                    eval_yield,
                )
            )

    return thresholds
