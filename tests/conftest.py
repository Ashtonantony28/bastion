import pytest


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path, monkeypatch):
    """Every test gets its own BASTION_DATA so nothing touches a real cache."""
    monkeypatch.setenv("BASTION_DATA", str(tmp_path / "data"))
