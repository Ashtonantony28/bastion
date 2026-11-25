from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from bastion import paths  # noqa: E402

RESULTS = paths.REPO_ROOT / "docs" / "results"
FIGURES = RESULTS / "figures"

# Colours: one accent for the bank under study, muted for the rest (accessible on white).
ACCENT = "#c2410c"
ACCENT_2 = "#1d4ed8"
ACCENT_3 = "#15803d"
MUTED = "#9ca3af"


def connect(target: str = "dev") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(paths.warehouse_path(target)), read_only=True)


def savefig(fig: plt.Figure, name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    out = FIGURES / name
    fig.savefig(out, dpi=150, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return out


def pct(x: float, nd: int = 1) -> str:
    return "n/a" if x != x else f"{100 * x:.{nd}f}%"


def bn(x_thousands: float, nd: int = 1) -> str:
    return "n/a" if x_thousands != x_thousands else f"{x_thousands / 1e6:,.{nd}f}"
