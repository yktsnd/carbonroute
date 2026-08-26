import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from carbonroute.ledger import load_ledger  # noqa: E402
from carbonroute.resolve import FactorTable  # noqa: E402
from carbonroute.uncertainty import load_uncertainty  # noqa: E402

ANALYTIC = ROOT / "benchmarks" / "analytic"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture()
def analytic_ledger():
    return load_ledger(ANALYTIC / "ledger.yaml")


@pytest.fixture()
def analytic_table():
    return FactorTable.load([ANALYTIC / "factors.csv"])


@pytest.fixture()
def model():
    return load_uncertainty()
