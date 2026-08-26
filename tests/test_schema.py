"""The ledger is the contract with the user; these tests pin its edges."""

import pytest
from pydantic import ValidationError

from carbonroute.schema import (
    Ledger,
    MaterialInput,
    Step,
    cas_checksum_ok,
    material_key,
    normalize_name,
)


@pytest.mark.parametrize(
    "cas,ok",
    [
        ("108-88-3", True),
        ("96-47-9", True),
        ("71-43-2", True),
        ("7732-18-5", True),
        ("108-88-4", False),   # wrong check digit
        ("108-8-3", False),    # malformed middle block
        ("toluene", False),
    ],
)
def test_cas_checksum(cas, ok):
    assert cas_checksum_ok(cas) is ok


def test_material_input_rejects_bad_cas():
    with pytest.raises(ValidationError):
        MaterialInput(name="toluene", cas="108-88-4", mass_kg=1.0, role="solvent")


def test_material_key_prefers_cas_and_normalizes_names():
    assert material_key("108-88-3", "Toluene") == "cas:108-88-3"
    assert material_key(None, "  Substrate   A ") == "name:substrate a"
    assert normalize_name("2-MeTHF") == "2-methf"


def test_recovery_is_solvent_only():
    MaterialInput(name="thf", cas=None, mass_kg=1.0, role="solvent", recovery=0.5)
    with pytest.raises(ValidationError):
        MaterialInput(name="pd", cas=None, mass_kg=1.0, role="catalyst", recovery=0.5)


def test_yield_bounds():
    Step.model_validate({"id": 1, "yield": 1.0})
    for bad in (0.0, -0.1, 1.2):
        with pytest.raises(ValidationError):
            Step.model_validate({"id": 1, "yield": bad})


def test_unknown_field_is_rejected(analytic_ledger):
    """A typo in a key must fail loudly rather than be silently ignored."""
    raw = analytic_ledger.model_dump(by_alias=True)
    raw["assumptions"]["solvent_recovery_defualt"] = 0.5
    with pytest.raises(ValidationError):
        Ledger.model_validate(raw)


def test_schema_version_must_be_known(analytic_ledger):
    raw = analytic_ledger.model_dump(by_alias=True)
    raw["schema_version"] = "9.9"
    with pytest.raises(ValidationError):
        Ledger.model_validate(raw)


def test_duplicate_step_ids_rejected(analytic_ledger):
    raw = analytic_ledger.model_dump(by_alias=True)
    raw["routes"]["a"]["steps"][1]["id"] = raw["routes"]["a"]["steps"][0]["id"]
    with pytest.raises(ValidationError):
        Ledger.model_validate(raw)
