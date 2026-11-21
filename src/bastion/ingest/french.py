"""Kenneth French data library: daily factor and industry-portfolio returns (percent).

Files are zipped CSVs with prose headers and several sections, and they are re-issued monthly.
We extract one section, keep observations up to ``END`` and rewrite it as a plain CSV, so the
bytes (and pin) only change if history is revised. Returns are in percent, as published.
"""

from __future__ import annotations

import io
import zipfile
from functools import partial

from bastion.ingest.base import DownloadItem, HttpClient

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
END = 20251231
FILES = {
    "factors_daily": ("F-F_Research_Data_Factors_daily_CSV.zip", None),
    "industry12_vw_daily": (
        "12_Industry_Portfolios_Daily_CSV.zip",
        "Average Value Weighted Returns -- Daily",
    ),
}


def extract_section(zip_bytes: bytes, section: str | None, end: int = END) -> bytes:
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    lines = zf.read(zf.namelist()[0]).decode("latin-1").splitlines()
    start = 0
    if section is not None:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == section) + 1
    header_idx = next(i for i in range(start, len(lines)) if lines[i].startswith(","))
    header = "date" + lines[header_idx].rstrip()
    out = [",".join(h.strip() for h in header.split(","))]
    for ln in lines[header_idx + 1 :]:
        s = ln.strip()
        if not s or not s[:8].isdigit():
            break
        parts = [p.strip() for p in s.split(",")]
        if int(parts[0]) > end:
            continue
        out.append(",".join(parts))
    return ("\n".join(out) + "\n").encode()


def _fetch(client: HttpClient, fname: str, section: str | None) -> bytes:
    return extract_section(client.get(BASE + fname), section)


def items(client: HttpClient) -> list[DownloadItem]:
    return [
        DownloadItem(f"french/{key}.csv", partial(_fetch, client, fname, section), url=BASE + fname)
        for key, (fname, section) in sorted(FILES.items())
    ]
