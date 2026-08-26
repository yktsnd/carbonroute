"""Emission accounting and the delta set (spec sections 7.3-7.4)."""

import pytest

from carbonroute.compute import diff_routes, route_result, run_comparison
from carbonroute.ledger import adjust_all
from carbonroute.resolve import resolve_materials

REL = 1e-12


@pytest.fixture()
def results(analytic_ledger, analytic_table):
    adjusted = adjust_all(analytic_ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, analytic_table))
    return adjusted, resolutions, analytic_ledger.assumptions


def test_route_totals_match_hand_calculation(results):
    adjusted, resolutions, assumptions = results
    a = route_result(adjusted["a"], resolutions, assumptions)
    b = route_result(adjusted["b"], resolutions, assumptions)
    # benzene 5.0*7 + toluene 10.0*1 = 45; electricity 25 kWh * 0.5 = 12.5
    assert a.material_gwp_kgCO2e == pytest.approx(45.0, rel=REL)
    assert a.electricity_gwp_kgCO2e == pytest.approx(12.5, rel=REL)
    assert a.total_kgCO2e == pytest.approx(57.5, rel=REL)
    # benzene 35 + 2-MeTHF 2.5*5 = 47.5
    assert b.total_kgCO2e == pytest.approx(60.0, rel=REL)


def test_unresolved_materials_are_listed_not_defaulted(results):
    adjusted, resolutions, assumptions = results
    a = route_result(adjusted["a"], resolutions, assumptions)
    assert a.missing == ["cas:67-64-1", "name:novel ligand z"]
    unresolved = [r for r in a.materials if r.factor is None]
    assert {r.gwp_kgCO2e for r in unresolved} == {None}


def test_contribution_split_by_role_and_provenance(results):
    adjusted, resolutions, assumptions = results
    a = route_result(adjusted["a"], resolutions, assumptions)
    assert a.by_role["reactant"] == pytest.approx(35.0, rel=REL)
    assert a.by_role["solvent"] == pytest.approx(10.0, rel=REL)
    assert a.by_provenance["primary"] == pytest.approx(35.0, rel=REL)
    assert a.by_provenance["background_db"] == pytest.approx(10.0, rel=REL)
    # Electricity is attributed to the grid factor's own provenance class.
    assert a.by_provenance["assumption"] == pytest.approx(12.5, rel=REL)
    assert sum(a.by_role.values()) == pytest.approx(a.material_gwp_kgCO2e, rel=REL)


def test_identical_masses_drop_out_of_the_diff(results):
    adjusted, resolutions, _ = results
    diff = diff_routes(adjusted["a"], adjusted["b"], resolutions)
    keys = {row.key for row in diff.rows}
    assert "cas:71-43-2" not in keys      # benzene: 5.0 kg in both
    assert "cas:67-64-1" not in keys      # acetone: 1.25 kg in both
    assert keys == {"cas:108-88-3", "cas:96-47-9", "name:novel ligand z"}
    assert diff.delta_electricity_kWh == pytest.approx(0.0, abs=1e-12)


def test_delta_signs_follow_a_minus_b(results):
    adjusted, resolutions, _ = results
    rows = {r.key: r for r in diff_routes(adjusted["a"], adjusted["b"], resolutions).rows}
    assert rows["cas:108-88-3"].delta_mass_kg == pytest.approx(10.0, rel=REL)
    assert rows["cas:96-47-9"].delta_mass_kg == pytest.approx(-2.5, rel=REL)
    assert rows["name:novel ligand z"].delta_mass_kg == pytest.approx(0.5, rel=REL)


def test_cancelling_gap_is_informational_but_a_real_gap_warns(results):
    """Spec 7.4: only unresolved materials that survive the diff are warnings."""
    adjusted, resolutions, _ = results
    diff = diff_routes(adjusted["a"], adjusted["b"], resolutions)
    assert diff.common_unresolved == ["cas:67-64-1"]
    assert diff.delta_unresolved == ["name:novel ligand z"]


def test_run_comparison_reports_provenance_and_hashes(analytic_ledger, analytic_table, model):
    c = run_comparison(analytic_ledger, "a", "b", analytic_table, model)
    assert c.factor_fingerprint == analytic_table.fingerprint()
    assert set(c.factor_sources) == set(analytic_table.sources)
    assert sorted(c.illustrative_keys) == ["cas:108-88-3", "cas:71-43-2", "cas:96-47-9"]


def test_unknown_route_name_is_a_clear_error(analytic_ledger, analytic_table, model):
    with pytest.raises(ValueError, match="nosuch"):
        run_comparison(analytic_ledger, "nosuch", "b", analytic_table, model)
