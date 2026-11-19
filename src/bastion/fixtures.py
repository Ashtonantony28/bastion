"""Synthetic, seeded CI fixtures in the exact raw formats of each public source.

CI never needs credentials or network: dbt runs the same models over ``fixtures/raw`` that it
runs over real downloads. Fixtures are committed; ``bastion fixtures --check`` proves the
committed bytes still equal this generator's output, so regenerating one is a visible, reviewed
change (CLAUDE.md rule 6). Numbers are synthetic and carry no meaning about any real bank.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from bastion.ingest.fdic import FAILURE_FIELDS, FINANCIAL_FIELDS
from bastion.ingest.fred import SERIES

SEED = 20261119
QUARTERLY_SERIES = {"GDPC1", "DRSFRMACBS", "CORSFRMACBS", "DRCCLACBS"}
SCENARIO_HEADER = [
    "Scenario Name", "Date", "Real GDP growth", "Nominal GDP growth",
    "Real disposable income growth", "Nominal disposable income growth", "Unemployment rate",
    "CPI inflation rate", "3-month Treasury rate", "5-year Treasury yield",
    "10-year Treasury yield", "BBB corporate yield", "Mortgage rate", "Prime rate",
    "Dow Jones Total Stock Market Index (Level)", "House Price Index (Level)",
    "Commercial Real Estate Price Index (Level)", "Market Volatility Index (Level)",
]  # fmt: skip
TENORS_2023 = ["1 Mo", "2 Mo", "3 Mo", "4 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]  # fmt: skip
TENORS_2021 = [t for t in TENORS_2023 if t != "4 Mo"]  # the 4-month bill started in Oct 2022
N_CASE_BANKS = 4
N_QUARTER_BANKS = 30
FIXTURE_FAILED_CERT = 90001  # fails in 2023Q1 in the fixture, mirroring the SVB timeline
FIXTURE_FAILDATE = "3/10/2023"


def _csv(header: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode()


def _f(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def _month_starts(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return out


def _quarter_ends(start_year: int, end_year: int) -> list[str]:
    return [
        f"{y}{md}"
        for y in range(start_year, end_year + 1)
        for md in ("0331", "0630", "0930", "1231")
    ]


def fred_files(rng: np.random.Generator) -> dict[str, bytes]:
    out = {}
    months = _month_starts(date(2018, 1, 1), date(2023, 12, 1))
    for sid in sorted(SERIES):
        dates = (
            [d for d in months if d.month in (1, 4, 7, 10)] if sid in QUARTERLY_SERIES else months
        )
        level = 100.0 if sid in {"CSUSHPINSA", "CPIAUCSL", "GDPC1"} else 4.0
        vals = level + np.cumsum(rng.normal(0, level * 0.01, len(dates)))
        rows: list[list[object]] = [
            [d.isoformat(), _f(v, 3)] for d, v in zip(dates, vals, strict=True)
        ]
        if len(rows) > 5:
            rows[3][1] = ""  # FRED leaves gaps empty; the staging model must tolerate them
        out[f"fred/{sid}.csv"] = _csv(["observation_date", sid], rows)
    return out


def scenario_files(rng: np.random.Generator) -> dict[str, bytes]:
    out = {}
    specs = {
        "historic": ("Actual", [(y, q) for y in range(2021, 2026) for q in range(1, 5)], 0.0),
        "baseline": (
            "Supervisory Baseline",
            [(y, q) for y in range(2026, 2030) for q in range(1, 5)][:13],
            0.0,
        ),
        "severely_adverse": (
            "Supervisory Severely Adverse",
            [(y, q) for y in range(2026, 2030) for q in range(1, 5)][:13],
            1.0,
        ),
    }
    for key, (name, quarters, stress) in specs.items():
        rows = []
        for i, (y, q) in enumerate(quarters):
            shock = stress * np.exp(-((i - 3) ** 2) / 8.0)
            vals = [
                2.0 - 9 * shock,
                4.0 - 8 * shock,
                1.5 - 5 * shock,
                3.5 - 4 * shock,
                4.0 + 6 * shock,
                2.5 - 1 * shock,
                4.0 - 3.9 * shock,
                4.0 - 2 * shock,
                4.3 - 1.5 * shock,
                5.5 + 3 * shock,
                6.5 + 1 * shock,
                7.5 - 3 * shock,
                40000 * (1 - 0.5 * shock),
                300 * (1 - 0.25 * shock),
                290 * (1 - 0.4 * shock),
                18 + 50 * shock,
            ]
            vals = [v + rng.normal(0, 0.05) for v in vals]
            rows.append([name, f"{y} Q{q}", *[_f(v, 1) for v in vals]])
        out[f"fed_scenarios/2026/{key}_domestic.csv"] = _csv(SCENARIO_HEADER, rows)
    return out


def treasury_files(rng: np.random.Generator) -> dict[str, bytes]:
    out = {}
    for year, tenors, base in ((2021, TENORS_2021, 0.5), (2023, TENORS_2023, 4.5)):
        rows = []
        d = date(year, 12, 29)
        for _ in range(10):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            curve = [base + 0.1 * i + rng.normal(0, 0.02) for i in range(len(tenors))]
            rows.append([d.strftime("%m/%d/%Y"), *[_f(v) for v in curve]])
            d -= timedelta(days=1)
        out[f"treasury/par_curve_{year}.csv"] = _csv(["Date", *tenors], rows)
    return out


def _bank_quarter(
    rng: np.random.Generator, cert: int, repdte: str, size: float, stress: float
) -> list[object]:
    """One synthetic Call Report row. Balance-sheet identity ASSET = LIAB + EQTOT holds exactly."""
    asset = int(size * (1 + rng.normal(0, 0.02)))
    eqtot = int(asset * (0.09 - 0.03 * stress))
    liab = asset - eqtot
    eq = eqtot
    dep = int(liab * 0.88)
    depuna = int(dep * (0.35 + 0.5 * stress))
    depins = dep - depuna
    sc = int(asset * (0.25 + 0.2 * stress))
    scha = int(sc * (0.3 + 0.4 * stress))
    schf = int(scha * (1 - 0.15 * stress))
    scaf = sc - scha
    scaa = int(scaf * (1 + 0.05 * stress))
    lnlsgr = int(asset * (0.6 - 0.2 * stress))
    lnatres = int(lnlsgr * 0.012)
    v = {
        "CERT": cert, "REPDTE": repdte, "ASSET": asset, "LIAB": liab, "EQTOT": eqtot, "EQ": eq,
        "CHBAL": int(asset * 0.06), "SC": sc, "SCUST": int(sc * 0.3), "SCHA": scha, "SCHF": schf,
        "SCAF": scaf, "SCAA": scaa, "ASSTLT": int(asset * (0.25 + 0.2 * stress)), "LNLSGR": lnlsgr,
        "LNLSNET": lnlsgr - lnatres, "LNATRES": lnatres, "LNRE": int(lnlsgr * 0.5),
        "LNRERES": int(lnlsgr * 0.25), "LNCI": int(lnlsgr * 0.25), "LNCON": int(lnlsgr * 0.1),
        "LNCRCD": int(lnlsgr * 0.03), "DEP": dep, "DEPDOM": dep, "DEPINS": depins,
        "DEPUNA": depuna, "BRO": int(dep * 0.03), "COREDEP": int(dep * (0.8 - 0.4 * stress)),
        "VOLIAB": int(liab * (0.15 + 0.3 * stress)), "OTHBRF": int(liab * 0.05),
        "FREPP": int(liab * 0.01), "NTLNLS": int(lnlsgr * 0.002), "NCLNLS": int(lnlsgr * 0.008),
        "P3ASSET": int(lnlsgr * 0.005), "P9ASSET": int(lnlsgr * 0.001), "NAASSET": int(lnlsgr * 0.006),
        "INTINC": int(asset * 0.035), "EINTEXP": int(asset * 0.008), "NONII": int(asset * 0.006),
        "NONIX": int(asset * 0.02), "ELNATR": int(asset * 0.002), "NETINC": int(asset * 0.009),
        "RBCT1J": int(eqtot * 0.95), "RWAJT": int(asset * 0.7), "RBC1AAJ": _f(9 - 3 * stress, 4),
        "RBCRWAJ": _f(14 - 3 * stress, 4), "IDT1CER": _f(12 - 3 * stress, 4),
        "NIMY": _f(3.1 - 0.8 * stress, 4), "ROA": _f(1.1 - 0.4 * stress, 4), "ROE": _f(11 - 3 * stress, 4),
    }  # fmt: skip
    return [v[f] for f in FINANCIAL_FIELDS]


def fdic_files(rng: np.random.Generator) -> dict[str, bytes]:
    out = {}
    rows = []
    for b in range(N_CASE_BANKS):
        cert = 90001 + b
        stress = 1.0 if cert == FIXTURE_FAILED_CERT else 0.1 * b
        for i, q in enumerate(_quarter_ends(2019, 2023)[3:]):  # 20191231 .. 20231231
            if cert == FIXTURE_FAILED_CERT and q > "20221231":
                break  # a failed bank stops filing
            rows.append(_bank_quarter(rng, cert, q, 1e8 * (1 + b) * (1 + 0.04 * i), stress))
    out["fdic/financials/case_study.csv"] = _csv(FINANCIAL_FIELDS, rows)

    rows = [
        _bank_quarter(
            rng, 80001 + b, "20221231", float(rng.lognormal(13, 1.5)), float(rng.uniform(0, 0.6))
        )
        for b in range(N_QUARTER_BANKS)
    ]
    out["fdic/financials/all_banks_20221231.csv"] = _csv(FINANCIAL_FIELDS, rows)

    fails = []
    for i in range(8):
        cert = FIXTURE_FAILED_CERT if i == 7 else 70001 + i
        d = FIXTURE_FAILDATE if i == 7 else f"{(i % 12) + 1}/{10 + i}/{2008 + i}"
        y = d.split("/")[-1]
        fails.append(
            [
                cert,
                10000 + i,
                f"FIXTURE BANK {i}",
                "SOMEWHERE, ZZ",
                d,
                y,
                "DIF",
                "FAILURE",
                "PA",
                "SM",
                50000 * (i + 1),
                45000 * (i + 1),
                5000 * (i + 1),
            ]
        )
    out["fdic/failures.csv"] = _csv(FAILURE_FIELDS, fails)
    return out


def generate() -> dict[str, bytes]:
    rng = np.random.default_rng(SEED)
    files: dict[str, bytes] = {}
    for gen in (fred_files, scenario_files, treasury_files, fdic_files):
        files.update(gen(rng))
    return files


def write_all(root: Path) -> list[str]:
    files = generate()
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return sorted(files)


def check(root: Path) -> list[str]:
    files = generate()
    diffs = [
        rel
        for rel, data in sorted(files.items())
        if not (root / rel).exists() or (root / rel).read_bytes() != data
    ]
    committed = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    diffs += [f"{rel} (not produced by generator)" for rel in sorted(committed - set(files))]
    return diffs
