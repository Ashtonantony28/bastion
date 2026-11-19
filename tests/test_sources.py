import json

import pytest

from bastion.ingest import fdic, fed_scenarios, fred, treasury
from bastion.ingest.registry import CORE, SOURCES


class FakeClient:
    """Serves canned FDIC pages; records calls."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.pages.pop(0)


def _page(rows, total):
    return json.dumps({"meta": {"total": total}, "data": [{"data": r} for r in rows]}).encode()


def test_fdic_pagination_collects_all_pages():
    client = FakeClient([_page([{"CERT": 2}], 3), _page([{"CERT": 1}], 3), _page([{"CERT": 3}], 3)])
    rows = fdic.fetch_all(client, "financials", ["CERT"])
    assert [r["CERT"] for r in rows] == [2, 1, 3]
    assert [c[1]["offset"] for c in client.calls] == [0, 1, 2]


def test_fdic_csv_is_order_independent():
    rows = [
        {"CERT": 10, "REPDTE": "20221231", "X": None},
        {"CERT": 2, "REPDTE": "20221231", "X": 1.5},
    ]
    a = fdic.to_csv(rows, ["CERT", "REPDTE", "X"], key=fdic._fin_key)
    b = fdic.to_csv(rows[::-1], ["CERT", "REPDTE", "X"], key=fdic._fin_key)
    assert a == b
    assert a.decode().splitlines() == ["CERT,REPDTE,X", "2,20221231,1.5", "10,20221231,"]


def test_fed_scenarios_rejects_html_error_page():
    class C:
        def get(self, url, params=None):
            return b"\xef\xbb\xbf<!doctype html>"

    with pytest.raises(RuntimeError, match="did not return a scenario CSV"):
        fed_scenarios.items(C(), years=[2026])[0].fetch()


def test_fed_scenarios_accepts_bom_csv():
    class C:
        def get(self, url, params=None):
            return b"\xef\xbb\xbfScenario Name,Date,X\n"

    assert fed_scenarios.items(C(), years=[2026])[0].fetch().endswith(b"X\n")


def test_fred_window_is_fixed():
    item = fred.items(FakeClient([]), series=["UNRATE"])[0]
    assert item.relpath == "fred/UNRATE.csv"
    assert f"coed={fred.FRED_END}" in item.url


def test_treasury_paths():
    assert [i.relpath for i in treasury.items(FakeClient([]), years=[2024])] == [
        "treasury/par_curve_2024.csv"
    ]


def test_core_sources_registered():
    assert set(CORE) <= set(SOURCES)
    with pytest.raises(ValueError):
        SOURCES["fdic-quarter"](FakeClient([]), [])
