"""Markdown report and lock-file rendering (spec sections 9, 13).

This module never computes an emission value itself; it only formats
:class:`~carbonroute.compute.Comparison`/`RouteResult` objects (and the
:class:`~carbonroute.sensitivity.Threshold` list) that ``compute.py`` and
``sensitivity.py`` build. Deliberately duck-typed: the ``from __future__
import annotations`` postpones evaluation of the type hints below, so this
module carries no hard import on ``compute``/``sensitivity`` — it only needs
objects that look like their dataclasses.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:  # pragma: no cover - type checking only, no runtime import
    from .compute import Comparison, RouteResult
    from .ledger import AdjustedRoute
    from .resolve import FactorTable, Resolution
    from .schema import Ledger
    from .sensitivity import Threshold

_NOT_ISO_NOTICE = (
    "**This is not an ISO 14067-conformant calculation.** carbonroute is a "
    "screening-level, comparative tool: it estimates which of two synthetic "
    "routes has the lower cradle-to-gate GHG footprint under the assumptions "
    "stated below, and how confident that ranking is. It does not certify a "
    "Product Carbon Footprint, has not been through critical review, and must "
    "not be cited as an ISO 14067/14040 result."
)


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}g}"


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _confidence_word(p_a_lower: float) -> str:
    p = max(p_a_lower, 1.0 - p_a_lower)
    if p >= 0.95:
        return "very likely"
    if p >= 0.8:
        return "likely"
    return "marginally likely"


def _yaml_block(assumptions: Any) -> str:
    dumped = assumptions.model_dump(mode="json")
    return yaml.safe_dump(dumped, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _factor_table_section(comparison: "Comparison") -> list[str]:
    # Group the database_version(s) actually seen per table path, from the
    # resolved factors — FactorTable itself is not carried on Comparison.
    versions_by_path: dict[str, set[str]] = defaultdict(set)
    for res in comparison.resolutions.values():
        if res.factor is not None and res.factor.table:
            versions_by_path[res.factor.table].add(res.factor.database_version or "n/a")

    lines = ["## Factor tables", ""]
    lines.append("| path | sha256 | database version(s) seen |")
    lines.append("|---|---|---|")
    for path, digest in sorted(comparison.factor_sources.items()):
        versions = ", ".join(sorted(versions_by_path.get(path, {"(none used)"})))
        lines.append(f"| `{path}` | `{digest}` | {versions} |")
    lines.append("")
    lines.append(f"Combined fingerprint (order-independent): `{comparison.factor_fingerprint}`")
    lines.append("")
    return lines


def _provenance_breakdown(comparison: "Comparison") -> list[str]:
    """Share of the *delta*'s emissions attributable to each uncertainty class."""
    totals: dict[str, float] = defaultdict(float)
    for row in comparison.diff.rows:
        if row.resolved and row.factor is not None:
            totals[row.factor.uncertainty_class] += abs(row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg)

    grid = comparison.assumptions.grid_factor
    elec_contribution = abs(comparison.diff.delta_electricity_kWh * grid.value_kgCO2e_per_kWh)
    if elec_contribution > 0:
        totals[grid.uncertainty_class] += elec_contribution

    grand_total = sum(totals.values())
    lines = ["## Provenance breakdown of the resolution", ""]
    lines.append(
        "Share of the resolved delta's absolute GWP contribution "
        "(`|delta_mass * factor|`, electricity included under the grid "
        "factor's own uncertainty class) that comes from each provenance class:"
    )
    lines.append("")
    if grand_total <= 0:
        lines.append("_No resolved, non-cancelling delta contributions to break down._")
        lines.append("")
        return lines
    lines.append("| uncertainty class | share of absolute delta GWP | kgCO2e (abs) |")
    lines.append("|---|---|---|")
    for cls, value in sorted(totals.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {cls} | {_pct(value / grand_total)} | {_fmt(value)} |")
    lines.append("")
    n_unresolved = len(comparison.diff.delta_unresolved)
    if n_unresolved:
        lines.append(
            f"_{n_unresolved} delta material(s) are unresolved and excluded from this "
            "breakdown; see the warning below._"
        )
        lines.append("")
    return lines


def _warning_block(comparison: "Comparison") -> list[str]:
    illustrative = comparison.illustrative_keys
    unresolved = comparison.diff.delta_unresolved
    if not illustrative and not unresolved:
        return []
    lines = ["> **WARNING — read before trusting the conclusion below.**", ">"]
    if illustrative:
        lines.append(
            f"> {len(illustrative)} of the factors consumed in this comparison are "
            "**ILLUSTRATIVE placeholders**, not real LCA data:"
        )
        for key in sorted(illustrative):
            res = comparison.resolutions.get(key)
            label = res.name if res is not None else key
            lines.append(f"> - `{key}` ({label})")
        lines.append(">")
    if unresolved:
        lines.append(
            f"> {len(unresolved)} material(s) that materially differ between the routes "
            "have **no resolved factor** and are excluded from the statistics below, "
            "biasing the comparison by an unknown amount:"
        )
        for key in sorted(unresolved):
            lines.append(f"> - `{key}`")
        lines.append(">")
    lines.append("> Treat any ranking below as provisional until these are addressed.")
    lines.append("")
    return lines


def _conclusion(comparison: "Comparison", thresholds: "list[Threshold] | None") -> list[str]:
    stats = comparison.stats
    a, b = comparison.a, comparison.b
    lines = ["## Conclusion", ""]

    from .compute import unresolved_flip_factor

    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)

    if stats.verdict == "indeterminate":
        band = comparison.assumptions.indeterminate_band
        if stats.indeterminate_reason:
            lines.append(
                f"**The comparison is undecided**, because {stats.indeterminate_reason}. "
                f"No ranking is reported."
            )
            lines.append("")
            lines.append(
                f"The Monte Carlo over the resolved part alone gives "
                f"P(GWP({a.label}) < GWP({b.label})) {_fmt_probability(stats.p_a_lower, stats.iterations)}. That number "
                f"describes {stats.coverage_mass_fraction * 100:.1f}% of the differing mass and "
                f"says nothing about the rest, which is why it is not the conclusion."
            )
        else:
            lines.append(
                f"**The comparison is undecided.** P(GWP({a.label}) < GWP({b.label})) "
                f"{_fmt_probability(stats.p_a_lower, stats.iterations)}, inside the configured indeterminate band "
                f"[{band.low}, {band.high}]. No ranking is reported."
            )
        lines.append("")
        lines.extend(_flip_lines(flip))
        lines.append("What would settle it:")
        lines.append("")
        unresolved_rows = sorted(
            (r for r in comparison.diff.rows if not r.resolved),
            key=lambda r: -abs(r.delta_mass_kg),
        )
        if unresolved_rows:
            lines.append("- Largest unresolved delta materials (need a factor):")
            for row in unresolved_rows[:8]:
                lines.append(
                    f"  - `{row.key}` ({row.name}, role={row.role}): "
                    f"delta mass {row.delta_mass_kg:+.4g} kg/FU"
                )
        else:
            lines.append("- No unresolved materials are driving the delta; the tie is genuine "
                          "under the current uncertainty model.")
        if thresholds:
            crossing = sorted(
                (t for t in thresholds if t.crossing is not None),
                key=lambda t: abs(t.baseline - t.crossing),
            )
            if crossing:
                lines.append("- Reversal thresholds nearest to their crossing point:")
                for t in crossing[:5]:
                    lines.append(
                        f"  - {t.label}: baseline {_fmt(t.baseline)}, crosses P=0.5 at "
                        f"{_fmt(t.crossing)}"
                    )
        lines.append("")
        return lines

    winner = a if stats.verdict == "A<B" else b
    loser = b if stats.verdict == "A<B" else a
    p_win = stats.p_a_lower if stats.verdict == "A<B" else 1.0 - stats.p_a_lower
    lines.append(
        f"**{winner.label} is {_confidence_word(p_win)} lower** than {loser.label} "
        f"(P {_fmt_probability(p_win, stats.iterations)})."
    )
    lines.append("")
    lines.append(
        f"Delta ({a.label} - {b.label}): median {_fmt(stats.delta_median)} kgCO2e/FU, "
        f"90% interval [{_fmt(stats.delta_p05)}, {_fmt(stats.delta_p95)}], "
        f"{stats.iterations} draws, seed {stats.seed}."
    )
    if stats.excluded_keys:
        lines.append(
            f"({len(stats.excluded_keys)} unresolved delta material(s) excluded from the "
            "Monte Carlo — see the warning above.)"
        )
    lines.append("")
    lines.extend(_flip_lines(flip))
    return lines


