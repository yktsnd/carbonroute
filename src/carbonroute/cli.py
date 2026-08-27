"""Command-line entry point (spec section 8).

Four commands: ``validate``, ``resolve``, ``compare``, ``lock``. The only
permitted side effect is writing the path given by ``-o``; without it,
output goes to stdout. Nothing here opens a socket: ``--fetch`` exists on
``resolve``/``compare`` only to fail loudly, since v0 ships no network
fetchers (spec section 13's "no LLM-guessed values" cousin: no silently
fetched ones either).

Imports of :mod:`compute` and :mod:`sensitivity` are deferred to inside the
command bodies rather than made at module level. That keeps ``--help``,
``validate`` and (mostly) ``resolve`` working even while those modules are
still being written elsewhere in the tree, and it costs nothing once they
exist.
"""

from __future__ import annotations

import hashlib
import csv
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

import click

from .ledger import LedgerError, adjust_all, load_ledger
from .resolve import FactorTable, FactorTableError, default_factor_paths, resolve_materials
from .report import render_coverage, build_lock, dump_lock_json, render_resolution_table

_FETCH_ERROR = (
    "--fetch is not implemented: v0 ships no network fetchers and opens no "
    "sockets anywhere in this package. Provide factor tables locally via "
    "--factors instead."
)


def _fail(msg: str, code: int = 2) -> NoReturn:
    click.echo(f"error: {msg}", err=True)
    sys.exit(code)


def _load_ledger_or_exit(path: str):
    try:
        return load_ledger(path)
    except LedgerError as exc:
        _fail(str(exc))


def _load_factors_or_exit(factor_paths: tuple[str, ...]) -> FactorTable:
    paths: list[str | Path] = list(factor_paths) or list(default_factor_paths())
    if not paths:
        _fail(
            "no factor tables found: pass --factors PATH (repeatable) or "
            "populate data/factors/*.csv"
        )
    try:
        return FactorTable.load(paths)
    except FactorTableError as exc:
        _fail(str(exc))


def _write_output(text: str, output_path: str | None) -> None:
    """The only side effect this CLI is allowed: writing ``-o``, or stdout."""
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    else:
        click.echo(text, nl=False)


_FACTORS_OPTION = click.option(
    "--factors",
    "factor_paths",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Factor table CSV (repeatable). Defaults to every CSV under data/factors/.",
)


@click.group()
def main() -> None:
    """carbonroute: comparative cradle-to-gate GHG screening for synthetic routes.

    Not an ISO 14067-conformant calculator. Ranks two routes and reports a
    probability, never a single absolute number, as its conclusion.
    """


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
def validate(ledger_path: str) -> None:
    """Validate ROUTE.yaml against the ledger schema. Performs no computation."""
    _load_ledger_or_exit(ledger_path)
    click.echo(f"OK: {ledger_path} is a valid route ledger.")


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
@_FACTORS_OPTION
@click.option("--show-missing", is_flag=True, help="List each unresolved material in detail.")
@click.option("--fetch", is_flag=True, help="Not implemented in v0; always errors.")
def resolve(ledger_path: str, factor_paths: tuple[str, ...], show_missing: bool, fetch: bool) -> None:
    """List factor resolution and gaps for every route in ROUTE.yaml. No emissions math."""
    if fetch:
        _fail(_FETCH_ERROR)
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths)
    adjusted = adjust_all(ledger)

    from .compute import route_result  # deferred: compute.py is a sibling deliverable

    routes = {}
    any_missing = False
    for name, ar in adjusted.items():
        resolutions = resolve_materials(ar.materials, table)
        rr = route_result(ar, resolutions, ledger.assumptions)
        routes[name] = rr
        any_missing = any_missing or bool(rr.missing)

    click.echo(render_resolution_table(routes, table, show_missing), nl=False)
    if any_missing:
        sys.exit(3)


