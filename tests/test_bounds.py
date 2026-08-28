"""Tests for deciding a comparison from bounds instead of values."""

from __future__ import annotations

import pytest

from carbonroute.bounds import (
    Bound,
    BoundsError,
    bounded_verdict,
    load_bounds,
)
from carbonroute.compute import DeltaRow, DiffResult
from carbonroute.schema import Assumptions


def _assumptions(grid: float = 0.0) -> Assumptions:
    return Assumptions.model_validate(
        {
            "functional_unit": {"mass_kg": 1.0, "basis": "product"},
            "boundary": "cradle-to-gate",
            "grid_factor": {
                "id": "TEST",
                "value_kgCO2e_per_kWh": grid,
                "source": "test fixture",
                "uncertainty_class": "assumption",
            },
            "gwp_method": {"name": "IPCC-AR6", "horizon_years": 100, "feedbacks": False},
            "solvent_recovery_default": 0.0,
            "waste_treatment": "excluded",
            "monte_carlo": {"iterations": 100, "seed": 1},
            "indeterminate_band": {"low": 0.4, "high": 0.6},
        }
    )


def _row(key: str, delta: float) -> DeltaRow:
    """An unresolved delta row carrying `delta` kg/FU (a minus b)."""
    return DeltaRow(
        key=key,
        name=key,
        role="reagent",
        mass_a_kg=max(delta, 0.0),
        mass_b_kg=max(-delta, 0.0),
        delta_mass_kg=delta,
        factor=None,
        resolved=False,
    )


def _diff(rows: list[DeltaRow]) -> DiffResult:
    return DiffResult(
        a_name="a",
        b_name="b",
        rows=rows,
        delta_electricity_kWh=0.0,
        common_unresolved=[],
        delta_unresolved=[r.key for r in rows if not r.resolved],
    )


def _bound(key: str, low: float, high: float | None) -> Bound:
    return Bound(key=key, low=low, high=high, rationale="test", sources=())


# --- the arithmetic ---------------------------------------------------------


def test_decisive_when_bounds_cannot_change_the_sign():
    # One unresolved material, b-heavy by 10 kg. Even at its floor of 2.0 it
    # subtracts 20 from a resolved lead of only 5, so the delta is negative
    # everywhere: a is lower, whatever the true value turns out to be.
    diff = _diff([_row("x", -10.0)])
    v = bounded_verdict(diff, _assumptions(), {"x": _bound("x", 2.0, 30.0)})
    assert v.decisive is True
    assert v.verdict == "a_lower"


def test_not_decisive_when_the_box_straddles_zero():
    # Resolved lead of 0 and a wide box: the sign flips inside it.
    diff = _diff([_row("x", -1.0), _row("y", 1.0)])
    v = bounded_verdict(
        diff, _assumptions(), {"x": _bound("x", 0.0, 10.0), "y": _bound("y", 0.0, 10.0)}
    )
    assert v.decisive is False
    assert v.verdict == "indeterminate"


def test_missing_ceiling_does_not_block_a_conclusion_it_only_reinforces():
    """An open ceiling on a material that pushes the delta down must not
    prevent concluding the delta is always negative."""
    diff = _diff([_row("x", -10.0)])
    v = bounded_verdict(diff, _assumptions(), {"x": _bound("x", 2.0, None)})
    assert v.decisive is True
    assert v.verdict == "a_lower"
    assert v.delta_min_kgCO2e is None  # genuinely unbounded on that side
    assert v.delta_max_kgCO2e is not None


def test_extremes_are_the_true_corners():
    # delta = resolved + sum(dm_i * f_i); with resolved == 0 here.
    # max: dm>0 at high, dm<0 at low. min: the other way.
    diff = _diff([_row("pos", 2.0), _row("neg", -3.0)])
    bounds = {"pos": _bound("pos", 1.0, 4.0), "neg": _bound("neg", 1.0, 5.0)}
    v = bounded_verdict(diff, _assumptions(), bounds)
    assert v.delta_max_kgCO2e == pytest.approx(2.0 * 4.0 + (-3.0) * 1.0)
    assert v.delta_min_kgCO2e == pytest.approx(2.0 * 1.0 + (-3.0) * 5.0)


def test_a_material_with_no_bound_is_floored_at_zero_not_dropped():
    """No factor is negative, so zero is a real floor -- but the ceiling is
    then open, and that must be reported rather than assumed away."""
    diff = _diff([_row("x", -10.0)])
    v = bounded_verdict(diff, _assumptions(), {})
    assert v.missing_bound_keys == ("x",)
    # Floored at zero, the delta's maximum is exactly the resolved part (0).
    assert v.delta_max_kgCO2e == pytest.approx(0.0)
    assert v.delta_min_kgCO2e is None


