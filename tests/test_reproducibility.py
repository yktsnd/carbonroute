"""The non-API route: data/raw/ must actually back up what it claims to.

These tests do not touch the network — they check that the *evidence* of a
past live run is internally consistent: every manifest entry has a payload
file on disk, and every source the reproducibility doc claims is populated
actually is. If a future commit accidentally .gitignores data/raw/ or drops
a payload file, this is what catches it before an --offline user does.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

#: Sources docs/reproducibility.md claims are populated. Keep in sync with it;
#: a source moving from "not yet populated" to populated should update both.
EXPECTED_POPULATED = {
    "ademe_base_carbone",
    "probas_gemis",
    "pubchem",
}

#: Known gap, tracked at https://github.com/yktsnd/carbonroute/issues/1.
KNOWN_GAPS = {"uslci"}


def test_snapshot_module_is_importable():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import _snapshot  # noqa: F401


@pytest.mark.parametrize("source", sorted(EXPECTED_POPULATED))
def test_manifest_exists_and_is_non_empty(source):
    manifest_path = RAW / source / "manifest.json"
    assert manifest_path.exists(), f"data/raw/{source}/manifest.json is missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest, f"data/raw/{source}/manifest.json has no entries"


@pytest.mark.parametrize("source", sorted(EXPECTED_POPULATED))
def test_every_manifest_entry_has_its_payload_file(source):
    """A manifest entry with no matching .bin is a snapshot that lies."""
    source_dir = RAW / source
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in manifest:
        payload = source_dir / f"{key}.bin"
        assert payload.exists(), f"{source}: manifest references {key} but {payload} is missing"


@pytest.mark.parametrize("source", sorted(EXPECTED_POPULATED))
def test_manifest_entries_have_no_leaked_credentials(source):
    """An API-key-bearing URL must never appear in a committed manifest."""
    manifest_path = RAW / source / "manifest.json"
    text = manifest_path.read_text(encoding="utf-8")
    assert "api_key=" not in text or "api_key=REDACTED" in text or True
    # Specifically: no query parameter value that looks like a live secret.
    import re

    for match in re.finditer(r"api_key=([^&\"'\s]+)", text):
        assert match.group(1) in {"REDACTED", "DEMO_KEY"}, (
            f"{source}: manifest.json appears to contain a live api_key value "
            f"({match.group(1)!r}) instead of a redacted placeholder"
        )


def test_known_gaps_are_not_silently_populated_or_stale():
    """If uslci's snapshot gets populated, the docs and this test should both know."""
    for source in KNOWN_GAPS:
        manifest_path = RAW / source / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert not manifest, (
                f"data/raw/{source}/manifest.json is now populated — update "
                "EXPECTED_POPULATED here, docs/reproducibility.md's table, and "
                "close https://github.com/yktsnd/carbonroute/issues/1"
            )


def test_letermovir_cas_cache_is_populated_and_matches_the_committed_ledger():
    """The benchmark ledger's own reproducibility path, checked the same way."""
    cache_path = RAW / "letermovir_cas_cache.json"
    assert cache_path.exists(), "data/raw/letermovir_cas_cache.json is missing"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache, "letermovir CAS cache has no entries"

    import yaml

    ledger = yaml.safe_load((ROOT / "benchmarks" / "letermovir" / "ledger.yaml").read_text())
    names_in_ledger = {
        item["name"]
        for route in ledger["routes"].values()
        for step in route["steps"]
        for item in step.get("inputs", [])
    }
    # Every material the ledger actually charges a CAS to must trace back to a
    # cached resolution — that is the whole point of freezing it.
    named_with_cas = {
        item["name"]
        for route in ledger["routes"].values()
        for step in route["steps"]
        for item in step.get("inputs", [])
        if item.get("cas")
    }
    for name in named_with_cas:
        assert name in cache, f"{name!r} has a CAS in the ledger but no entry in the frozen cache"
        assert cache[name]["cas"], f"{name!r}: cached entry has no CAS, but the ledger does"


def test_letermovir_source_material_is_committed():
    """The benchmark's entire empirical basis must survive this session ending."""
    src_dir = ROOT / "benchmarks" / "letermovir" / "source-material"
    workbook = src_dir / "ja5c14470_si_002.xlsx"
    assert workbook.exists(), "the CC BY licensed SI workbook is not committed"
    assert workbook.stat().st_size > 100_000, "workbook looks truncated"
    assert (src_dir / "README.md").exists(), "source-material/README.md (attribution) is missing"


def test_ledger_reproduces_with_zero_arguments_and_zero_network(tmp_path):
    """The strongest reproducibility claim this repo makes, checked directly.

    No workbook path, no --cas-cache path, nothing but --offline and --out:
    everything else must come from files already committed to the repo.
    """
    import subprocess
    import sys

    out = tmp_path / "ledger.yaml"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_letermovir_ledger.py"),
         "--out", str(out), "--offline"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    committed = (ROOT / "benchmarks" / "letermovir" / "ledger.yaml").read_text()
    assert out.read_text() == committed, (
        "zero-argument --offline extraction no longer reproduces the committed ledger"
    )
