"""Reader interface and shared helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from ..errors import FormatError
from ..model import Trial


@runtime_checkable
class Reader(Protocol):
    """A vendor reader converts one raw export file into one or more
    Trials (multi-run exports, e.g. PASCO, produce several)."""

    name: str

    def sniff(self, columns: list[str]) -> bool: ...

    def read(self, path: str | Path) -> list[Trial]: ...


def require_columns(df: pd.DataFrame, required: list[str], path: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise FormatError(
            f"{path.name}: missing columns {missing}; found: {list(df.columns)}"
        )


def sampling_rate(t: np.ndarray, path: Path) -> float:
    """Sampling rate from the median sample interval.

    Derived from the data rather than trusted from export metadata, since
    PASCO runs can vary in rate and metadata is unreliable across vendors.
    """
    dt = np.diff(t)
    if dt.size == 0 or np.any(dt <= 0):
        raise FormatError(f"{path.name}: time column must be strictly increasing")
    return float(1.0 / np.median(dt))
