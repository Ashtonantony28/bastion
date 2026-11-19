"""Shared download, write and checksum-pinning machinery.

Rules (ADR 0004):
- Downloaders are idempotent: re-running overwrites the same files with the same bytes.
- Every file written under ``raw/`` is checksummed. ``--pin`` records checksums in
  ``ingest/pins.json`` (a committed, reviewed file). Later runs compare against the pin and fail
  on drift unless ``allow_drift`` is set, because silently changed source data would silently
  change every downstream model.
- Data itself is never committed.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from bastion.hashing import sha256_bytes
from bastion.paths import PINS_FILE

log = logging.getLogger(__name__)

USER_AGENT = "bastion-research/0.1 (public-data ingest)"
DEFAULT_TIMEOUT_S = 60
MAX_ATTEMPTS = 4
BACKOFF_S = 2.0


class PinMismatchError(RuntimeError):
    """A downloaded file does not match its committed checksum pin."""


@dataclass(frozen=True)
class DownloadItem:
    """One file to materialise under raw/. ``fetch`` returns the exact bytes to write."""

    relpath: str
    fetch: Callable[[], bytes]
    url: str = ""


@dataclass
class IngestResult:
    relpath: str
    sha256: str
    nbytes: int
    status: str  # "pinned-ok" | "pinned-new" | "unpinned" | "drift-allowed"


@dataclass
class Pins:
    path: Path = PINS_FILE
    entries: dict[str, dict[str, object]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = PINS_FILE) -> Pins:
        if path.exists():
            return cls(path=path, entries=json.loads(path.read_text()))
        return cls(path=path, entries={})

    def save(self) -> None:
        ordered = {k: self.entries[k] for k in sorted(self.entries)}
        self.path.write_text(json.dumps(ordered, indent=2, sort_keys=True) + "\n")


class HttpClient:
    """requests wrapper with retries and backoff. Sends no user-identifying data."""

    def __init__(
        self, session: requests.Session | None = None, sleep: Callable[[float], None] = time.sleep
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep

    def get(self, url: str, params: Mapping[str, Any] | None = None) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_exc = RuntimeError(f"HTTP {resp.status_code} for {url}")
                else:
                    raise RuntimeError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
            except requests.RequestException as exc:
                last_exc = exc
            if attempt < MAX_ATTEMPTS:
                self._sleep(BACKOFF_S * 2 ** (attempt - 1))
        raise RuntimeError(f"giving up on {url} after {MAX_ATTEMPTS} attempts") from last_exc


def materialise(
    items: Iterable[DownloadItem],
    raw_root: Path,
    pins: Pins,
    pin: bool = False,
    allow_drift: bool = False,
) -> list[IngestResult]:
    """Fetch each item, verify against pins, then write it. Nothing is written on a mismatch."""
    results: list[IngestResult] = []
    for item in items:
        data = item.fetch()
        digest = sha256_bytes(data)
        existing = pins.entries.get(item.relpath)
        if pin:
            status = (
                "pinned-new" if existing is None or existing["sha256"] != digest else "pinned-ok"
            )
            pins.entries[item.relpath] = {"sha256": digest, "bytes": len(data), "url": item.url}
        elif existing is None:
            status = "unpinned"
            log.warning("%s is not pinned (run with --pin to record it)", item.relpath)
        elif existing["sha256"] == digest:
            status = "pinned-ok"
        elif allow_drift:
            status = "drift-allowed"
            log.warning("%s drifted from its pin (allowed)", item.relpath)
        else:
            raise PinMismatchError(
                f"{item.relpath}: sha256 {digest[:12]}... != pinned {str(existing['sha256'])[:12]}... "
                "The source changed. Inspect it, then re-pin with --pin as a reviewed change."
            )
        out = raw_root / item.relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        results.append(IngestResult(item.relpath, digest, len(data), status))
    if pin:
        pins.save()
    return results
