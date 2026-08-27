"""Derive factors for substances no open database covers.

The values a process chemist needs — THF, dichloromethane, acetonitrile — are
not absent because nobody measured them. They sit inside commercially licensed
databases this project may not redistribute. Looking harder does not fix that.

So instead of looking a substance up, this module *computes* it, from the same
kind of description the tool already understands: what goes in, how much energy
it takes, and what comes out. A production recipe in ``data/processes`` plus the
factors already in hand yields a factor for the product, which can in turn feed
the next recipe. The tool bootstraps its own factor table.

Two properties keep this honest.

**Every derived value is a lower bound first.** Each term in the sum is
non-negative, so omitting one — an unsourced energy figure, a minor reagent, a
feedstock with no factor of its own — can only make the result too small, never
too large. What comes out is therefore a floor that follows from the data,
before it is anything else.

**A floor is published as an interval, not as a number.** The floor becomes the
low end; the high end is the floor divided by a declared completeness fraction.
That interval is then carried through the existing machinery as a lognormal
whose 90% range reproduces it exactly, so a derived factor is wide by
construction and can never pass for a measurement. The completeness fraction is
an assumption, declared as one, and the report says which factors were modelled.

This is the mechanism the specification anticipated in section 15.1, where
estimated values are kept in their own provenance class and given generous
uncertainty. Nothing here is recalled or guessed: a recipe carries a citation
for every number it states, and arithmetic does the rest.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .resolve import Factor, FactorTable
from .schema import cas_checksum_ok, material_key, normalize_name

#: Marker on the ``source`` column of a derived row, the counterpart of
#: ILLUSTRATIVE. Reports call these out so a model is never read as a
#: measurement.
DERIVED_MARKER = "DERIVED"

#: Half-width of a lognormal's 90% interval, in units of log(GSD).
_Z90 = 1.6448536269514722


class BootstrapError(ValueError):
    pass


@dataclass(frozen=True)
class Citation:
    document: str
    url: str
    locator: str

    def render(self) -> str:
        parts = [p for p in (self.document, self.locator, self.url) if p]
        return " | ".join(parts)

    @classmethod
    def parse(cls, raw: Any, where: str) -> "Citation":
        if not isinstance(raw, dict):
            raise BootstrapError(f"{where}: expected a source mapping, got {type(raw).__name__}")
        document = str(raw.get("document", "")).strip()
        if not document:
            raise BootstrapError(f"{where}: every stated number needs a source document")
        return cls(document, str(raw.get("url", "")).strip(), str(raw.get("locator", "")).strip())


@dataclass(frozen=True)
class RecipeInput:
    name: str
    cas: str | None
    kg_per_kg_product: float
    #: "stated" means the figure already reflects real plant losses; the yield
    #: has been applied by the source. "stoichiometric" means it is theory, and
    #: the yield still has to divide it.
    basis: str
    source: Citation | None

    @property
    def key(self) -> str:
        return material_key(self.cas, self.name)


@dataclass(frozen=True)
class Energy:
    electricity_kWh_per_kg: float | None = None
    electricity_source: Citation | None = None
    fuel_MJ_per_kg: float | None = None
    fuel_source: Citation | None = None


@dataclass(frozen=True)
class ProcessRecipe:
    name: str
    cas: str | None
    inchikey: str
    route_name: str
    route_description: str
    yield_: float | None
    yield_source: Citation | None
    inputs: list[RecipeInput]
    energy: Energy
    notes: str
    gaps: list[str]
    path: str

    @property
    def key(self) -> str:
        return material_key(self.cas, self.name)


@dataclass(frozen=True)
class EnergyFactors:
    """Declared emission factors for the energy a process consumes.

    Supplying neither is legitimate: the energy terms drop out and the bound
    simply gets weaker, which the output records rather than hides.
    """

    grid_kgCO2e_per_kWh: float | None = None
    grid_source: str = ""
    fuel_kgCO2e_per_MJ: float | None = None
    fuel_source: str = ""


@dataclass(frozen=True)
class DerivedFactor:
    key: str
    name: str
    cas: str | None
    inchikey: str
    #: The rigorous floor: the sum of every term that could be evaluated.
    low_kgCO2e_per_kg: float
    high_kgCO2e_per_kg: float
    median_kgCO2e_per_kg: float
    gsd: float
    included: list[str]
    omitted: list[str]
    recipe: ProcessRecipe
    depth: int

    @property
    def is_complete(self) -> bool:
        return not self.omitted


@dataclass
class BootstrapResult:
    derived: dict[str, DerivedFactor] = field(default_factory=dict)
    #: substance key -> why nothing could be derived for it
    skipped: dict[str, str] = field(default_factory=dict)


def _f(raw: Any) -> float | None:
    if raw is None:
        return None
    return float(raw)


def load_recipe(path: str | Path) -> ProcessRecipe:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BootstrapError(f"{p}: a process recipe must be a mapping")

    substance = raw.get("substance") or {}
    name = str(substance.get("name", "")).strip()
    if not name:
        raise BootstrapError(f"{p}: substance.name is required")
    cas = substance.get("cas")
    cas = str(cas).strip() if cas else None
    if cas and not cas_checksum_ok(cas):
        raise BootstrapError(f"{p}: invalid CAS check digit: {cas!r}")

    route = raw.get("route") or {}
    yield_raw = route.get("yield")
    yield_ = _f(yield_raw)
    if yield_ is not None and not (0.0 < yield_ <= 1.0):
        raise BootstrapError(f"{p}: route.yield must be in (0, 1], got {yield_}")
    yield_source = (
        Citation.parse(route["yield_source"], f"{p}: route.yield_source")
        if yield_ is not None and route.get("yield_source")
        else None
    )
    if yield_ is not None and yield_source is None:
        raise BootstrapError(f"{p}: route.yield is stated without route.yield_source")

    inputs = []
    for i, item in enumerate(raw.get("inputs") or []):
        where = f"{p}: inputs[{i}]"
        basis = str(item.get("basis", "")).strip()
        if basis not in {"stated", "stoichiometric"}:
            raise BootstrapError(f"{where}: basis must be 'stated' or 'stoichiometric'")
        amount = _f(item.get("kg_per_kg_product"))
        if amount is None or amount < 0:
            raise BootstrapError(f"{where}: kg_per_kg_product must be a non-negative number")
        source = Citation.parse(item["source"], where) if item.get("source") else None
        if basis == "stated" and source is None:
            raise BootstrapError(f"{where}: a stated quantity needs a source")
        item_cas = item.get("cas")
        item_cas = str(item_cas).strip() if item_cas else None
        if item_cas and not cas_checksum_ok(item_cas):
            raise BootstrapError(f"{where}: invalid CAS check digit: {item_cas!r}")
        inputs.append(
            RecipeInput(str(item.get("name", "")).strip(), item_cas, amount, basis, source)
        )

    energy_raw = raw.get("energy") or {}
    elec = _f(energy_raw.get("electricity_kWh_per_kg"))
    fuel = _f(energy_raw.get("fuel_MJ_per_kg"))
    energy = Energy(
        electricity_kWh_per_kg=elec,
        electricity_source=(
            Citation.parse(energy_raw["electricity_source"], f"{p}: energy.electricity_source")
            if elec is not None and energy_raw.get("electricity_source")
            else None
        ),
        fuel_MJ_per_kg=fuel,
        fuel_source=(
            Citation.parse(energy_raw["fuel_source"], f"{p}: energy.fuel_source")
            if fuel is not None and energy_raw.get("fuel_source")
            else None
        ),
    )
    if elec is not None and energy.electricity_source is None:
        raise BootstrapError(f"{p}: energy.electricity_kWh_per_kg is stated without a source")
    if fuel is not None and energy.fuel_source is None:
        raise BootstrapError(f"{p}: energy.fuel_MJ_per_kg is stated without a source")

    return ProcessRecipe(
        name=name,
        cas=cas,
        inchikey=str(substance.get("inchikey", "")).strip().upper(),
        route_name=str(route.get("name", "")).strip(),
        route_description=str(route.get("description", "")).strip(),
        yield_=yield_,
        yield_source=yield_source,
        inputs=inputs,
        energy=energy,
        notes=str(raw.get("notes", "")).strip(),
        gaps=[str(g) for g in (raw.get("gaps") or [])],
        path=str(p),
    )


def load_recipes(directory: str | Path) -> dict[str, ProcessRecipe]:
    d = Path(directory)
    if not d.is_dir():
        raise BootstrapError(f"{d}: not a directory")
    recipes: dict[str, ProcessRecipe] = {}
    for path in sorted(d.glob("*.yaml")):
        recipe = load_recipe(path)
        if recipe.key in recipes:
            raise BootstrapError(
                f"{path}: {recipe.key} is already defined by {recipes[recipe.key].path}"
            )
        recipes[recipe.key] = recipe
    return recipes


def interval_to_lognormal(low: float, high: float) -> tuple[float, float]:
    """Express an interval as the lognormal whose 90% range reproduces it.

    Keeps derived factors inside the machinery every other factor already uses,
    instead of bolting a second representation onto the Monte Carlo.
    """
    if low <= 0 or high < low:
        raise BootstrapError(f"cannot map interval [{low}, {high}] onto a lognormal")
    if high == low:
        return low, 1.0
    median = math.sqrt(low * high)
    gsd = math.exp(math.log(high / low) / (2 * _Z90))
    return median, gsd


def _lookup(key: str, name: str, table: FactorTable, derived: dict[str, DerivedFactor]):
    if key in derived:
        return derived[key].median_kgCO2e_per_kg, derived[key].name, True
    hit = table.lookup(key, name)
    if hit.resolved and hit.factor is not None:
        return hit.factor.gwp_kgCO2e_per_kg, hit.factor.name, False
    return None, name, False


def derive_all(
    recipes: dict[str, ProcessRecipe],
    table: FactorTable,
    energy: EnergyFactors,
    completeness_floor: float = 0.5,
    max_passes: int | None = None,
) -> BootstrapResult:
    """Derive every recipe that can be derived, resolving dependencies in order.

    A recipe whose feedstock is itself a recipe is held back until that one is
    done. Repeated passes settle the order without needing an explicit graph;
    a recipe that never becomes derivable is reported, not silently dropped.
    """
    if not (0.0 < completeness_floor <= 1.0):
        raise BootstrapError("completeness_floor must be in (0, 1]")

    result = BootstrapResult()
    pending = dict(recipes)
    passes = max_passes if max_passes is not None else len(recipes) + 1
    depth = 0

    while pending and passes > 0:
        passes -= 1
        ready = [
            key
            for key, recipe in pending.items()
            if not any(
                inp.key in pending and inp.key != key for inp in recipe.inputs
            )
        ]
        if not ready:
            break
        for key in sorted(ready):
            recipe = pending.pop(key)
            factor = _derive_one(recipe, table, result.derived, energy, completeness_floor, depth)
            if isinstance(factor, str):
                result.skipped[key] = factor
            else:
                result.derived[key] = factor
        depth += 1

    for key, recipe in pending.items():
        result.skipped[key] = (
            "circular or unresolvable dependency between recipes; "
            f"inputs: {', '.join(i.key for i in recipe.inputs)}"
        )
    return result


def _derive_one(
    recipe: ProcessRecipe,
    table: FactorTable,
    derived: dict[str, DerivedFactor],
    energy: EnergyFactors,
    completeness_floor: float,
    depth: int,
) -> DerivedFactor | str:
    included: list[str] = []
    omitted: list[str] = []
    floor = 0.0

    for inp in recipe.inputs:
        amount = inp.kg_per_kg_product
        if inp.basis == "stoichiometric":
            if recipe.yield_ is None:
                omitted.append(
                    f"{inp.name}: stoichiometric quantity with no sourced yield to divide by; "
                    "counted at theoretical demand, which understates it"
                )
            else:
                amount = amount / recipe.yield_
        value, matched_name, from_derived = _lookup(inp.key, inp.name, table, derived)
        if value is None:
            omitted.append(f"{inp.name} ({inp.key}): no factor available")
            continue
        contribution = amount * value
        floor += contribution
        origin = "derived" if from_derived else "table"
        included.append(
            f"{inp.name}: {amount:.6g} kg/kg x {value:.6g} kgCO2e/kg "
            f"= {contribution:.6g} ({origin}: {matched_name})"
        )

    e = recipe.energy
    if e.electricity_kWh_per_kg is None:
        omitted.append("process electricity: not stated in the recipe")
    elif energy.grid_kgCO2e_per_kWh is None:
        omitted.append("process electricity: no grid factor supplied to bootstrap")
    else:
        contribution = e.electricity_kWh_per_kg * energy.grid_kgCO2e_per_kWh
        floor += contribution
        included.append(
            f"electricity: {e.electricity_kWh_per_kg:.6g} kWh/kg x "
            f"{energy.grid_kgCO2e_per_kWh:.6g} = {contribution:.6g}"
        )

    if e.fuel_MJ_per_kg is None:
        omitted.append("process fuel/steam: not stated in the recipe")
    elif energy.fuel_kgCO2e_per_MJ is None:
        omitted.append("process fuel/steam: no fuel factor supplied to bootstrap")
    else:
        contribution = e.fuel_MJ_per_kg * energy.fuel_kgCO2e_per_MJ
        floor += contribution
        included.append(
            f"fuel: {e.fuel_MJ_per_kg:.6g} MJ/kg x "
            f"{energy.fuel_kgCO2e_per_MJ:.6g} = {contribution:.6g}"
        )

    omitted.extend(f"recipe-declared gap: {g}" for g in recipe.gaps)

    if floor <= 0.0:
        return (
            "nothing could be evaluated: no feedstock resolved to a factor and no "
            "energy term was usable, so there is no floor to report"
        )

    # The completeness floor applies even when nothing was omitted. A recipe
    # that states every term is still a model of a plant, not a measurement of
    # one, and handing back a zero-width interval would dress it up as one.
    high = floor / completeness_floor
    median, gsd = interval_to_lognormal(floor, high)
    return DerivedFactor(
        key=recipe.key,
        name=recipe.name,
        cas=recipe.cas,
        inchikey=recipe.inchikey,
        low_kgCO2e_per_kg=floor,
        high_kgCO2e_per_kg=high,
        median_kgCO2e_per_kg=median,
        gsd=gsd,
        included=included,
        omitted=omitted,
        recipe=recipe,
        depth=depth,
    )


CSV_COLUMNS = (
    "identifier",
    "name",
    "gwp_kgCO2e_per_kg",
    "source",
    "database_version",
    "region",
    "retrieved_date",
    "uncertainty_class",
    "license",
    "notes",
    "inchikey",
    "gsd",
)


def to_rows(result: BootstrapResult, retrieved_date: str, completeness_floor: float) -> list[dict]:
    rows = []
    for key in sorted(result.derived):
        d = result.derived[key]
        if not d.cas and not d.inchikey:
            continue  # the loader keys on an identifier; a bare name cannot be a row
        completeness = (
            "complete (no term omitted)"
            if d.is_complete
            else f"lower bound; {len(d.omitted)} term(s) omitted"
        )
        notes = (
            f"Derived by carbonroute bootstrap from {Path(d.recipe.path).name}. "
            f"Route: {d.recipe.route_name or 'unstated'}. "
            f"Floor {d.low_kgCO2e_per_kg:.6g}, upper {d.high_kgCO2e_per_kg:.6g} kgCO2e/kg "
            f"(completeness floor {completeness_floor}); {completeness}. "
            f"Median and gsd reproduce that interval as a lognormal 90% range. "
            f"Included: {'; '.join(d.included)}. "
            f"Omitted: {'; '.join(d.omitted) if d.omitted else 'none'}."
        )
        rows.append(
            {
                "identifier": d.cas or d.inchikey,
                "name": d.name,
                "gwp_kgCO2e_per_kg": repr(d.median_kgCO2e_per_kg),
                "source": f"{DERIVED_MARKER} by carbonroute bootstrap from {d.recipe.path}",
                "database_version": "bootstrap/0.1",
                "region": "GLO",
                "retrieved_date": retrieved_date,
                "uncertainty_class": "structural_estimate",
                "license": "derived work; see the recipe for each input's licence",
                "notes": notes,
                "inchikey": d.inchikey,
                "gsd": repr(d.gsd),
            }
        )
    return rows


def write_csv(rows: list[dict], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def is_derived(factor: Factor) -> bool:
    return factor.source.strip().upper().startswith(DERIVED_MARKER)
