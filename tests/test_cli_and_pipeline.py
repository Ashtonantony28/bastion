import pytest

from bastion.cli import main


def test_unknown_source_is_rejected(capsys):
    assert main(["ingest", "--source", "nope"]) == 2
    assert "unknown source" in capsys.readouterr().err


def test_fixtures_check_passes():
    assert main(["fixtures", "--check"]) == 0


def test_dagster_definitions_load():
    pytest.importorskip("dagster")
    from bastion.pipelines.definitions import defs

    keys = {k.to_user_string() for k in defs.resolve_asset_graph().get_all_asset_keys()}
    assert {"raw_fred", "raw_fdic_case_study", "lakehouse"} <= keys
