"""FDIC BankFind Suite API: Call Report financials, failures and institution metadata.

The financials endpoint exposes Call Report data (FFIEC 031/041/051) per insured bank per
quarter, already harmonised by the FDIC, which is easier to consume than the FFIEC bulk zip.
Responses are paginated JSON; we normalise them to a CSV with a fixed column order and sorted
rows so the bytes, and therefore the pinned checksum, are deterministic.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable

from bastion.ingest.base import DownloadItem, HttpClient

API = "https://api.fdic.gov/banks/"
PAGE_LIMIT = 10_000

# Call Report fields used across ALM, early warning and the stress test. Names are FDIC
# RISVIEW field codes; definitions in docs/DATA.md.
FINANCIAL_FIELDS: list[str] = [
    "CERT", "REPDTE",
    # balance sheet
    "ASSET", "LIAB", "EQTOT", "EQ", "CHBAL", "SC", "SCUST", "SCHA", "SCHF", "SCAF", "SCAA",
    "ASSTLT", "LNLSGR", "LNLSNET", "LNATRES", "LNRE", "LNRERES", "LNCI", "LNCON", "LNCRCD",
    # funding
    "DEP", "DEPDOM", "DEPINS", "DEPUNA", "BRO", "COREDEP", "VOLIAB", "OTHBRF", "FREPP",
    # asset quality
    "NTLNLS", "NCLNLS", "P3ASSET", "P9ASSET", "NAASSET",
    # earnings (year-to-date)
    "INTINC", "EINTEXP", "NONII", "NONIX", "ELNATR", "NETINC",
    # capital (PCA)
    "RBCT1J", "RWAJT", "RBC1AAJ", "RBCRWAJ", "IDT1CER",
    # FDIC-computed ratios
    "NIMY", "ROA", "ROE",
]  # fmt: skip

FAILURE_FIELDS: list[str] = [
    "CERT", "FIN", "NAME", "CITYST", "FAILDATE", "FAILYR", "SAVR", "RESTYPE", "RESTYPE1",
    "CHCLASS1", "QBFASSET", "QBFDEP", "COST",
]  # fmt: skip

INSTITUTION_FIELDS: list[str] = [
    "CERT", "NAME", "STALP", "ACTIVE", "BKCLASS", "ESTYMD", "ENDEFYMD", "INSDATE", "ASSET",
    "FED_RSSD", "RSSDHCR", "NAMEHCR",
]  # fmt: skip

# ALM / IRRBB / liquidity fields (M6): Call Report repricing and maturity buckets
# (RC-B Memo 2 securities, RC-C Memo 2 loans, RC-E Memo time deposits, RC-M borrowings),
# deposit mix and HQLA proxies. Kept separate from FINANCIAL_FIELDS so existing pins stay valid.
ALM_FIELDS: list[str] = [
    "CERT", "REPDTE",
    # securities by repricing / remaining maturity
    "SCNM3LES", "SCNM3T12", "SCNM1T3", "SCNM3T5", "SCNM5T15", "SCNMOV15",
    "SCPT3LES", "SCPT3T12", "SCPT1T3", "SCPT3T5", "SCPT5T15", "SCPTOV15",
    "SCO3YLES", "SCOOV3Y",
    # loans by repricing / remaining maturity
    "LNRS3LES", "LNRS3T12", "LNRS1T3", "LNRS3T5", "LNRS5T15", "LNRSOV15",
    "LNOT3LES", "LNOT3T12", "LNOT1T3", "LNOT3T5", "LNOT5T15", "LNOTOV15",
    # time deposits by remaining maturity (<= and > $250k)
    "CD3LESS", "CD3T12S", "CD1T3S", "CDOV3S", "CD3LES", "CD3T12", "CD1T3", "CDOV3",
    # non-maturity deposit mix
    "DEP", "DEPNI", "DEPI", "TRN", "NTRSMMDA", "NTRSOTH", "NTRTIME", "DEPINS", "DEPUNA", "BRO",
    # borrowings by remaining maturity
    "FREPP", "OTBFH1L", "OTBFH1T3", "OTBFH3T5", "OTBFHOV5", "OTBOT1L", "OTBOT1T3", "OTBOT3T5", "OTBOTOV5",
    # liquidity and HQLA proxies
    "ASSET", "LIAB", "EQTOT", "RBCT1J", "CHBAL", "SC", "SCUST", "SCGNM", "SCMUNI", "SCAF", "SCAA",
    "SCHA", "SCHF", "SCPLEDGE", "LNPLEDGE", "LNLSGR", "LNRERES",
    # funding cost (year-to-date)
    "EDEP", "EINTEXP", "INTINC",
]  # fmt: skip

# SVB, Signature and First Republic plus large regional peers (see ADR 0006 and the M7 case study).
CASE_STUDY_CERTS: dict[int, str] = {
    24735: "Silicon Valley Bank",
    57053: "Signature Bank",
    59017: "First Republic Bank",
    57512: "Western Alliance Bank",
    24045: "Banc of California (PacWest)",
    2270: "Zions Bancorporation",
    983: "Comerica Bank",
    17534: "KeyBank",
    6560: "Huntington National Bank",
    588: "M&T Bank",
    6672: "Fifth Third Bank",
    57957: "Citizens Bank",
}
CASE_STUDY_FROM = "20191231"
CASE_STUDY_TO = "20231231"


def fetch_all(
    client: HttpClient,
    endpoint: str,
    fields: list[str],
    filters: str | None = None,
    sort_by: str | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    offset = 0
    while True:
        params: dict[str, object] = {
            "fields": ",".join(fields),
            "limit": PAGE_LIMIT,
            "offset": offset,
            "format": "json",
        }
        if filters:
            params["filters"] = filters
        if sort_by:
            params["sort_by"] = sort_by
            params["sort_order"] = "ASC"
        payload = json.loads(client.get(API + endpoint, params=params))
        page = [rec["data"] for rec in payload.get("data", [])]
        rows.extend(page)
        total = int(payload.get("meta", {}).get("total", len(rows)))
        offset += len(page)
        if not page or offset >= total:
            break
    return rows


def to_csv(rows: list[dict[str, object]], fields: list[str], key: Callable[[dict], tuple]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(fields)
    for row in sorted(rows, key=key):
        writer.writerow(["" if row.get(f) is None else row.get(f) for f in fields])
    return buf.getvalue().encode()


def _num(v: object) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return -1


def _fin_key(r: dict) -> tuple:
    return (_num(r.get("CERT")), str(r.get("REPDTE")))


def _mdy_key(s: object) -> tuple[int, int, int]:
    try:
        m, d, y = (int(x) for x in str(s).split("/"))
        return (y, m, d)
    except ValueError:
        return (0, 0, 0)


def failures_item(client: HttpClient) -> DownloadItem:
    def fetch() -> bytes:
        rows = fetch_all(client, "failures", FAILURE_FIELDS)
        return to_csv(
            rows,
            FAILURE_FIELDS,
            key=lambda r: (*_mdy_key(r.get("FAILDATE")), _num(r.get("FIN")), _num(r.get("CERT"))),
        )

    return DownloadItem("fdic/failures.csv", fetch, url=API + "failures")


def institutions_item(client: HttpClient) -> DownloadItem:
    def fetch() -> bytes:
        rows = fetch_all(client, "institutions", INSTITUTION_FIELDS)
        return to_csv(rows, INSTITUTION_FIELDS, key=lambda r: (_num(r.get("CERT")),))

    return DownloadItem("fdic/institutions.csv", fetch, url=API + "institutions")


def financials_case_study_item(client: HttpClient) -> DownloadItem:
    certs = " OR ".join(str(c) for c in sorted(CASE_STUDY_CERTS))
    filters = f"CERT:({certs}) AND REPDTE:[{CASE_STUDY_FROM} TO {CASE_STUDY_TO}]"

    def fetch() -> bytes:
        rows = fetch_all(client, "financials", FINANCIAL_FIELDS, filters=filters)
        return to_csv(rows, FINANCIAL_FIELDS, key=_fin_key)

    return DownloadItem("fdic/financials/case_study.csv", fetch, url=API + "financials?" + filters)


def financials_quarter_item(client: HttpClient, repdte: str) -> DownloadItem:
    """Every insured bank for one report date (YYYYMMDD, a quarter end)."""
    filters = f"REPDTE:{repdte}"

    def fetch() -> bytes:
        rows = fetch_all(client, "financials", FINANCIAL_FIELDS, filters=filters, sort_by="CERT")
        return to_csv(rows, FINANCIAL_FIELDS, key=_fin_key)

    return DownloadItem(
        f"fdic/financials/all_banks_{repdte}.csv", fetch, url=API + "financials?" + filters
    )


def alm_case_study_item(client: HttpClient) -> DownloadItem:
    certs = " OR ".join(str(c) for c in sorted(CASE_STUDY_CERTS))
    filters = f"CERT:({certs}) AND REPDTE:[{CASE_STUDY_FROM} TO {CASE_STUDY_TO}]"

    def fetch() -> bytes:
        return to_csv(
            fetch_all(client, "financials", ALM_FIELDS, filters=filters), ALM_FIELDS, key=_fin_key
        )

    return DownloadItem("fdic/alm/case_study.csv", fetch, url=API + "financials?" + filters)


def alm_quarter_item(client: HttpClient, repdte: str) -> DownloadItem:
    filters = f"REPDTE:{repdte}"

    def fetch() -> bytes:
        rows = fetch_all(client, "financials", ALM_FIELDS, filters=filters, sort_by="CERT")
        return to_csv(rows, ALM_FIELDS, key=_fin_key)

    return DownloadItem(
        f"fdic/alm/all_banks_{repdte}.csv", fetch, url=API + "financials?" + filters
    )
