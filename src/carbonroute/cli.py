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
from .resolve import default_synonym_paths, FactorTable, FactorTableError, default_factor_paths, resolve_materials
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


def _load_factors_or_exit(
    factor_paths: tuple[str, ...], synonym_paths: tuple[str, ...] = ()
) -> FactorTable:
    paths: list[str | Path] = list(factor_paths) or list(default_factor_paths())
    if not paths:
        _fail(
            "no factor tables found: pass --factors PATH (repeatable) or "
            "populate data/factors/*.csv"
        )
    try:
        table = FactorTable.load(paths)
        for synonyms in list(synonym_paths) or list(default_synonym_paths()):
            table.load_synonyms(synonyms)
        return table
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

_SYNONYMS_OPTION = click.option(
    "--synonyms",
    "synonym_paths",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Alias table CSV mapping the names a ledger uses onto identifiers "
    "(repeatable). Defaults to every CSV under data/synonyms/.",
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
@_SYNONYMS_OPTION
@click.option("--show-missing", is_flag=True, help="List each unresolved material in detail.")
@click.option("--fetch", is_flag=True, help="Not implemented in v0; always errors.")
def resolve(ledger_path: str, factor_paths: tuple[str, ...], synonym_paths: tuple[str, ...], show_missing: bool, fetch: bool) -> None:
    """List factor resolution and gaps for every route in ROUTE.yaml. No emissions math."""
    if fetch:
        _fail(_FETCH_ERROR)
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths, synonym_paths)
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
@_SYNONYMS_OPTION
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
    synonym_paths: tuple[str, ...],
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

    table = _load_factors_or_exit(factor_paths, synonym_paths) if factor_paths else _load_factors_or_exit(())
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
@_SYNONYMS_OPTION
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def coverage(
    ledger_path: str, a_name: str, b_name: str,
    factor_paths: tuple[str, ...], synonym_paths: tuple[str, ...], output_path: str | None,
) -> None:
    """Report how much of the A-vs-B delta set the loaded factor tables cover."""
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths, synonym_paths)
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
@_SYNONYMS_OPTION
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
@click.option(
    "--bounds",
    "bounds_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=(
        "Bounds file asserting where each unresolved material's factor cannot be. "
        "Adds a section asking whether the ranking holds everywhere inside those "
        "bounds. Bounds are never treated as factors and never change coverage."
    ),
)
@click.option("--fetch", is_flag=True, help="Not implemented in v0; always errors.")
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def compare(
    ledger_path: str,
    a_name: str,
    b_name: str,
    factor_paths: tuple[str, ...],
    synonym_paths: tuple[str, ...],
    uncertainty_path: str | None,
    iterations: int | None,
    seed: int | None,
    no_thresholds: bool,
    bounds_path: str | None,
    fetch: bool,
    output_path: str | None,
) -> None:
    """Compare route A against route B and write a Markdown report."""
    if fetch:
        _fail(_FETCH_ERROR)
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths, synonym_paths)

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

    bounded = None
    if bounds_path:
        from .bounds import BoundsError, bounded_verdict, load_bounds

        try:
            bounds = load_bounds(bounds_path)
        except BoundsError as exc:
            _fail(str(exc))
        bounded = bounded_verdict(comparison.diff, comparison.assumptions, bounds)

    _write_output(render_report(comparison, thresholds, ledger_path, bounded), output_path)


@main.command()
@click.argument("ledger_path", type=click.Path(exists=True, dir_okay=False))
@_FACTORS_OPTION
@_SYNONYMS_OPTION
@click.option(
    "--uncertainty",
    "uncertainty_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Override the default uncertainty class config; pinned into the lock file.",
)
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def lock(ledger_path: str, factor_paths: tuple[str, ...], synonym_paths: tuple[str, ...], uncertainty_path: str | None, output_path: str | None) -> None:
    """Pin the factor table versions and resolution results for ROUTE.yaml."""
    ledger = _load_ledger_or_exit(ledger_path)
    table = _load_factors_or_exit(factor_paths, synonym_paths)
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


