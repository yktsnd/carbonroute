"""Ledger loading and conversion to the functional unit (spec section 7.1-7.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import prod
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schema import Assumptions, Ledger, MaterialInput, Role, Route, material_key


class LedgerError(ValueError):
    """Raised for ledgers that are structurally valid YAML but not usable."""


@dataclass(frozen=True)
class MaterialAmount:
    """One material line after conversion to the functional unit."""

    key: str
    name: str
    cas: str | None
    role: Role
    mass_kg: float
    #: Mass before solvent make-up (``mass * (1 - r)``) was applied.
    gross_mass_kg: float
    recovery: float


@dataclass(frozen=True)
class AdjustedRoute:
    """A route expressed per functional unit, ready for emission accounting."""

    name: str
    label: str
    materials: list[MaterialAmount]
    electricity_kWh: float
    step_factors: dict[str, float]
    #: (step id, material key) -> adjusted mass, kept for contribution tables.
    by_step: dict[tuple[str, str], float] = field(default_factory=dict)

    def masses(self) -> dict[str, float]:
        return {m.key: m.mass_kg for m in self.materials}

    def roles(self) -> dict[str, Role]:
        return {m.key: m.role for m in self.materials}

    def names(self) -> dict[str, str]:
        return {m.key: m.name for m in self.materials}


def load_ledger(path: str | Path) -> Ledger:
    """Read and validate a route ledger. Raises :class:`LedgerError` on failure."""
    p = Path(path)
    try:
        raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - message passthrough
        raise LedgerError(f"{p}: could not parse YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise LedgerError(f"{p}: top level of a ledger must be a mapping")
    try:
        return Ledger.model_validate(raw)
    except ValidationError as exc:
        raise LedgerError(f"{p}: {format_validation_error(exc)}") from exc


def format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        lines.append(f"  {loc}: {err['msg']}")
    return "invalid ledger:\n" + "\n".join(lines)


def step_factors(route: Route) -> dict[str, float]:
    """``factor_k = 1 / prod(yield_j for j >= k)`` (spec section 7.1)."""
    yields = [s.yield_ for s in route.steps]
    factors: dict[str, float] = {}
    for k, step in enumerate(route.steps):
        downstream = yields[k:]
        denom = prod(downstream)
        if denom <= 0.0:
            raise LedgerError(
                f"cumulative yield from step {step.id!r} onwards is zero; cannot convert"
            )
        factors[str(step.id)] = 1.0 / denom
    return factors


def _recovery_for(inp: MaterialInput, assumptions: Assumptions) -> float:
    if inp.role != "solvent":
        return 0.0
    if inp.recovery is not None:
        return inp.recovery
    overrides = assumptions.solvent_recovery
    for candidate in (inp.cas, inp.name, material_key(inp.cas, inp.name)):
        if candidate and candidate in overrides:
            return overrides[candidate]
    return assumptions.solvent_recovery_default


def adjust_route(name: str, route: Route, assumptions: Assumptions) -> AdjustedRoute:
    """Convert a route's inventory to the declared functional unit.

    Masses are scaled by the downstream cumulative yield, then solvents are
    reduced to their make-up quantity, then everything is scaled to the
    functional unit mass.
    """
    factors = step_factors(route)
    fu = assumptions.functional_unit.mass_kg

    merged: dict[str, dict[str, Any]] = {}
    by_step: dict[tuple[str, str], float] = {}
    electricity = 0.0

    for step in route.steps:
        f = factors[str(step.id)]
        electricity += step.electricity_kWh * f * fu
        for inp in step.inputs:
            recovery = _recovery_for(inp, assumptions)
            gross = inp.mass_kg * f * fu
            net = gross * (1.0 - recovery)
            key = inp.key
            slot = merged.setdefault(
                key,
                {
                    "name": inp.name,
                    "cas": inp.cas,
                    "role": inp.role,
                    "mass": 0.0,
                    "gross": 0.0,
                    "recovery_weighted": 0.0,
                },
            )
            if slot["role"] != inp.role:
                raise LedgerError(
                    f"material {inp.name!r} appears with conflicting roles "
                    f"({slot['role']} and {inp.role}) in route {name!r}"
                )
            slot["mass"] += net
            slot["gross"] += gross
            slot["recovery_weighted"] += recovery * gross
            by_step[(str(step.id), key)] = by_step.get((str(step.id), key), 0.0) + net

    materials = [
        MaterialAmount(
            key=key,
            name=slot["name"],
            cas=slot["cas"],
            role=slot["role"],
            mass_kg=slot["mass"],
            gross_mass_kg=slot["gross"],
            recovery=(slot["recovery_weighted"] / slot["gross"]) if slot["gross"] else 0.0,
        )
        for key, slot in merged.items()
    ]
    materials.sort(key=lambda m: m.key)

    return AdjustedRoute(
        name=name,
        label=route.label,
        materials=materials,
        electricity_kWh=electricity,
        step_factors=factors,
        by_step=by_step,
    )


def adjust_all(ledger: Ledger) -> dict[str, AdjustedRoute]:
    return {
        name: adjust_route(name, route, ledger.assumptions)
        for name, route in ledger.routes.items()
    }
