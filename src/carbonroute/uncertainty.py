"""Uncertainty model and Monte Carlo comparison statistics (spec section 7.5-7.6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import yaml

from .schema import Assumptions

if TYPE_CHECKING:
    from .compute import DiffResult

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "uncertainty.yaml"


@dataclass(frozen=True)
class UncertaintyModel:
    classes: dict[str, float]  # class name -> GSD
    descriptions: dict[str, str]
    fallback_class: str
    path: str

    def gsd(self, uncertainty_class: str) -> float:
        return self.classes.get(uncertainty_class, self.classes[self.fallback_class])


def load_uncertainty(path: str | Path | None = None) -> UncertaintyModel:
    """Load the GSD-per-provenance-class table (spec section 7.5)."""
    p = Path(path) if path is not None else _DEFAULT_CONFIG
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    classes_raw = raw["classes"]
    classes = {name: float(entry["gsd"]) for name, entry in classes_raw.items()}
    descriptions = {name: str(entry.get("description", "")) for name, entry in classes_raw.items()}
    fallback = raw["fallback_class"]
    if fallback not in classes:
        raise ValueError(f"{p}: fallback_class {fallback!r} is not a listed class")
    return UncertaintyModel(
        classes=classes, descriptions=descriptions, fallback_class=fallback, path=str(p)
    )


@dataclass(frozen=True)
class ComparisonStats:
    p_a_lower: float  # P(GWP_A < GWP_B)
    verdict: str  # "A<B" | "B<A" | "indeterminate"
    delta_median: float  # median of GWP_A - GWP_B, kgCO2e
    delta_p05: float
    delta_p95: float
    median_a: float
    median_b: float
    iterations: int
    seed: int
    excluded_keys: list[str]  # delta materials left out (unresolved)


def compare_monte_carlo(
    diff: DiffResult,
    assumptions: Assumptions,
    model: UncertaintyModel,
    iterations: int,
    seed: int,
) -> ComparisonStats:
    """Monte Carlo comparison of two routes via the DeltaLCA construction.

    One factor draw per material key is applied to the mass *difference*, so a
    material with equal adjusted mass in both routes contributes an exact zero
    regardless of its uncertainty (arXiv:2311.09611). Rows are visited in
    sorted key order so the same seed always reproduces the same draws.
    """
    rng = np.random.default_rng(seed)
    total = np.zeros(iterations, dtype=np.float64)
    excluded: list[str] = []

    for row in sorted(diff.rows, key=lambda r: r.key):
        if not row.resolved or row.factor is None:
            excluded.append(row.key)
            continue
        gsd = model.gsd(row.factor.uncertainty_class)
        if gsd == 1.0:
            g = np.full(iterations, row.factor.gwp_kgCO2e_per_kg)
        else:
            sigma = np.log(gsd)
            z = rng.standard_normal(iterations)
            g = row.factor.gwp_kgCO2e_per_kg * np.exp(sigma * z)
        total += row.delta_mass_kg * g

    grid = assumptions.grid_factor
    grid_gsd = model.gsd(grid.uncertainty_class)
    if grid_gsd == 1.0:
        grid_g = np.full(iterations, grid.value_kgCO2e_per_kWh)
    else:
        sigma = np.log(grid_gsd)
        z = rng.standard_normal(iterations)
        grid_g = grid.value_kgCO2e_per_kWh * np.exp(sigma * z)
    total += diff.delta_electricity_kWh * grid_g

    p_a_lower = float(np.mean(total < 0))
    band = assumptions.indeterminate_band
    if band.low <= p_a_lower <= band.high:
        verdict = "indeterminate"
    elif p_a_lower > 0.5:
        verdict = "A<B"
    else:
        verdict = "B<A"

    delta_median = float(np.median(total))
    delta_p05 = float(np.percentile(total, 5))
    delta_p95 = float(np.percentile(total, 95))

    return ComparisonStats(
        p_a_lower=p_a_lower,
        verdict=verdict,
        delta_median=delta_median,
        delta_p05=delta_p05,
        delta_p95=delta_p95,
        # Filled in by run_comparison, which has the RouteResults; see compute.py.
        median_a=0.0,
        median_b=0.0,
        iterations=iterations,
        seed=seed,
        excluded_keys=sorted(excluded),
    )
