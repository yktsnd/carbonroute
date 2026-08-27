"""Deriving factors from production recipes (carbonroute bootstrap).

The values these produce are models, and the tests exist mainly to hold them to
being *honest* models: a floor that follows from the arithmetic, an interval
that never collapses to a point, a citation demanded for every stated number,
and a marker that stops a model being read as a measurement.
"""

import math
from pathlib import Path

import pytest

from carbonroute.bootstrap import (
    DERIVED_MARKER,
    BootstrapError,
    EnergyFactors,
    derive_all,
    interval_to_lognormal,
    is_derived,
    load_recipe,
    load_recipes,
    to_rows,
)
from carbonroute.resolve import FactorTable

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "processes"
ADEME = Path(__file__).resolve().parents[1] / "data" / "factors" / "ademe_base_carbone.csv"
Z90 = 1.6448536269514722


@pytest.fixture()
def table():
    return FactorTable.load([ADEME])


@pytest.fixture()
def derived(table):
    return derive_all(
        load_recipes(FIXTURES),
        table,
        EnergyFactors(grid_kgCO2e_per_kWh=0.4, grid_source="declared for the test"),
        completeness_floor=0.5,
    )


def test_interval_maps_onto_a_lognormal_that_reproduces_it():
    median, gsd = interval_to_lognormal(1.0, 4.0)
    assert median == pytest.approx(2.0)
    assert median / gsd**Z90 == pytest.approx(1.0)
    assert median * gsd**Z90 == pytest.approx(4.0)


def test_the_floor_is_the_arithmetic_and_nothing_else(derived):
    """methanol 2.0 kg stoichiometric / 0.5 yield = 4.0 kg, times 0.521, plus 10 kWh * 0.4."""
    d = derived.derived["cas:67-64-1"]
    assert d.low_kgCO2e_per_kg == pytest.approx(4.0 * 0.521 + 10.0 * 0.4)
    assert d.high_kgCO2e_per_kg == pytest.approx(d.low_kgCO2e_per_kg / 0.5)
    assert d.median_kgCO2e_per_kg == pytest.approx(
        math.sqrt(d.low_kgCO2e_per_kg * d.high_kgCO2e_per_kg)
    )


def test_a_stoichiometric_quantity_is_divided_by_the_yield(derived):
    trace = " ".join(derived.derived["cas:67-64-1"].included)
    assert "methanol: 4 kg/kg" in trace


def test_omitted_terms_are_named_not_dropped(derived):
    omitted = derived.derived["cas:67-64-1"].omitted
    assert any("fuel" in o for o in omitted)
    assert any("recipe-declared gap" in o for o in omitted)


def test_a_recipe_can_consume_another_recipes_product(derived):
    """The table bootstraps itself: downstreamine is priced off widgetol."""
    upstream = derived.derived["cas:67-64-1"]
    downstream = derived.derived["cas:71-43-2"]
    assert downstream.low_kgCO2e_per_kg == pytest.approx(upstream.median_kgCO2e_per_kg)
    assert downstream.depth > upstream.depth
    assert "derived: widgetol" in " ".join(downstream.included)


def test_a_complete_recipe_still_gets_an_interval(tmp_path, table):
    """A model of a plant is not a measurement of one, however complete it looks."""
    (tmp_path / "x.yaml").write_text(
        """
substance: {name: thing, cas: "67-64-1"}
route:
  name: r
  yield: 1.0
  yield_source: {document: fixture}
inputs:
  - {name: methanol, cas: "67-56-1", kg_per_kg_product: 1.0, basis: stated,
     source: {document: fixture}}
energy:
  electricity_kWh_per_kg: 1.0
  electricity_source: {document: fixture}
  fuel_MJ_per_kg: 1.0
  fuel_source: {document: fixture}
gaps: []
""",
        encoding="utf-8",
    )
    result = derive_all(
        load_recipes(tmp_path),
        table,
        EnergyFactors(0.4, "declared", 0.07, "declared"),
        completeness_floor=0.5,
    )
    d = result.derived["cas:67-64-1"]
    assert d.is_complete
    assert d.gsd > 1.0
    assert d.high_kgCO2e_per_kg > d.low_kgCO2e_per_kg


def test_energy_without_a_factor_weakens_the_bound_rather_than_breaking_it(table):
    """Supplying no grid factor is allowed; the term drops out and is reported."""
    result = derive_all(load_recipes(FIXTURES), table, EnergyFactors(), completeness_floor=0.5)
    d = result.derived["cas:67-64-1"]
    assert d.low_kgCO2e_per_kg == pytest.approx(4.0 * 0.521)
    assert any("no grid factor supplied" in o for o in d.omitted)


def test_a_stated_number_without_a_citation_is_rejected(tmp_path):
    (tmp_path / "x.yaml").write_text(
        """
substance: {name: thing, cas: "67-64-1"}
route: {name: r}
inputs:
  - {name: methanol, cas: "67-56-1", kg_per_kg_product: 1.0, basis: stated}
""",
        encoding="utf-8",
    )
    with pytest.raises(BootstrapError, match="source"):
        load_recipes(tmp_path)


def test_an_unsourced_yield_is_rejected(tmp_path):
    (tmp_path / "x.yaml").write_text(
        'substance: {name: t, cas: "67-64-1"}\nroute: {name: r, yield: 0.5}\n', encoding="utf-8"
    )
    with pytest.raises(BootstrapError, match="yield_source"):
        load_recipes(tmp_path)


def test_a_bad_cas_check_digit_is_rejected(tmp_path):
    (tmp_path / "x.yaml").write_text(
        'substance: {name: t, cas: "67-64-2"}\nroute: {name: r}\n', encoding="utf-8"
    )
    with pytest.raises(BootstrapError, match="CAS"):
        load_recipes(tmp_path)


def test_rows_are_marked_as_models_and_load_as_factors(derived, tmp_path):
    rows = to_rows(derived, "2026-08-27", 0.5)
    assert rows and all(r["source"].startswith(DERIVED_MARKER) for r in rows)
    assert all(r["uncertainty_class"] == "structural_estimate" for r in rows)

    out = tmp_path / "derived.csv"
    from carbonroute.bootstrap import write_csv

    write_csv(rows, out)
    table = FactorTable.load([out])
    factor = table.by_key["cas:67-64-1"]
    assert is_derived(factor)
    # The interval survives the round trip through the CSV.
    d = derived.derived["cas:67-64-1"]
    assert factor.gwp_kgCO2e_per_kg == pytest.approx(d.median_kgCO2e_per_kg, rel=1e-12)
    assert factor.gsd == pytest.approx(d.gsd, rel=1e-12)
    assert factor.gwp_kgCO2e_per_kg / factor.gsd**Z90 == pytest.approx(
        d.low_kgCO2e_per_kg, rel=1e-9
    )


def test_derivation_is_deterministic(table):
    a = derive_all(load_recipes(FIXTURES), table, EnergyFactors(0.4, "x"), 0.5)
    b = derive_all(load_recipes(FIXTURES), table, EnergyFactors(0.4, "x"), 0.5)
    assert to_rows(a, "2026-08-27", 0.5) == to_rows(b, "2026-08-27", 0.5)