@main.command()
@click.option(
    "--reactions",
    "reactions_path",
    type=click.Path(exists=True, dir_okay=False),
    default="data/rhea/reactions.tsv",
    show_default=True,
    help="Reaction database written by scripts/ingest_rhea.py.",
)
@click.option(
    "--structures",
    "structures_path",
    type=click.Path(exists=True, dir_okay=False),
    default="data/rhea/participants.csv",
    show_default=True,
    help="Participant structures (SMILES), written by the same script.",
)
@click.option(
    "--template",
    "template_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Reaction-class template: the chemical counterpart to screen against.",
)
@click.option(
    "--bounds",
    "bounds_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Bounds for the materials the screen cannot resolve to a public factor.",
)
@click.option(
    "--assumptions-from",
    "assumptions_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="A ledger whose assumptions block the screen should adopt.",
)
@click.option(
    "--enzymatic-yield",
    "enzymatic_yield",
    type=click.FloatRange(min=0.0, max=1.0, min_open=True),
    default=1.0,
    show_default=True,
    help=(
        "The enzymatic route's conversion to product. Divides the cofactor "
        "demand. The 1.0 default flatters the enzyme: a template's chemical "
        "amounts already carry its source paper's real yield."
    ),
)
@click.option(
    "--reference-recovery",
    "reference_recovery",
    type=click.FloatRange(min=0.0, max=1.0, max_open=True),
    default=0.90,
    show_default=True,
    help="Solvent recovery at which the minimum-conversion figures are evaluated.",
)
@click.option(
    "--cofactor-recycling",
    "cofactor_recycling",
    type=click.FloatRange(min=0.0, max=1.0, max_open=True),
    default=0.0,
    show_default=True,
    help=(
        "Share of cofactor regenerated rather than discarded -- the enzymatic "
        "route's counterpart of solvent recovery. Requires the template to "
        "declare a cofactor_regeneration block, whose co-substrate is then "
        "charged every turnover."
    ),
)
@click.option(
    "--fair-fight",
    "fair_fight",
    is_flag=True,
    default=False,
    help=(
        "Sweep BOTH effort dials together -- chemical solvent recovery and "
        "enzymatic cofactor regeneration at the same rate -- and report who "
        "wins when neither side is the only one optimised."
    ),
)
@click.option(
    "--frontier",
    "frontier",
    is_flag=True,
    default=False,
    help=(
        "Also sweep enzymatic conversion and print the class's break-even "
        "curve on the (conversion, solvent recovery) plane."
    ),
)
@_FACTORS_OPTION
@_SYNONYMS_OPTION
@click.option("-o", "--output", "output_path", type=click.Path(dir_okay=False), default=None)
def screen(
    reactions_path: str,
    structures_path: str,
    template_path: str,
    bounds_path: str,
    assumptions_path: str,
    enzymatic_yield: float,
    reference_recovery: float,
    cofactor_recycling: float,
    fair_fight: bool,
    frontier: bool,
    factor_paths: tuple[str, ...],
    synonym_paths: tuple[str, ...],
    output_path: str | None,
) -> None:
    """Screen a whole reaction database against one chemical-route template.

    Answers, for every enzymatic reaction in a class, how much solvent a
    chemical plant would have to recover before the enzyme stops winning.
    The output is a ranked shortlist of candidates for a real `compare`,
    not a set of verdicts -- see docs/screening.md.
    """
    from .bounds import BoundsError, load_bounds
    from .report import render_fair_fight, render_screen
    from .screen import (
        ScreenError,
        break_even_frontier,
        fair_fight_frontier,
        load_reactions,
        load_structures,
        load_template,
        screen_all,
    )

    ledger = _load_ledger_or_exit(assumptions_path)
    table = _load_factors_or_exit(factor_paths, synonym_paths)
    try:
        reactions, _ = load_reactions(reactions_path)
        structures = load_structures(structures_path)
        template = load_template(template_path)
    except ScreenError as exc:
        _fail(str(exc))
    try:
        bounds = load_bounds(bounds_path)
    except BoundsError as exc:
        _fail(str(exc))

    run = screen_all(
        reactions,
        template,
        structures,
        table,
        ledger.assumptions,
        bounds,
        enzymatic_yield=enzymatic_yield,
        reference_recovery=reference_recovery,
        cofactor_recycling=cofactor_recycling,
    )
    report = render_screen(run, reactions_path, bounds)
    if fair_fight:
        report += "\n" + render_fair_fight(
            fair_fight_frontier(
                reactions, template, structures, table, ledger.assumptions, bounds
            ),
            template,
        )
    if frontier:
        curve = break_even_frontier(
            reactions, template, structures, table, ledger.assumptions, bounds
        )
        report += "\n" + _render_frontier(curve)
    _write_output(report, output_path)


def _render_frontier(curve: list) -> str:
    """The class's verdict boundary, swept over enzymatic conversion.

    A single recovery threshold fixes conversion at 100% and hides that it
    was a choice. This shows what the enzymatic route gives up in
    solvent-recovery headroom for every point of conversion it loses.
    """
    lines = [
        "## Break-even frontier: conversion versus solvent recovery",
        "",
        "Each row re-screens the whole class at a different enzymatic "
        "conversion. The thresholds are the solvent recovery rates at which "
        "the verdict stops holding, so reading down the table shows how fast "
        "the enzymatic advantage erodes as the reactor gets more realistic.",
        "",
        "| enzymatic conversion | decided | min threshold | median | max |",
        "|---|---|---|---|---|",
    ]

    def pct(v: float | None) -> str:
        return f"{v * 100:.2f}%" if v is not None else "—"

    for p in curve:
        lines.append(
            f"| {p.enzymatic_yield * 100:.0f}% | {p.decided} | "
            f"{pct(p.min_threshold)} | {pct(p.median_threshold)} | "
            f"{pct(p.max_threshold)} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    main()
