"""Live checks against public sources. Run with `pytest -m network`; deselected in CI."""

import pytest

from bastion.ingest import fred
from bastion.ingest.base import HttpClient

pytestmark = pytest.mark.network


def test_fred_unrate_downloads():
    data = fred.items(HttpClient(), series=["UNRATE"])[0].fetch()
    assert data.startswith(b"observation_date,UNRATE")
