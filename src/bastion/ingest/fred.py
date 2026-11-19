"""FRED macro series via the public fredgraph CSV endpoint (no API key required).

The observation window is fixed (``FRED_START``..``FRED_END``) so that pinned checksums only
change when FRED revises history, which is exactly the event we want to review.
"""

from __future__ import annotations

from functools import partial

from bastion.ingest.base import DownloadItem, HttpClient

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_START = "1990-01-01"
FRED_END = "2025-12-31"

# series id -> description. Kept deliberately small for M0; pillars add series as they need them.
SERIES: dict[str, str] = {
    "UNRATE": "Civilian unemployment rate, %, monthly SA",
    "CSUSHPINSA": "S&P CoreLogic Case-Shiller US national home price index, monthly NSA",
    "GDPC1": "Real GDP, billions of chained 2017 $, quarterly SAAR",
    "CPIAUCSL": "CPI all urban consumers, index, monthly SA",
    "FEDFUNDS": "Effective federal funds rate, %, monthly",
    "DGS3MO": "3-month Treasury constant maturity, %, daily",
    "DGS5": "5-year Treasury constant maturity, %, daily",
    "DGS10": "10-year Treasury constant maturity, %, daily",
    "MORTGAGE30US": "30-year fixed mortgage average (Freddie Mac PMMS), %, weekly",
    "BAMLC0A4CBBB": "ICE BofA BBB US corporate option-adjusted spread, %, daily",
    "VIXCLS": "CBOE VIX close, daily",
    "DRSFRMACBS": "Delinquency rate on single-family residential mortgages, all banks, %, quarterly SA",
    "CORSFRMACBS": "Charge-off rate on single-family residential mortgages, all banks, %, quarterly SA",
    "DRCCLACBS": "Delinquency rate on credit card loans, all banks, %, quarterly SA",
}


def items(client: HttpClient, series: list[str] | None = None) -> list[DownloadItem]:
    chosen = series or sorted(SERIES)
    out = []
    for sid in chosen:
        params = {"id": sid, "cosd": FRED_START, "coed": FRED_END}
        url = f"{FREDGRAPH_URL}?id={sid}&cosd={FRED_START}&coed={FRED_END}"
        out.append(
            DownloadItem(
                relpath=f"fred/{sid}.csv",
                url=url,
                fetch=partial(client.get, FREDGRAPH_URL, params=params),
            )
        )
    return out
