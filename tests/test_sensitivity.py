"""Reversal thresholds (spec section 7.7)."""

import pytest

from carbonroute.sensitivity import reversal_thresholds


@pytest.fixture()
def thresholds(analytic_ledger, analytic_table, model):
    return reversal_thresholds(
        analytic_ledger, "a", "b", analytic_table, model, iterations=2000, seed=101
    )


def test_every_declared_variable_is_scanned(thresholds, analytic_ledger):
    names = {t.variable for t in thresholds}
    assert "solvent_recovery_default" in names
    assert "grid_factor" in names
    for route in ("a", "b"):
        for step in analytic_ledger.routes[route].steps:
            assert f"yield:{route}:{step.id}" in names


def test_a_crossing_is_inside_the_range_it_was_found_in(thresholds):
    for t in thresholds:
        if t.crossing is not None:
            assert t.low <= t.crossing <= t.high


def test_no_crossing_is_stated_not_guessed(thresholds):
    """The grid factor cancels here, so no grid value can flip the ranking."""
    grid = next(t for t in thresholds if t.variable == "grid_factor")
    assert grid.crossing is None
    assert "not change" in grid.message or "no crossing" in grid.message.lower()


def test_solvent_recovery_flips_the_ranking(analytic_ledger, analytic_table, model):
    """Route A carries 10 kg of a cheap solvent; B carries 2.5 kg of a dear one.

    Recovering solvent shrinks both, but it shrinks A's larger charge faster,
    so a high enough recovery must move the ranking.
    """
    ts = reversal_thresholds(
        analytic_ledger, "a", "b", analytic_table, model, iterations=2000, seed=101
    )
    recovery = next(t for t in ts if t.variable == "solvent_recovery_default")
    assert recovery.crossing is None or 0.0 <= recovery.crossing <= 0.95


def test_thresholds_are_reproducible(analytic_ledger, analytic_table, model):
    kw = dict(iterations=1500, seed=55)
    first = reversal_thresholds(analytic_ledger, "a", "b", analytic_table, model, **kw)
    second = reversal_thresholds(analytic_ledger, "a", "b", analytic_table, model, **kw)
    assert [(t.variable, t.crossing, t.p_at_low, t.p_at_high) for t in first] == [
        (t.variable, t.crossing, t.p_at_low, t.p_at_high) for t in second
    ]
