"""dbt build over the committed fixtures, then spot-check the marts."""

import duckdb
import pytest

from bastion import fixtures, paths
from bastion.cli import run_dbt


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    import os

    os.environ["BASTION_DATA"] = str(tmp_path_factory.mktemp("lake"))
    assert run_dbt("ci"), "dbt build on fixtures failed"
    con = duckdb.connect(str(paths.warehouse_path("ci")))
    yield con
    con.close()


def test_failed_fixture_bank_flagged_and_stops_filing(warehouse):
    rows = warehouse.execute(
        "select max(repdte), bool_and(failed_ever) from bank_quarter where cert = ?",
        [fixtures.FIXTURE_FAILED_CERT],
    ).fetchone()
    assert str(rows[0]) == "2022-12-31" and rows[1] is True


def test_unrealized_losses_computed(warehouse):
    v = warehouse.execute(
        "select securities_unrealized_gain_k from bank_quarter where cert = ? order by repdte desc limit 1",
        [fixtures.FIXTURE_FAILED_CERT],
    ).fetchone()[0]
    assert v < 0


def test_scenarios_have_13_quarters(warehouse):
    n = warehouse.execute(
        "select count(distinct quarter_end) from scenario_paths where scenario = 'severely_adverse'"
    ).fetchone()[0]
    assert n == 13


def test_treasury_tenor_union_by_name(warehouse):
    tenors = {
        r[0]
        for r in warehouse.execute(
            "select distinct tenor_months from treasury_par_curve"
        ).fetchall()
    }
    assert 4.0 in tenors and 360.0 in tenors


def test_macro_quarterly_has_all_fixture_series(warehouse):
    n = warehouse.execute("select count(distinct series_id) from macro_quarterly").fetchone()[0]
    assert n == len(fixtures.SERIES)


def test_ews_label_marks_quarters_before_failure(warehouse):
    rows = warehouse.execute(
        "select repdte, fail_within_4q from ews_features where cert = ? order by repdte",
        [fixtures.FIXTURE_FAILED_CERT],
    ).fetchall()
    labelled = [str(d) for d, f in rows if f]
    # fails 2023-03-10: quarters ending 2022-03-31 .. 2022-12-31 are within four quarters
    assert labelled == ["2022-03-31", "2022-06-30", "2022-09-30", "2022-12-31"]


def test_bank_institution_names(warehouse):
    assert warehouse.execute("select count(*) from bank_institution").fetchone()[0] > 0