# --- thresholds -------------------------------------------------------------


def test_threshold_is_the_tie_point_with_others_held_least_favourably():
    # resolved = 0; x is b-heavy by 4 kg, y a-heavy by 1 kg bounded [0, 2].
    # For x, the least favourable other is y at its HIGH (2.0), contributing
    # +2. So x ties when 4*f == 2, i.e. f == 0.5.
    diff = _diff([_row("x", -4.0), _row("y", 1.0)])
    v = bounded_verdict(diff, _assumptions(), {"y": _bound("y", 0.0, 2.0)})
    x = next(c for c in v.critical if c.key == "x")
    assert x.status == "threshold"
    assert x.threshold_kgCO2e_per_kg == pytest.approx(0.5)
    assert x.direction == "above"


def test_material_that_cannot_flip_the_verdict_is_reported_as_always():
    """A non-positive tie point means no admissible value reaches it. That is
    a stronger result than clearing a threshold and must not read as a gap."""
    # x is b-heavy and the resolved part already favours a: nothing x can be
    # (>= 0) pushes the delta back positive.
    rows = [_row("x", -1.0)]
    diff = DiffResult(
        a_name="a",
        b_name="b",
        rows=rows,
        delta_electricity_kWh=-10.0,  # drives resolved delta strongly negative
        common_unresolved=[],
        delta_unresolved=["x"],
    )
    v = bounded_verdict(diff, _assumptions(grid=1.0), {"x": _bound("x", 0.0, None)})
    x = next(c for c in v.critical if c.key == "x")
    assert x.status == "always"
    assert x.cleared_by_bound is True


def test_threshold_not_computable_when_an_opposing_material_is_unbounded():
    diff = _diff([_row("x", -4.0), _row("y", 1.0)])
    v = bounded_verdict(diff, _assumptions(), {"y": _bound("y", 0.0, None)})
    x = next(c for c in v.critical if c.key == "x")
    assert x.status == "unbounded"
    assert x.threshold_kgCO2e_per_kg is None


def test_clearing_is_judged_against_the_supplied_bound():
    diff = _diff([_row("x", -4.0), _row("y", 1.0)])
    y_bound = {"y": _bound("y", 0.0, 2.0)}
    # x needs to be above 0.5; a floor of 3.5 clears it, a floor of 0.1 does not.
    cleared = bounded_verdict(diff, _assumptions(), {**y_bound, "x": _bound("x", 3.5, None)})
    assert next(c for c in cleared.critical if c.key == "x").cleared_by_bound is True
    not_cleared = bounded_verdict(diff, _assumptions(), {**y_bound, "x": _bound("x", 0.1, 0.2)})
    assert next(c for c in not_cleared.critical if c.key == "x").cleared_by_bound is False


# --- a bound is never a factor ---------------------------------------------


def test_bounds_never_resolve_a_material():
    """The whole design rests on this: supplying a bound must not make an
    unresolved material count as resolved anywhere."""
    diff = _diff([_row("x", -10.0)])
    v = bounded_verdict(diff, _assumptions(), {"x": _bound("x", 2.0, 30.0)})
    # The diff itself is untouched, so coverage computed from it is untouched.
    assert diff.rows[0].resolved is False
    assert diff.rows[0].factor is None
    assert diff.delta_unresolved == ["x"]
    # And the resolved part of the delta ignores the bound entirely.
    assert v.resolved_delta_kgCO2e == pytest.approx(0.0)


# --- loading ----------------------------------------------------------------


def _write(tmp_path, text: str):
    p = tmp_path / "bounds.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_reads_intervals_and_metadata(tmp_path):
    p = _write(
        tmp_path,
        "bounds:\n"
        '  "cas:1-1-1":\n'
        "    low: 3.5\n"
        "    high: 27.3\n"
        "    rationale: because\n"
        "    sources: [a citation]\n",
    )
    got = load_bounds(p)
    assert got["cas:1-1-1"].low == 3.5
    assert got["cas:1-1-1"].high == 27.3
    assert got["cas:1-1-1"].rationale == "because"
    assert got["cas:1-1-1"].sources == ("a citation",)


def test_load_allows_an_omitted_ceiling(tmp_path):
    p = _write(tmp_path, 'bounds:\n  x:\n    low: 1.0\n    high: null\n    rationale: r\n')
    assert load_bounds(p)["x"].bounded_above is False


def test_load_rejects_a_bound_with_no_rationale(tmp_path):
    p = _write(tmp_path, "bounds:\n  x:\n    low: 1.0\n")
    with pytest.raises(BoundsError, match="rationale"):
        load_bounds(p)


