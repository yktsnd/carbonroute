"""CLI surface and its side effects (spec section 8)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from carbonroute.cli import main

LEDGER = "benchmarks/analytic/ledger.yaml"
FACTORS = "benchmarks/analytic/factors.csv"


@pytest.fixture()
def run(repo_root):
    runner = CliRunner()

    def _run(*args, expect: int | None = 0):
        result = runner.invoke(main, [str(a) for a in args], catch_exceptions=False)
        if expect is not None:
            assert result.exit_code == expect, result.output
        return result

    cwd = Path.cwd()
    import os

    os.chdir(repo_root)
    try:
        yield _run
    finally:
        os.chdir(cwd)


def test_validate_accepts_a_good_ledger(run):
    assert "valid" in run("validate", LEDGER).output


def test_validate_rejects_a_bad_ledger_without_a_traceback(run, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema_version: '0.1'\nroutes: {}\n", encoding="utf-8")
    result = run("validate", str(bad), expect=2)
    assert "Traceback" not in result.output
    assert result.output.strip().startswith("error:")


def test_resolve_exits_3_when_factors_are_missing(run):
    result = run("resolve", LEDGER, "--factors", FACTORS, "--show-missing", expect=3)
    assert "novel ligand Z" in result.output


def test_compare_writes_only_the_output_file(run, tmp_path):
    out = tmp_path / "report.md"
    before = {p.name for p in Path("benchmarks/analytic").iterdir()}
    run("compare", LEDGER, "--a", "a", "--b", "b", "--factors", FACTORS, "-o", str(out))
    assert out.exists()
    assert "## Conclusion" in out.read_text(encoding="utf-8")
    assert {p.name for p in Path("benchmarks/analytic").iterdir()} == before


def test_compare_headline_is_a_ranking_not_a_number(run):
    text = run("compare", LEDGER, "--a", "a", "--b", "b", "--factors", FACTORS).output
    headline = text.split("## Conclusion", 1)[1].strip().splitlines()[0]
    assert "P = " in headline or "P > " in headline or "P < " in headline
    assert "kgCO2e" not in headline


def test_compare_rejects_an_unknown_route_name(run):
    result = run("compare", LEDGER, "--a", "a", "--b", "nope", "--factors", FACTORS, expect=2)
    assert "nope" in result.output and "Traceback" not in result.output


def test_seed_and_iteration_overrides_reach_the_report(run):
    text = run(
        "compare", LEDGER, "--a", "a", "--b", "b", "--factors", FACTORS,
        "--iterations", "500", "--seed", "777", "--no-thresholds",
    ).output
    assert "500 draws" in text and "777" in text
    assert "Reversal thresholds" not in text


def test_lock_output_is_deterministic_json(run, tmp_path):
    first, second = tmp_path / "1.json", tmp_path / "2.json"
    for out in (first, second):
        run("lock", LEDGER, "--factors", FACTORS, "-o", str(out))
    assert first.read_text() == second.read_text()
    payload = json.loads(first.read_text())
    assert payload["ledger"]["sha256"] and payload["factor_tables"]["fingerprint"]


def test_fetch_is_refused(run):
    result = run("resolve", LEDGER, "--factors", FACTORS, "--fetch", expect=2)
    assert "not implemented" in result.output


def test_no_networking_code_is_reachable(repo_root):
    """Spec section 8: network access is off, and there is nothing to turn on.

    Checked against the parsed import graph rather than the file text, so that
    prose explaining the absence of networking does not trip the test.
    """
    import ast

    banned = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}
    for path in (repo_root / "src" / "carbonroute").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in banned, f"{path.name} imports {name}"