@main.command()
@click.option(
    "--processes",
    "processes_dir",
    type=click.Path(exists=True, file_okay=False),
    default="data/processes",
    show_default=True,
    help="Directory of production recipes, one YAML per substance.",
)
@_FACTORS_OPTION
@click.option("--grid-kgco2e-per-kwh", "grid_value", type=float, default=None,
              help="Emission factor for process electricity. Omit and electricity is left out, "
                   "which weakens the bound rather than invalidating it.")
@click.option("--grid-source", default="", help="Where the grid factor came from. Required with it.")
@click.option("--fuel-kgco2e-per-mj", "fuel_value", type=float, default=None,
              help="Emission factor for process fuel or steam, per MJ.")
@click.option("--fuel-source", default="", help="Where the fuel factor came from. Required with it.")
@click.option("--completeness-floor", type=float, default=0.5, show_default=True,
              help="Assumed worst-case share of the true footprint that a recipe captures. "
                   "Sets the top of each derived interval. A declared assumption, not a "
                   "measurement.")
@click.option("--report", is_flag=True, help="Print the full derivation for every substance.")
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def bootstrap(
    processes_dir: str,
    factor_paths: tuple[str, ...],
    grid_value: float | None,
    grid_source: str,
    fuel_value: float | None,
    fuel_source: str,
    completeness_floor: float,
    report: bool,
    output_path: str | None,
) -> None:
    """Derive factors for substances no open database covers, from production recipes.

    Each recipe states what a substance is made from and how much energy it
    takes, with a citation per number. Multiplying that by the factors already
    in hand gives a floor for the product, which can feed the next recipe. Every
    omitted term is non-negative, so the result is a lower bound before it is
    anything else, and it is published as an interval rather than a number.
    """
    from .bootstrap import (
        BootstrapError,
        EnergyFactors,
        derive_all,
        load_recipes,
        to_rows,
        write_csv,
    )

    if grid_value is not None and not grid_source.strip():
        _fail("--grid-kgco2e-per-kwh requires --grid-source: an undocumented factor is "
              "exactly what this tool exists to prevent")
    if fuel_value is not None and not fuel_source.strip():
        _fail("--fuel-kgco2e-per-mj requires --fuel-source")

    table = _load_factors_or_exit(factor_paths) if factor_paths else _load_factors_or_exit(())
    try:
        recipes = load_recipes(processes_dir)
        result = derive_all(
            recipes,
            table,
            EnergyFactors(grid_value, grid_source.strip(), fuel_value, fuel_source.strip()),
            completeness_floor,
        )
    except BootstrapError as exc:
        _fail(str(exc))

    if not recipes:
        _fail(f"no recipes found in {processes_dir}")

    rows = to_rows(result, date.today().isoformat(), completeness_floor)

    lines = [f"Recipes read: {len(recipes)}; derived: {len(result.derived)}; "
             f"skipped: {len(result.skipped)}; rows written: {len(rows)}", ""]
    for key in sorted(result.derived):
        d = result.derived[key]
        kind = "complete" if d.is_complete else f"lower bound, {len(d.omitted)} term(s) omitted"
        lines.append(
            f"  {d.name} ({key}): [{d.low_kgCO2e_per_kg:.4g}, {d.high_kgCO2e_per_kg:.4g}] "
            f"kgCO2e/kg  median {d.median_kgCO2e_per_kg:.4g}, gsd {d.gsd:.3f}  [{kind}]"
        )
        if report:
            for item in d.included:
                lines.append(f"      + {item}")
            for item in d.omitted:
                lines.append(f"      ? {item}")
    for key in sorted(result.skipped):
        lines.append(f"  SKIPPED {key}: {result.skipped[key]}")
    lines.append("")

    click.echo("\n".join(lines), err=output_path is not None, nl=False)
    if output_path:
        write_csv(rows, output_path)
        click.echo(f"wrote {len(rows)} row(s) to {output_path}", err=True)
    elif rows:
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        click.echo(buf.getvalue(), nl=False)


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--a", "a_name", required=True, help="Name of the first route in the ledger.")
@click.option("--b", "b_name", required=True, help="Name of the second route in the ledger.")
@_FACTORS_OPTION
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def coverage(
    ledger_path: str, a_name: str, b_name: str,
    factor_paths: tuple[str, ...], output_path: str | None,
) -> None:
    """Report how much of the A-vs-B delta set the loaded factor tables cover."""
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths)
    adjusted = adjust_all(ledger)
    for name in (a_name, b_name):
        if name not in adjusted:
            _fail(f"route {name!r} is not in {ledger_path}; "
                  f"available: {', '.join(sorted(adjusted))}")

    from .compute import coverage as compute_coverage, diff_routes

    resolutions = {}
    for name in (a_name, b_name):
        resolutions.update(resolve_materials(adjusted[name].materials, table))
    diff = diff_routes(adjusted[a_name], adjusted[b_name], resolutions)
    cov = compute_coverage(diff)
    _write_output(render_coverage(cov, a_name, b_name, table), output_path)
    if cov.unresolved:
        sys.exit(3)


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--a", "a_name", required=True, help="Name of the first route in the ledger.")
@click.option("--b", "b_name", required=True, help="Name of the second route in the ledger.")
@_FACTORS_OPTION
@click.option(
    "--uncertainty",
    "uncertainty_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Override the default uncertainty class config (config/uncertainty.yaml).",
)
@click.option("--iterations", type=int, default=None, help="Override assumptions.monte_carlo.iterations.")
@click.option("--seed", type=int, default=None, help="Override assumptions.monte_carlo.seed.")
@click.option("--no-thresholds", is_flag=True, help="Skip the reversal-threshold scan (faster).")
@click.option("--fetch", is_flag=True, help="Not implemented in v0; always errors.")
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def compare(
    ledger_path: str,
    a_name: str,
    b_name: str,
    factor_paths: tuple[str, ...],
    uncertainty_path: str | None,
    iterations: int | None,
    seed: int | None,
    no_thresholds: bool,
    fetch: bool,
    output_path: str | None,
) -> None:
    """Compare route A against route B and write a Markdown report."""
    if fetch:
        _fail(_FETCH_ERROR)
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths)

    from .compute import run_comparison
    from .report import render_report
    from .uncertainty import load_uncertainty

    try:
        model = load_uncertainty(uncertainty_path)
    except (OSError, ValueError) as exc:
        _fail(f"could not load uncertainty config: {exc}")

    try:
        comparison = run_comparison(ledger, a_name, b_name, table, model, iterations=iterations, seed=seed)
    except ValueError as exc:
        # Covers unknown route names (compute.run_comparison wraps KeyError as ValueError).
        _fail(str(exc))

    thresholds = None
    if not no_thresholds:
        from .sensitivity import reversal_thresholds

        thresholds = reversal_thresholds(ledger, a_name, b_name, table, model)

    _write_output(render_report(comparison, thresholds, ledger_path), output_path)


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
@_FACTORS_OPTION
@click.option(
    "--uncertainty",
    "uncertainty_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Override the default uncertainty class config; pinned into the lock file.",
)
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def lock(ledger_path: str, factor_paths: tuple[str, ...], uncertainty_path: str | None, output_path: str | None) -> None:
    """Pin the factor table versions and resolution results for ROUTE.yaml."""
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths)
    adjusted = adjust_all(ledger)

    all_materials = [m for ar in adjusted.values() for m in ar.materials]
    resolutions = resolve_materials(all_materials, table)

    payload = build_lock(ledger, ledger_path, table, resolutions)
    if uncertainty_path:
        # build_lock always pins the default uncertainty config (its binding
        # signature takes no such argument); when the caller overrides it on
        # the command line, reflect that override in the emitted lock here.
        digest = hashlib.sha256(Path(uncertainty_path).read_bytes()).hexdigest()
        payload["uncertainty_config"] = {"path": uncertainty_path, "sha256": digest}

    _write_output(dump_lock_json(payload), output_path)


if __name__ == "__main__":  # pragma: no cover
    main()