def test_load_rejects_a_negative_floor(tmp_path):
    p = _write(tmp_path, "bounds:\n  x:\n    low: -1.0\n    rationale: r\n")
    with pytest.raises(BoundsError, match="cannot be negative"):
        load_bounds(p)


def test_load_rejects_an_inverted_interval(tmp_path):
    p = _write(tmp_path, "bounds:\n  x:\n    low: 5.0\n    high: 1.0\n    rationale: r\n")
    with pytest.raises(BoundsError, match="below low"):
        load_bounds(p)


def test_load_rejects_a_malformed_file(tmp_path):
    p = _write(tmp_path, "not_bounds: {}\n")
    with pytest.raises(BoundsError, match="bounds"):
        load_bounds(p)


# --- the ibuprofen case study, pinned --------------------------------------


def test_ibuprofen_case_study_is_decided_by_the_ionic_liquid_alone():
    """Pins the published result of examples/case-studies/ibuprofen-*.

    This is the case that motivated the feature: 52.9% coverage, no ranking
    possible from factors alone, but the ranking is nonetheless settled over
    the asserted bounds -- and settled by exactly one material. If any of
    these numbers move, the case study's write-up is stale.
    """
    from pathlib import Path

    from carbonroute.compute import adjust_route, diff_routes
    from carbonroute.ledger import load_ledger
    from carbonroute.resolve import (
        FactorTable,
        default_factor_paths,
        default_synonym_paths,
        resolve_materials,
    )

    root = Path(__file__).resolve().parents[1]
    case = root / "examples" / "case-studies" / "ibuprofen-bogdan-vs-enzymatic"

    ledger = load_ledger(case / "ledger.yaml")
    table = FactorTable.load(list(default_factor_paths(root)))
    for syn in default_synonym_paths(root):
        table.load_synonyms(syn)

    a = adjust_route("bogdan", ledger.routes["bogdan"], ledger.assumptions)
    b = adjust_route("enzymatic", ledger.routes["enzymatic"], ledger.assumptions)
    diff = diff_routes(a, b, resolve_materials(list(a.materials) + list(b.materials), table))

    verdict = bounded_verdict(diff, ledger.assumptions, load_bounds(case / "bounds.yaml"))

    assert verdict.decisive is True
    assert verdict.verdict == "a_lower"  # bogdan is the lower-carbon route
    assert verdict.delta_max_kgCO2e == pytest.approx(-15.01, abs=0.05)

    il = next(c for c in verdict.critical if c.key == "cas:174501-64-5")
    assert il.status == "threshold"
    assert il.threshold_kgCO2e_per_kg == pytest.approx(1.715, abs=0.005)
    assert il.cleared_by_bound is True

    # Every other bounded material is irrelevant to the verdict: nothing it
    # could be would flip it. That is the point of the case study.
    others = [c for c in verdict.critical if c.key != "cas:174501-64-5"]
    assert {c.status for c in others} <= {"always", "unbounded"}


def test_ibuprofen_verdict_turns_over_at_about_half_ionic_liquid_recovery():
    """The paper's own conclusion is conditional on recycling; so is ours.

    Pins the crossover this project computes independently (~51% recovery of
    the ionic liquid), which is the number the case study's write-up quotes
    against the paper's 50%/100% scenarios.
    """
    from pathlib import Path

    from carbonroute.compute import adjust_route, diff_routes
    from carbonroute.ledger import load_ledger
    from carbonroute.resolve import (
        FactorTable,
        default_factor_paths,
        default_synonym_paths,
        resolve_materials,
    )

    root = Path(__file__).resolve().parents[1]
    case = root / "examples" / "case-studies" / "ibuprofen-bogdan-vs-enzymatic"
    ledger = load_ledger(case / "ledger.yaml")
    table = FactorTable.load(list(default_factor_paths(root)))
    for syn in default_synonym_paths(root):
        table.load_synonyms(syn)
    bounds = load_bounds(case / "bounds.yaml")

    def verdict_at(recovery: float) -> str:
        asm = ledger.assumptions.model_copy(
            update={"solvent_recovery": {"174501-64-5": recovery}}
        )
        a = adjust_route("bogdan", ledger.routes["bogdan"], asm)
        b = adjust_route("enzymatic", ledger.routes["enzymatic"], asm)
        diff = diff_routes(a, b, resolve_materials(list(a.materials) + list(b.materials), table))
        return bounded_verdict(diff, asm, bounds).verdict

    assert verdict_at(0.0) == "a_lower"
    assert verdict_at(0.50) == "a_lower"
    assert verdict_at(0.55) == "indeterminate"

    lo, hi = 0.0, 0.99
    for _ in range(40):
        mid = (lo + hi) / 2
        if verdict_at(mid) == "a_lower":
            lo = mid
        else:
            hi = mid
    assert hi == pytest.approx(0.51, abs=0.01)
