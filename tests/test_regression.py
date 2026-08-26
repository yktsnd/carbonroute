"""Frozen output for the analytic benchmark (spec section 10).

These numbers are a tripwire, not a truth claim. Any change to the conversion
arithmetic, the sampler, the draw order or the shipped GSDs moves them. When a
change is intended, update the values in the same commit and say why.

They depend on numpy's Generator stream, so a numpy release that changes
`standard_normal` would also trip this.
"""

import pytest

from carbonroute.compute import run_comparison
from carbonroute.report import build_lock, render_report
from carbonroute.sensitivity import reversal_thresholds

FROZEN = {
    "p_a_lower": 0.65115,
    "delta_median": -2.3410144082171405,
    "delta_p05": -15.029997072099162,
    "delta_p95": 8.625486783761978,
    "verdict": "A<B",
    "total_a": 57.5,
    "total_b": 60.0,
}


@pytest.fixture()
def comparison(analytic_ledger, analytic_table, model):
    return run_comparison(analytic_ledger, "a", "b", analytic_table, model)


def test_frozen_statistics(comparison):
    s = comparison.stats
    assert s.p_a_lower == FROZEN["p_a_lower"]
    assert s.delta_median == pytest.approx(FROZEN["delta_median"], rel=1e-12)
    assert s.delta_p05 == pytest.approx(FROZEN["delta_p05"], rel=1e-12)
    assert s.delta_p95 == pytest.approx(FROZEN["delta_p95"], rel=1e-12)
    assert s.verdict == FROZEN["verdict"]
    assert comparison.a.total_kgCO2e == pytest.approx(FROZEN["total_a"], rel=1e-12)
    assert comparison.b.total_kgCO2e == pytest.approx(FROZEN["total_b"], rel=1e-12)


def test_report_is_byte_identical_across_runs(analytic_ledger, analytic_table, model):
    def once():
        c = run_comparison(analytic_ledger, "a", "b", analytic_table, model)
        t = reversal_thresholds(
            analytic_ledger, "a", "b", analytic_table, model, iterations=1000, seed=1
        )
        return render_report(c, t, "benchmarks/analytic/ledger.yaml")

    assert once() == once()


def test_report_states_its_limits_before_its_conclusion(comparison):
    text = render_report(comparison, None, "benchmarks/analytic/ledger.yaml")
    iso = text.index("ISO 14067")
    assumptions = text.index("## Applied assumptions")
    conclusion = text.index("## Conclusion")
    assert iso < assumptions < conclusion
    assert "sha256" in text.lower()
    assert "ILLUSTRATIVE" in text
    assert "novel ligand z" in text.lower()


def test_lock_pins_everything_needed_to_reproduce(
    analytic_ledger, analytic_table, model, comparison
):
    lock = build_lock(
        analytic_ledger,
        "benchmarks/analytic/ledger.yaml",
        analytic_table,
        comparison.resolutions,
        comparison,
    )
    assert lock["schema_version"] == "0.1"
    assert lock["tool_version"]
    assert lock["ledger"]["sha256"]
    assert lock["factor_tables"]
    assert lock["uncertainty_config"]["sha256"]
    assert lock["rng"] == {"seed": 12345, "iterations": 20000}
    resolutions = lock["resolutions"]
    toluene = resolutions["cas:108-88-3"]
    assert toluene["resolved"] is True
    assert toluene["gwp_kgCO2e_per_kg"] == 1.0
    assert toluene["source"] and toluene["is_illustrative"] is True
    assert resolutions["name:novel ligand z"]["resolved"] is False


def test_lock_carries_no_machine_specific_paths(
    analytic_ledger, analytic_table, comparison
):
    """A lock file travels with a report; absolute paths make it unportable."""
    import json

    text = json.dumps(
        build_lock(
            analytic_ledger,
            "benchmarks/analytic/ledger.yaml",
            analytic_table,
            comparison.resolutions,
            comparison,
        )
    )
    assert "/home/" not in text
    assert not any(part.startswith("/") for part in json.loads(text)["factor_tables"]["sources"])


def test_lock_is_stable(analytic_ledger, analytic_table, comparison):
    import json

    def once():
        return json.dumps(
            build_lock(
                analytic_ledger,
                "benchmarks/analytic/ledger.yaml",
                analytic_table,
                comparison.resolutions,
                comparison,
            ),
            sort_keys=True,
            indent=2,
        )

    assert once() == once()
