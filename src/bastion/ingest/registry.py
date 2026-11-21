"""Named ingest sources, so the CLI and the Dagster assets share one definition."""

from __future__ import annotations

from collections.abc import Callable

from bastion.ingest import fdic, fed_scenarios, fred, treasury
from bastion.ingest.base import DownloadItem, HttpClient

SourceFn = Callable[[HttpClient, list[str]], list[DownloadItem]]


def _quarters(client: HttpClient, quarters: list[str]) -> list[DownloadItem]:
    if not quarters:
        raise ValueError("fdic-quarter needs --quarters YYYYMMDD[,YYYYMMDD...]")
    return [fdic.financials_quarter_item(client, q) for q in quarters]


def _alm_quarters(client: HttpClient, quarters: list[str]) -> list[DownloadItem]:
    if not quarters:
        raise ValueError("fdic-alm-quarter needs --quarters YYYYMMDD[,YYYYMMDD...]")
    return [fdic.alm_quarter_item(client, q) for q in quarters]


SOURCES: dict[str, SourceFn] = {
    "fred": lambda c, _q: fred.items(c),
    "fed-scenarios": lambda c, _q: fed_scenarios.items(c),
    "treasury": lambda c, _q: treasury.items(c),
    "fdic-failures": lambda c, _q: [fdic.failures_item(c)],
    "fdic-institutions": lambda c, _q: [fdic.institutions_item(c)],
    "fdic-case-study": lambda c, _q: [fdic.financials_case_study_item(c)],
    "fdic-quarter": _quarters,
    "fdic-alm-case-study": lambda c, _q: [fdic.alm_case_study_item(c)],
    "fdic-alm-quarter": _alm_quarters,
}

# The default set: everything M0 needs, no credentials required.
CORE = ["fred", "fed-scenarios", "treasury", "fdic-failures", "fdic-case-study"]
