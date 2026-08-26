"""Functional-unit conversion and solvent make-up (spec sections 7.1-7.2)."""

import textwrap

import pytest

from carbonroute.ledger import LedgerError, adjust_all, adjust_route, load_ledger, step_factors

REL = 1e-12


def _write(tmp_path, body):
    p = tmp_path / "ledger.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


BASE_ASSUMPTIONS = """\
    schema_version: "0.1"
    assumptions:
      grid_factor: {id: T, value_kgCO2e_per_kWh: 0.5, source: fixture}
      gwp_method: {name: IPCC-AR6, horizon_years: 100, feedbacks: false}
"""


def test_step_factors_are_downstream_cumulative_yield(analytic_ledger):
    a = step_factors(analytic_ledger.routes["a"])
    assert a["1"] == pytest.approx(1 / (0.5 * 0.8), rel=REL)
    assert a["2"] == pytest.approx(1 / 0.8, rel=REL)


def test_adjusted_masses_match_hand_calculation(analytic_ledger):
    routes = adjust_all(analytic_ledger)
    a = routes["a"].masses()
    b = routes["b"].masses()
    assert a["cas:71-43-2"] == pytest.approx(5.0, rel=REL)
    assert a["cas:108-88-3"] == pytest.approx(10.0, rel=REL)
    assert a["cas:67-64-1"] == pytest.approx(1.25, rel=REL)
    assert a["name:novel ligand z"] == pytest.approx(0.5, rel=REL)
    assert b["cas:71-43-2"] == pytest.approx(5.0, rel=REL)
    assert b["cas:96-47-9"] == pytest.approx(2.5, rel=REL)
    # Shared lines must land on exactly the same number, or nothing cancels.
    assert a["cas:71-43-2"] == b["cas:71-43-2"]
    assert a["cas:67-64-1"] == b["cas:67-64-1"]
    assert routes["a"].electricity_kWh == routes["b"].electricity_kWh == 25.0


def test_functional_unit_scales_linearly(analytic_ledger):
    scaled = analytic_ledger.model_copy(deep=True)
    scaled.assumptions.functional_unit.mass_kg = 3.0
    before = adjust_route("a", analytic_ledger.routes["a"], analytic_ledger.assumptions)
    after = adjust_route("a", scaled.routes["a"], scaled.assumptions)
    for key, mass in before.masses().items():
        assert after.masses()[key] == pytest.approx(3.0 * mass, rel=REL)
    assert after.electricity_kWh == pytest.approx(3.0 * before.electricity_kWh, rel=REL)


def test_solvent_recovery_reduces_to_make_up_only(analytic_ledger):
    led = analytic_ledger.model_copy(deep=True)
    led.assumptions.solvent_recovery_default = 0.75
    adjusted = adjust_route("a", led.routes["a"], led.assumptions)
    toluene = adjusted.masses()["cas:108-88-3"]
    assert toluene == pytest.approx(10.0 * 0.25, rel=REL)
    # A reactant is untouched by a solvent recovery assumption.
    assert adjusted.masses()["cas:71-43-2"] == pytest.approx(5.0, rel=REL)


def test_per_material_recovery_overrides_default(analytic_ledger):
    led = analytic_ledger.model_copy(deep=True)
    led.assumptions.solvent_recovery_default = 0.5
    led.assumptions.solvent_recovery = {"108-88-3": 0.9}
    adjusted = adjust_route("a", led.routes["a"], led.assumptions)
    assert adjusted.masses()["cas:108-88-3"] == pytest.approx(10.0 * 0.1, rel=REL)


def test_zero_yield_is_an_error_not_a_number(tmp_path):
    p = _write(tmp_path, BASE_ASSUMPTIONS + """\
    routes:
      a:
        label: x
        steps:
          - {id: 1, yield: 0.0, inputs: [], electricity_kWh: 1.0}
    """)
    with pytest.raises(LedgerError):
        load_ledger(p)


def test_conflicting_roles_for_one_material_are_rejected(tmp_path):
    p = _write(tmp_path, BASE_ASSUMPTIONS + """\
    routes:
      a:
        label: x
        steps:
          - id: 1
            yield: 1.0
            inputs: [{name: toluene, cas: "108-88-3", mass_kg: 1.0, role: solvent}]
          - id: 2
            yield: 1.0
            inputs: [{name: toluene, cas: "108-88-3", mass_kg: 1.0, role: reactant}]
    """)
    led = load_ledger(p)
    with pytest.raises(LedgerError):
        adjust_route("a", led.routes["a"], led.assumptions)


def test_same_material_across_steps_is_merged(tmp_path):
    p = _write(tmp_path, BASE_ASSUMPTIONS + """\
    routes:
      a:
        label: x
        steps:
          - id: 1
            yield: 0.5
            inputs: [{name: toluene, cas: "108-88-3", mass_kg: 1.0, role: solvent}]
          - id: 2
            yield: 1.0
            inputs: [{name: Toluene, cas: "108-88-3", mass_kg: 2.0, role: solvent}]
    """)
    led = load_ledger(p)
    adjusted = adjust_route("a", led.routes["a"], led.assumptions)
    assert adjusted.masses() == pytest.approx({"cas:108-88-3": 1.0 / 0.5 + 2.0}, rel=REL)


def test_malformed_yaml_reports_the_file(tmp_path):
    p = tmp_path / "broken.yaml"
    p.write_text("schema_version: [unclosed\n", encoding="utf-8")
    with pytest.raises(LedgerError) as exc:
        load_ledger(p)
    assert "broken.yaml" in str(exc.value)
