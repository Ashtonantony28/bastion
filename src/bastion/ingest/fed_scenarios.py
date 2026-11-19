"""Federal Reserve supervisory stress-test scenarios (DFAST/CCAR), domestic variables.

File names change from year to year, so each year's URLs are listed explicitly rather than
guessed. Add a year here as a reviewed change when the Fed publishes it.
"""

from __future__ import annotations

from functools import partial

from bastion.ingest.base import DownloadItem, HttpClient

BASE = "https://www.federalreserve.gov/supervisionreg/files/"

# year -> scenario key -> file name
FILES: dict[int, dict[str, str]] = {
    2025: {
        "historic": "2025-Table_1A_Historic_Domestic.csv",
        "baseline": "2025-Table_2A_Supervisory_Baseline_Domestic.csv",
        "severely_adverse": "2025-Table_3A_Supervisory_Severely_Adverse_Domestic.csv",
    },
    2026: {
        "historic": "2026_Final_Historic_Domestic.csv",
        "baseline": "2026_Final_Supervisory_Baseline_Domestic.csv",
        "severely_adverse": "2026_Final_Supervisory_Severely_Adverse_Domestic.csv",
    },
}

EXPECTED_HEADER_PREFIX = b"Scenario Name,Date,"


def _checked(client: HttpClient, url: str) -> bytes:
    data = client.get(url)
    if not data.lstrip(b"\xef\xbb\xbf").startswith(EXPECTED_HEADER_PREFIX):
        raise RuntimeError(f"{url} did not return a scenario CSV (got {data[:40]!r})")
    return data


def items(client: HttpClient, years: list[int] | None = None) -> list[DownloadItem]:
    out = []
    for year in years or sorted(FILES):
        for key, fname in sorted(FILES[year].items()):
            url = BASE + fname
            out.append(
                DownloadItem(
                    relpath=f"fed_scenarios/{year}/{key}_domestic.csv",
                    url=url,
                    fetch=partial(_checked, client, url),
                )
            )
    return out
