"""Emission factor tables and material resolution (spec sections 6.2, 7.4)."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .schema import normalize_name

REQUIRED_COLUMNS = (
    "identifier",
    "name",
    "gwp_kgCO2e_per_kg",
    "source",
    "database_version",
    "region",
    "retrieved_date",
    "uncertainty_class",
)
OPTIONAL_COLUMNS = ("license", "notes")

#: Sources beginning with this marker carry no real LCA provenance. They exist
#: so the pipeline can be exercised end to end; every report that touches one
#: says so loudly.
ILLUSTRATIVE_MARKER = "ILLUSTRATIVE"


class FactorTableError(ValueError):
    pass


@dataclass(frozen=True)
class Factor:
    key: str
    identifier: str
    name: str
    gwp_kgCO2e_per_kg: float
    source: str
    database_version: str
    region: str
    retrieved_date: str
    uncertainty_class: str
    license: str = ""
    notes: str = ""
    table: str = ""

    @property
    def is_illustrative(self) -> bool:
        return self.source.strip().upper().startswith(ILLUSTRATIVE_MARKER)


@dataclass(frozen=True)
class Resolution:
    """Outcome of looking one material up in the factor tables."""

    key: str
    name: str
    factor: Factor | None
    #: "cas", "inchikey" or "name"; ``None`` when unresolved.
    matched_by: str | None = None

    @property
    def resolved(self) -> bool:
        return self.factor is not None


def _identifier_key(identifier: str) -> str:
    ident = identifier.strip()
    if not ident:
        raise FactorTableError("empty identifier")
    # InChIKeys are 14-10-1 uppercase blocks; anything else is treated as CAS.
    parts = ident.split("-")
    if len(parts) == 3 and len(parts[0]) == 14 and parts[0].isalpha():
        return f"inchikey:{ident.upper()}"
    return f"cas:{ident}"


@dataclass
class FactorTable:
    """The union of one or more CSV factor tables, indexed by key and by name."""

    by_key: dict[str, Factor] = field(default_factory=dict)
    by_name: dict[str, Factor] = field(default_factory=dict)
    #: path -> sha256 of the file, recorded in reports and lock files.
    sources: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, paths: list[str | Path]) -> "FactorTable":
        table = cls()
        for path in paths:
            table.load_file(path)
        return table

    def load_file(self, path: str | Path) -> None:
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        reader = csv.DictReader(text.splitlines())
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise FactorTableError(f"{p}: missing required column(s): {', '.join(missing)}")

        for lineno, row in enumerate(reader, start=2):
            source = (row.get("source") or "").strip()
            if not source:
                # Spec section 6.2: a row without provenance is never accepted.
                raise FactorTableError(f"{p}:{lineno}: 'source' must not be empty")
            try:
                gwp = float(row["gwp_kgCO2e_per_kg"])
            except (TypeError, ValueError) as exc:
                raise FactorTableError(
                    f"{p}:{lineno}: gwp_kgCO2e_per_kg is not a number: {row['gwp_kgCO2e_per_kg']!r}"
                ) from exc
            if gwp < 0:
                raise FactorTableError(f"{p}:{lineno}: gwp_kgCO2e_per_kg must not be negative")
            try:
                key = _identifier_key(row["identifier"])
            except FactorTableError as exc:
                raise FactorTableError(f"{p}:{lineno}: {exc}") from exc

            factor = Factor(
                key=key,
                identifier=row["identifier"].strip(),
                name=row["name"].strip(),
                gwp_kgCO2e_per_kg=gwp,
                source=source,
                database_version=(row.get("database_version") or "").strip(),
                region=(row.get("region") or "").strip(),
                retrieved_date=(row.get("retrieved_date") or "").strip(),
                uncertainty_class=(row.get("uncertainty_class") or "").strip() or "unknown",
                license=(row.get("license") or "").strip(),
                notes=(row.get("notes") or "").strip(),
                table=str(p),
            )
            if key in self.by_key and self.by_key[key].gwp_kgCO2e_per_kg != gwp:
                raise FactorTableError(
                    f"{p}:{lineno}: conflicting values for {key} "
                    f"({self.by_key[key].table} and {p}); resolve the conflict explicitly"
                )
            self.by_key[key] = factor
            self.by_name.setdefault(normalize_name(factor.name), factor)

        self.sources[str(p)] = digest

    def lookup(self, key: str, name: str) -> Resolution:
        if key in self.by_key:
            kind = key.split(":", 1)[0]
            return Resolution(key=key, name=name, factor=self.by_key[key], matched_by=kind)
        by_name = self.by_name.get(normalize_name(name))
        if by_name is not None:
            return Resolution(key=key, name=name, factor=by_name, matched_by="name")
        return Resolution(key=key, name=name, factor=None, matched_by=None)

    def fingerprint(self) -> str:
        """Order-independent hash of the *contents* of every table loaded.

        Deliberately independent of file paths: the same tables read from a
        different checkout, or via absolute rather than relative paths, must
        fingerprint identically, or a lock file stops being portable.
        """
        joined = "\n".join(sorted(self.sources.values()))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def default_factor_paths(root: Path | None = None) -> list[Path]:
    """Every CSV under ``data/factors`` of the installed/checked-out tree."""
    base = root or Path(__file__).resolve().parents[2]
    directory = base / "data" / "factors"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.csv"))


def resolve_materials(materials, table: FactorTable) -> dict[str, Resolution]:
    """Resolve every material in an adjusted inventory. Never invents a value."""
    return {m.key: table.lookup(m.key, m.name) for m in materials}