def _flip_lines(flip) -> list[str]:
    """How much the unresolved part of the delta would have to carry to reverse things."""
    if flip.unresolved_delta_mass_kg == 0.0 and flip.breakeven_kgCO2e_per_kg is None:
        return []
    lines = ["### What the missing data would have to be", ""]
    lines.append(
        f"Resolved part of the difference: {_fmt(flip.resolved_delta_kgCO2e)} kgCO2e/FU. "
        f"Unresolved differing mass: {_fmt(flip.unresolved_delta_mass_kg)} kg/FU (signed)."
    )
    lines.append("")
    lines.append(flip.note)
    lines.append("")
    lines.append(
        "_No factor was assumed for the unresolved materials. This states the "
        "break-even value they would need to average, which is a question the data "
        "can answer, rather than filling the gap with a number it cannot._"
    )
    lines.append("")
    return lines


def _route_body(rr: "RouteResult") -> list[str]:
    lines = [f"### {rr.label} (`{rr.name}`)", ""]
    lines.append(
        f"Indicative total: **{_fmt(rr.total_kgCO2e)} kgCO2e/FU** "
        f"(materials {_fmt(rr.material_gwp_kgCO2e)} + electricity "
        f"{_fmt(rr.electricity_gwp_kgCO2e)}, resolved rows only — see warnings above "
        "for what this omits). This absolute figure is indicative context, not the "
        "tool's conclusion."
    )
    lines.append("")
    lines.append("| material | role | mass_kg/FU | factor kgCO2e/kg | gwp kgCO2e/FU |")
    lines.append("|---|---|---|---|---|")
    for row in rr.materials:
        factor_val = _fmt(row.factor.gwp_kgCO2e_per_kg) if row.factor else "UNRESOLVED"
        gwp_val = _fmt(row.gwp_kgCO2e) if row.gwp_kgCO2e is not None else "-"
        lines.append(f"| {row.name} | {row.role} | {_fmt(row.mass_kg)} | {factor_val} | {gwp_val} |")
    lines.append("")
    lines.append("By role (resolved only):")
    lines.append("")
    lines.append("| role | kgCO2e/FU |")
    lines.append("|---|---|")
    for role, value in sorted(rr.by_role.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {role} | {_fmt(value)} |")
    lines.append("")
    if rr.missing:
        lines.append(f"Missing factors: {', '.join(f'`{k}`' for k in rr.missing)}")
        lines.append("")
    return lines


def _delta_table(comparison: "Comparison") -> list[str]:
    diff = comparison.diff
    lines = ["## Contribution to the delta, by material", ""]
    lines.append(f"{comparison.a.label} - {comparison.b.label}, materials with a non-zero "
                 "adjusted-mass difference only:")
    lines.append("")
    lines.append("| material | role | mass_a_kg | mass_b_kg | delta_mass_kg | delta gwp kgCO2e |")
    lines.append("|---|---|---|---|---|---|")
    for row in diff.rows:
        if row.resolved and row.factor is not None:
            delta_gwp = _fmt(row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg)
        else:
            delta_gwp = "UNRESOLVED"
        lines.append(
            f"| {row.name} | {row.role} | {_fmt(row.mass_a_kg)} | {_fmt(row.mass_b_kg)} | "
            f"{row.delta_mass_kg:+.4g} | {delta_gwp} |"
        )
    if diff.delta_electricity_kWh:
        lines.append(
            f"| _electricity_ | - | - | - | {diff.delta_electricity_kWh:+.4g} kWh | "
            f"{_fmt(diff.delta_electricity_kWh * comparison.assumptions.grid_factor.value_kgCO2e_per_kWh)} |"
        )
    lines.append("")

    by_role: dict[str, float] = defaultdict(float)
    for row in diff.rows:
        if row.resolved and row.factor is not None:
            by_role[row.role] += row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg
    lines.append("### Contribution to the delta, by role")
    lines.append("")
    lines.append("| role | delta gwp kgCO2e |")
    lines.append("|---|---|")
    for role, value in sorted(by_role.items(), key=lambda kv: -abs(kv[1])):
        lines.append(f"| {role} | {_fmt(value)} |")
    lines.append("")

    if diff.common_unresolved:
        lines.append(
            "Unresolved materials whose masses cancel between routes (informational, "
            "not a warning — they do not affect the delta): "
            + ", ".join(f"`{k}`" for k in diff.common_unresolved)
        )
        lines.append("")
    return lines


def _thresholds_section(thresholds: "list[Threshold] | None") -> list[str]:
    if thresholds is None:
        return []
    lines = ["## Reversal thresholds", ""]
    if not thresholds:
        lines.append("_No threshold scan was requested or none applied to this ledger._")
        lines.append("")
        return lines
    lines.append("| variable | baseline | range | crossing (P=0.5) | P at low | P at high | note |")
    lines.append("|---|---|---|---|---|---|---|")
    for t in thresholds:
        crossing = _fmt(t.crossing) if t.crossing is not None else "none in range"
        lines.append(
            f"| {t.label} | {_fmt(t.baseline)} | [{_fmt(t.low)}, {_fmt(t.high)}] | {crossing} | "
            f"{_fmt(t.p_at_low, 3)} | {_fmt(t.p_at_high, 3)} | {t.message} |"
        )
    lines.append("")
    return lines


def render_report(comparison: "Comparison", thresholds: "list[Threshold] | None", ledger_path: str) -> str:
    """Render the full Markdown comparison report (spec section 9).

    Section order is binding: (1) the not-ISO-14067 notice, (2) the full
    applied assumptions, (3) factor table versions/hashes, (4) the
    provenance breakdown — *then* a warning block if warranted, *then* the
    conclusion as a ranking-plus-probability. Everything after that
    (absolute totals, material/role tables, thresholds) is supporting body.
    """
    a, b = comparison.a, comparison.b
    lines: list[str] = []
    lines.append(f"# carbonroute comparison: {a.label} vs {b.label}")
    lines.append("")
    lines.append(f"> {_NOT_ISO_NOTICE}")
    lines.append("")
    lines.append(f"Ledger: `{ledger_path}`")
    lines.append("")

    lines.append("## Applied assumptions")
    lines.append("")
    lines.append("```yaml")
    lines.append(_yaml_block(comparison.assumptions).rstrip("\n"))
    lines.append("```")
    lines.append("")

    lines.extend(_factor_table_section(comparison))
    lines.extend(render_conflicts(comparison.factor_conflicts))
    lines.extend(_provenance_breakdown(comparison))
    lines.extend(_warning_block(comparison))
    lines.extend(_conclusion(comparison, thresholds))

    lines.append("---")
    lines.append("")
    lines.append("## Route totals and contributions (indicative detail)")
    lines.append("")
    lines.extend(_route_body(a))
    lines.extend(_route_body(b))
    lines.extend(_delta_table(comparison))
    lines.extend(_thresholds_section(thresholds))

    return "\n".join(lines).rstrip("\n") + "\n"


def render_resolution_table(routes: "dict[str, RouteResult]", table: "FactorTable", show_missing: bool) -> str:
    """Render the ``resolve`` command's report: what resolved, what did not."""
    lines: list[str] = ["# Factor resolution", ""]
    lines.append(f"Factor tables loaded: {len(table.sources)}; fingerprint `{table.fingerprint()}`")
    lines.append("")
    for path, digest in sorted(table.sources.items()):
        lines.append(f"- `{path}` sha256:`{digest}`")
    lines.append("")

    for name, rr in routes.items():
        resolved = [m for m in rr.materials if m.factor is not None]
        missing = [m for m in rr.materials if m.factor is None]
        lines.append(f"## {name} ({rr.label})")
        lines.append("")
        lines.append(f"Resolved {len(resolved)}/{len(rr.materials)} material(s).")
        lines.append("")
        if resolved:
            lines.append("| key | name | role | mass_kg/FU | gwp kgCO2e/kg | source | uncertainty_class |")
            lines.append("|---|---|---|---|---|---|---|")
            for m in resolved:
                assert m.factor is not None
                lines.append(
                    f"| `{m.key}` | {m.name} | {m.role} | {_fmt(m.mass_kg)} | "
                    f"{_fmt(m.factor.gwp_kgCO2e_per_kg)} | {m.factor.source} | "
                    f"{m.factor.uncertainty_class} |"
                )
            lines.append("")
        if missing:
            lines.append(
                f"**Missing ({len(missing)}):** "
                + ", ".join(f"`{m.key}` ({m.name})" for m in sorted(missing, key=lambda x: x.key))
            )
            lines.append("")
            if show_missing:
                lines.append("| key | name | role | mass_kg/FU |")
                lines.append("|---|---|---|---|")
                for m in sorted(missing, key=lambda x: x.key):
                    lines.append(f"| `{m.key}` | {m.name} | {m.role} | {_fmt(m.mass_kg)} |")
                lines.append("")
        else:
            lines.append("No missing factors.")
            lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_lock(
    ledger: "Ledger",
    ledger_path: str,
    table: "FactorTable",
    resolutions: "dict[str, Resolution]",
    comparison: "Comparison | None" = None,
) -> dict:
    """Build the JSON-serialisable lock payload (spec sections 8, 9, 13).

    Pins everything needed to reproduce a resolution/comparison byte-for-byte:
    ledger contents, factor table contents, the uncertainty config, the
    resolved value+provenance for every material key, and the RNG
    seed/iteration count. Does not itself run any computation; it only
    hashes and restates what was already computed.
    """
    # The uncertainty config path/hash is required by spec but not carried on
    # Comparison; load the default config here so it is always represented,
    # even for a `lock` that did not run a comparison. A caller who resolved
    # against a --uncertainty override would need that override reflected by
    # passing a Comparison through (its RNG seed/iterations are taken from
    # `comparison.stats` below); the config file itself is still the default
    # unless the CLI is extended to thread an override through.
    from .uncertainty import load_uncertainty  # local import: keeps report.py decoupled

    uncertainty_model = load_uncertainty()

    resolved_payload = {}
    for key in sorted(resolutions):
        res = resolutions[key]
        if res.factor is None:
            resolved_payload[key] = {"resolved": False, "matched_by": None}
        else:
            f = res.factor
            resolved_payload[key] = {
                "resolved": True,
                "matched_by": res.matched_by,
                "gwp_kgCO2e_per_kg": f.gwp_kgCO2e_per_kg,
                "uncertainty_class": f.uncertainty_class,
                "source": f.source,
                "database_version": f.database_version,
                "table": _portable_path(f.table),
                "is_illustrative": f.is_illustrative,
            }

    if comparison is not None:
        rng = {"seed": comparison.stats.seed, "iterations": comparison.stats.iterations}
        comparison_payload: dict[str, Any] | None = {
            "a": comparison.a.name,
            "b": comparison.b.name,
            "verdict": comparison.stats.verdict,
            "p_a_lower": comparison.stats.p_a_lower,
            "delta_median_kgCO2e": comparison.stats.delta_median,
        }
    else:
        mc = ledger.assumptions.monte_carlo
        rng = {"seed": mc.seed, "iterations": mc.iterations}
        comparison_payload = None

    return {
        "schema_version": ledger.schema_version,
        "tool_version": _tool_version(),
        "ledger": {"path": _portable_path(ledger_path), "sha256": _sha256_file(ledger_path)},
        "factor_tables": {
            "sources": {_portable_path(p): d for p, d in sorted(table.sources.items())},
            "fingerprint": table.fingerprint(),
            # Which source won a disagreement changes the numbers, so it is
            # pinned alongside the tables themselves.
            "conflicts": [
                {
                    "key": c.key,
                    "used": {
                        "gwp_kgCO2e_per_kg": c.kept.gwp_kgCO2e_per_kg,
                        "source": c.kept.source,
                        "table": _portable_path(c.kept.table),
                    },
                    "not_used": {
                        "gwp_kgCO2e_per_kg": c.rejected.gwp_kgCO2e_per_kg,
                        "source": c.rejected.source,
                        "table": _portable_path(c.rejected.table),
                    },
                }
                for c in sorted(table.conflicts, key=lambda c: c.key)
            ],
        },
        "uncertainty_config": {
            "path": _portable_path(uncertainty_model.path),
            "sha256": _sha256_file(uncertainty_model.path),
        },
        "resolutions": resolved_payload,
        "rng": rng,
        "comparison": comparison_payload,
    }


def _portable_path(path: str) -> str:
    """Path as it should appear in a lock file.

    A lock file is meant to travel with a paper or a report, so an absolute
    path from whoever happened to run the tool is noise at best and a privacy
    leak at worst. Paths under the working directory become relative; anything
    else (a packaged default, a table elsewhere on disk) is reduced to its file
    name. The accompanying sha256 is what actually pins the content.
    """
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return p.name


def _fmt_probability(p: float, iterations: int) -> str:
    """Render a sampled probability without claiming more than sampling gives.

    A Monte Carlo estimate that lands on 0 or 1 means "no draw fell the other
    way in this many draws", not certainty, so those cases are reported as a
    bound at the resolution the draw count actually supports.
    """
    resolution = 1.0 / max(iterations, 1)
    if p >= 1.0 - resolution:
        return f"> {1.0 - resolution:.4g}"
    if p <= resolution:
        return f"< {resolution:.4g}"
    return f"= {p:.3f}"


def _tool_version() -> str:
    from . import __version__

    return __version__


def dump_lock_json(lock: dict) -> str:
    """Deterministic JSON rendering for the ``lock`` command (spec section 8)."""
    return json.dumps(lock, sort_keys=True, indent=2) + "\n"


def render_coverage(cov, a_name: str, b_name: str, table: "FactorTable") -> str:
    """Render the coverage of a delta set (spec section 14's last open item)."""
    lines = [
        f"# Factor coverage of the delta set: `{a_name}` vs `{b_name}`",
        "",
        f"Factor tables loaded: {len(table.sources)}; "
        f"fingerprint `{table.fingerprint()}`",
        "",
        f"- Materials whose adjusted mass differs between the routes: **{cov.delta_material_count}**",
        f"- Resolved to a factor: **{cov.resolved_count}** "
        f"({cov.count_fraction * 100:.1f}% by count)",
        f"- Share of the absolute delta mass that is resolved: "
        f"**{cov.mass_fraction * 100:.1f}%** "
        f"({_fmt(cov.resolved_mass_kg)} of {_fmt(cov.delta_mass_kg)} kg/FU)",
        "",
        "> Mass coverage is not impact coverage. A catalyst charged at a fraction of a",
        "> percent by mass can dominate a route's footprint, and no mass-based measure",
        "> will show it. Read the per-role table below before treating a high",
        "> percentage as reassurance.",
        "",
        "| role | resolved kg/FU | delta kg/FU | resolved share |",
        "|---|---|---|---|",
    ]
    for role, (resolved, total) in cov.by_role.items():
        share = f"{resolved / total * 100:.1f}%" if total else "n/a"
        lines.append(f"| {role} | {_fmt(resolved)} | {_fmt(total)} | {share} |")
    lines.append("")

    if cov.unresolved:
        lines.append("## Unresolved materials in the delta set")
        lines.append("")
        lines.append("Largest first. Each of these is a gap in the comparison, not a zero.")
        lines.append("")
        lines.append("| material | role | delta mass kg/FU | key |")
        lines.append("|---|---|---|---|")
        for key, name, role, mass in cov.unresolved:
            lines.append(f"| {name} | {role} | {_fmt(mass)} | `{key}` |")
        lines.append("")
    else:
        lines.append("Every material in the delta set resolved to a factor.")
        lines.append("")
    return "\n".join(lines)


def render_conflicts(conflicts) -> list[str]:
    """Substances the loaded tables disagree about.

    Not an error and not a footnote. Two independent public sources differing
    about the same material measures how far apart openly available data sits,
    which is one of the things this project set out to find out. The first table
    in sorted path order supplies the value used; both are shown.
    """
    if not conflicts:
        return []
    lines = [
        "## Sources disagree",
        "",
        f"{len(conflicts)} substance(s) appear in more than one loaded table with "
        "different values. The value used is the one from the first table in sorted "
        "path order; the alternative is shown so the spread is visible.",
        "",
        "| substance | used | from | alternative | from | ratio |",
        "|---|---|---|---|---|---|",
    ]
    for c in sorted(conflicts, key=lambda c: c.key):
        lines.append(
            f"| {c.kept.name} (`{c.key}`) | {_fmt(c.kept.gwp_kgCO2e_per_kg)} | "
            f"{c.kept.source} | {_fmt(c.rejected.gwp_kgCO2e_per_kg)} | "
            f"{c.rejected.source} | {c.ratio:.2f}x |"
        )
    lines.append("")
    return lines
