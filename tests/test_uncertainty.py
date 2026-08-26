"""Monte Carlo behaviour: cancellation, determinism, verdicts (spec 7.5-7.6)."""

import numpy as np
import pytest

from carbonroute.compute import diff_routes, run_comparison
from carbonroute.ledger import adjust_all
from carbonroute.resolve import resolve_materials
from carbonroute.uncertainty import compare_monte_carlo, load_uncertainty


def _diff(ledger, table):
    adjusted = adjust_all(ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, table))
    return diff_routes(adjusted["a"], adjusted["b"], resolutions)


def test_gsd_lookup_falls_back_for_unknown_classes(model):
    assert model.gsd("primary") == pytest.approx(1.10)
    assert model.gsd("background_db") == pytest.approx(1.50)
    assert model.gsd("no such class") == model.gsd(model.fallback_class)


def test_config_documents_every_class_it_ships(model):
    assert set(model.descriptions) >= set(model.classes)
    assert model.fallback_class in model.classes


def test_same_seed_gives_identical_results(analytic_ledger, analytic_table, model):
    a = run_comparison(analytic_ledger, "a", "b", analytic_table, model, iterations=4000, seed=7)
    b = run_comparison(analytic_ledger, "a", "b", analytic_table, model, iterations=4000, seed=7)
    assert a.stats.p_a_lower == b.stats.p_a_lower
    assert a.stats.delta_median == b.stats.delta_median
    assert (a.stats.delta_p05, a.stats.delta_p95) == (b.stats.delta_p05, b.stats.delta_p95)


def test_different_seeds_move_the_answer_a_little_not_a_lot(
    analytic_ledger, analytic_table, model
):
    values = [
        run_comparison(
            analytic_ledger, "a", "b", analytic_table, model, iterations=20000, seed=s
        ).stats.p_a_lower
        for s in (1, 2, 3, 4)
    ]
    assert max(values) - min(values) < 0.02


def test_a_material_common_to_both_routes_carries_no_variance(
    analytic_ledger, analytic_table, model
):
    """The point of comparing by difference: shared inputs cannot widen the spread.

    Benzene is 5.0 kg in both routes and has a factor in the table. Making it
    ten times more uncertain must leave the comparison untouched.
    """
    base = run_comparison(
        analytic_ledger, "a", "b", analytic_table, model, iterations=8000, seed=11
    )
    widened = model.__class__(
        classes={**model.classes, "primary": 10.0},
        descriptions=model.descriptions,
        fallback_class=model.fallback_class,
        path=model.path,
    )
    after = run_comparison(
        analytic_ledger, "a", "b", analytic_table, widened, iterations=8000, seed=11
    )
    assert after.stats.p_a_lower == base.stats.p_a_lower
    assert after.stats.delta_p05 == pytest.approx(base.stats.delta_p05, rel=1e-12)


def test_unresolved_delta_material_is_excluded_and_named(
    analytic_ledger, analytic_table, model
):
    c = run_comparison(analytic_ledger, "a", "b", analytic_table, model, iterations=2000, seed=5)
    assert c.stats.excluded_keys == ["name:novel ligand z"]


def test_verdict_respects_the_indeterminate_band(analytic_ledger, analytic_table, model):
    led = analytic_ledger.model_copy(deep=True)
    led.assumptions.indeterminate_band.low = 0.0
    led.assumptions.indeterminate_band.high = 1.0
    c = run_comparison(led, "a", "b", analytic_table, model, iterations=2000, seed=5)
    assert c.stats.verdict == "indeterminate"

    led.assumptions.indeterminate_band.low = 0.5
    led.assumptions.indeterminate_band.high = 0.5
    c = run_comparison(led, "a", "b", analytic_table, model, iterations=2000, seed=5)
    assert c.stats.verdict in {"A<B", "B<A"}


def test_a_zero_gsd_class_is_treated_as_exact(analytic_ledger, analytic_table, model):
    exact = model.__class__(
        classes={k: 1.0 for k in model.classes},
        descriptions=model.descriptions,
        fallback_class=model.fallback_class,
        path=model.path,
    )
    c = run_comparison(analytic_ledger, "a", "b", analytic_table, exact, iterations=500, seed=3)
    # delta = 10.0 kg toluene * 1.0 - 2.5 kg 2-MeTHF * 5.0 = -2.5 kgCO2e, exactly
    assert c.stats.delta_median == pytest.approx(-2.5, rel=1e-12)
    assert c.stats.delta_p05 == pytest.approx(-2.5, rel=1e-12)
    assert c.stats.p_a_lower == 1.0


def test_sampled_medians_sit_where_the_lognormal_puts_them(
    analytic_ledger, analytic_table, model
):
    diff = _diff(analytic_ledger, analytic_table)
    stats = compare_monte_carlo(
        diff, analytic_ledger.assumptions, model, iterations=200_000, seed=99
    )
    # Median of (10*g_tol - 2.5*g_methf) has no closed form; check against a
    # direct simulation with the same distributions but an independent RNG.
    rng = np.random.default_rng(4242)
    sigma = np.log(model.gsd("background_db"))
    tol = 1.0 * np.exp(sigma * rng.standard_normal(200_000))
    methf = 5.0 * np.exp(sigma * rng.standard_normal(200_000))
    reference = np.median(10.0 * tol - 2.5 * methf)
    assert stats.delta_median == pytest.approx(reference, abs=0.15)
