"""Population stability index (PSI), the standard score/feature drift measure in credit model
monitoring. Rule of thumb (Siddiqi, Intelligent Credit Scoring): < 0.10 stable, 0.10-0.25 monitor,
> 0.25 significant shift.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

EPS = 1e-6


def psi(expected: ArrayLike, actual: ArrayLike, bins: int | ArrayLike = 10) -> float:
    """PSI of ``actual`` vs ``expected``. Integer ``bins`` uses quantiles of ``expected``."""
    e = np.asarray(expected, dtype=float)
    a = np.asarray(actual, dtype=float)
    if isinstance(bins, int):
        edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    else:
        edges = np.asarray(bins, dtype=float)
    edges[0], edges[-1] = -np.inf, np.inf
    pe = np.histogram(e, edges)[0] / e.size
    pa = np.histogram(a, edges)[0] / a.size
    pe, pa = np.clip(pe, EPS, None), np.clip(pa, EPS, None)
    return float(np.sum((pa - pe) * np.log(pa / pe)))
