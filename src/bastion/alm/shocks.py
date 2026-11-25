"""BCBS IRRBB standardised interest-rate shock scenarios.

Source: BCBS, "Interest rate risk in the banking book" (April 2016, d368), Annex 2. USD shock
sizes: parallel 200bp, short 300bp, long 150bp. Short and long shocks decay/grow with x = 4:
  short(t) = S_short * exp(-t / 4)
  long(t)  = S_long * (1 - exp(-t / 4))
  steepener = -0.65 |short| + 0.9 |long|;  flattener = +0.8 |short| - 0.6 |long|
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray

USD_PARALLEL = 0.0200
USD_SHORT = 0.0300
USD_LONG = 0.0150
DECAY_X = 4.0


def _short(t: NDArray[np.float64]) -> NDArray[np.float64]:
    return USD_SHORT * np.exp(-t / DECAY_X)


def _long(t: NDArray[np.float64]) -> NDArray[np.float64]:
    return USD_LONG * (1.0 - np.exp(-t / DECAY_X))


SCENARIOS: dict[str, Callable[[NDArray[np.float64]], NDArray[np.float64]]] = {
    "parallel_up": lambda t: np.full_like(t, USD_PARALLEL),
    "parallel_down": lambda t: np.full_like(t, -USD_PARALLEL),
    "steepener": lambda t: -0.65 * _short(t) + 0.9 * _long(t),
    "flattener": lambda t: 0.8 * _short(t) - 0.6 * _long(t),
    "short_up": _short,
    "short_down": lambda t: -_short(t),
}


def shock(name: str, t: ArrayLike) -> NDArray[np.float64]:
    return SCENARIOS[name](np.asarray(t, dtype=float))
