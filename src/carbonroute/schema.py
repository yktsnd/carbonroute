"""Pydantic models for the route ledger (spec section 6.1).

Everything a human decides lives in ``assumptions``. Everything else in this
package is deterministic: the same ledger plus the same factor tables always
produce the same numbers.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "0.1"

Role = Literal["solvent", "reactant", "reagent", "catalyst", "auxiliary"]

_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def normalize_name(name: str) -> str:
    """Lower-cased, whitespace-collapsed name used as a fallback join key."""
    return re.sub(r"\s+", " ", name).strip().lower()


def cas_checksum_ok(cas: str) -> bool:
    """CAS registry numbers carry a mod-10 check digit; verify it."""
    if not _CAS_RE.match(cas):
        return False
    digits = cas.replace("-", "")
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * i for i, d in enumerate(reversed(body), start=1))
    return total % 10 == check


def material_key(cas: str | None, name: str) -> str:
    """Primary key for a material.

    CAS wins when present, because names drift between ledgers. Anything
    without a CAS falls back to a normalized name, which is explicitly a
    weaker key and is reported as such by the resolver.
    """
    if cas:
        return f"cas:{cas.strip()}"
    return f"name:{normalize_name(name)}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FunctionalUnit(StrictModel):
    mass_kg: Annotated[float, Field(gt=0)] = 1.0
    basis: Literal["product"] = "product"


class GridFactor(StrictModel):
    id: str
    value_kgCO2e_per_kWh: Annotated[float, Field(ge=0)]
    source: Annotated[str, Field(min_length=1)]
    uncertainty_class: str = "assumption"


class GWPMethod(StrictModel):
    name: str
    horizon_years: Annotated[int, Field(gt=0)] = 100
    feedbacks: bool = False


class MonteCarloSettings(StrictModel):
    # Provisional default (spec section 7.5 / 14). See docs/convergence.md.
    iterations: Annotated[int, Field(ge=100)] = 10_000
    seed: int = 20240101


class IndeterminateBand(StrictModel):
    """Range of P(GWP_A < GWP_B) in which no ranking is reported.

    The 0.4-0.6 default has no empirical basis; it is a convention this tool
    adopts so that near-ties are never dressed up as conclusions.
    """

    low: Annotated[float, Field(ge=0.0, le=1.0)] = 0.4
    high: Annotated[float, Field(ge=0.0, le=1.0)] = 0.6

    @model_validator(mode="after")
    def _ordered(self) -> "IndeterminateBand":
        if self.low > self.high:
            raise ValueError("indeterminate_band.low must not exceed .high")
        return self


class Assumptions(StrictModel):
    functional_unit: FunctionalUnit = Field(default_factory=FunctionalUnit)
    boundary: Literal["cradle-to-gate"] = "cradle-to-gate"
    grid_factor: GridFactor
    gwp_method: GWPMethod
    solvent_recovery_default: Annotated[float, Field(ge=0.0, lt=1.0)] = 0.0
    #: Per-material override, keyed by CAS or by material name.
    solvent_recovery: dict[str, Annotated[float, Field(ge=0.0, lt=1.0)]] = Field(
        default_factory=dict
    )
    waste_treatment: Literal["excluded"] = "excluded"
    monte_carlo: MonteCarloSettings = Field(default_factory=MonteCarloSettings)
    indeterminate_band: IndeterminateBand = Field(default_factory=IndeterminateBand)


class MaterialInput(StrictModel):
    name: Annotated[str, Field(min_length=1)]
    cas: str | None = None
    mass_kg: Annotated[float, Field(ge=0)]
    role: Role
    #: Overrides ``assumptions.solvent_recovery`` for this line. Solvents only.
    recovery: Annotated[float, Field(ge=0.0, lt=1.0)] | None = None

    @field_validator("cas")
    @classmethod
    def _check_cas(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not cas_checksum_ok(v):
            raise ValueError(f"invalid CAS registry number: {v!r}")
        return v

    @model_validator(mode="after")
    def _recovery_only_for_solvents(self) -> "MaterialInput":
        if self.recovery is not None and self.role != "solvent":
            raise ValueError("recovery may only be set on inputs with role=solvent")
        return self

    @property
    def key(self) -> str:
        return material_key(self.cas, self.name)


class Step(StrictModel):
    id: int | str
    yield_: Annotated[float, Field(gt=0.0, le=1.0)] = Field(alias="yield")
    inputs: list[MaterialInput] = Field(default_factory=list)
    electricity_kWh: Annotated[float, Field(ge=0)] = 0.0


class Route(StrictModel):
    label: str
    steps: list[Step] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_step_ids(self) -> "Route":
        ids = [str(s.id) for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique within a route")
        return self


class Ledger(StrictModel):
    schema_version: str
    assumptions: Assumptions
    routes: dict[str, Route] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {v!r}; this build understands {SCHEMA_VERSION!r}"
            )
        return v

    @model_validator(mode="after")
    def _linear_routes_only(self) -> "Ledger":
        # v0 is linear routes only (spec section 5.2). Convergent routes would
        # need a step graph; the flat step list cannot express one, so there is
        # nothing to detect here beyond keeping the restriction documented.
        return self
