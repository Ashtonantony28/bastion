"""US Treasury daily par yield curve, one CSV per calendar year."""

from __future__ import annotations

from functools import partial

from bastion.ingest.base import DownloadItem, HttpClient

URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
)
DEFAULT_YEARS = list(range(2005, 2026))


def items(client: HttpClient, years: list[int] | None = None) -> list[DownloadItem]:
    out = []
    for year in years or DEFAULT_YEARS:
        params = {
            "type": "daily_treasury_yield_curve",
            "field_tdr_date_value": str(year),
            "page": "",
            "_format": "csv",
        }
        url = URL.format(year=year)
        out.append(
            DownloadItem(
                relpath=f"treasury/par_curve_{year}.csv",
                url=url,
                fetch=partial(client.get, url, params=params),
            )
        )
    return out
