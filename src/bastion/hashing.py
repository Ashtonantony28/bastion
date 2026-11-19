"""Deterministic content hashes (ADR 0005).

Every model run and every reported table can be reduced to a SHA-256 over a canonical byte
encoding, so CI can detect any change in outputs bit-exactly, as Tickforge does for fill logs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def frame_hash(df: pd.DataFrame, sort_by: list[str] | None = None, float_digits: int = 12) -> str:
    """Hash a DataFrame independent of row order (if sort_by given) and column order.

    Floats are rendered with a fixed number of significant digits so that the hash is stable
    across platforms while still catching any meaningful numerical change.
    """
    out = df.copy()
    out = out[sorted(out.columns)]
    if sort_by:
        out = out.sort_values(sort_by, kind="mergesort").reset_index(drop=True)
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda v: "nan" if pd.isna(v) else f"{v:.{float_digits}g}")
    payload = out.to_csv(index=False, lineterminator="\n").encode()
    return sha256_bytes(payload)
