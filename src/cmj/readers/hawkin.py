"""Hawkin Dynamics export reader.

Hawkin Dynamics CSV exports contain one trial per file with a header row
naming 'Time (s)', 'Left (N)', 'Right (N)', 'Combined (N)' among other
columns; the combined vertical force is the analysis input and the time
column starts at 0.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..errors import FormatError
from ..model import Trial
from .base import Reader, require_columns, sampling_rate

COLUMNS = ["Time (s)", "Combined (N)"]


class HawkinReader:
    name = "hawkin"

    def sniff(self, columns: list[str]) -> bool:
        return all(c in columns for c in COLUMNS)

    def read(self, path: str | Path) -> list[Trial]:
        path = Path(path)
        df = pd.read_csv(path, encoding="utf-8-sig")
        require_columns(df, COLUMNS, path)
        t = df["Time (s)"].to_numpy(dtype=float)
        fz = df["Combined (N)"].to_numpy(dtype=float)
        if t.size < 2 or t.size != fz.size:
            raise FormatError(
                f"{path.name}: time and force columns must have equal length >= 2"
            )
        return [
            Trial(
                t=t,
                fz=fz,
                plate_type=self.name,
                fs=sampling_rate(t, path),
                meta={"source_file": path.name},
            )
        ]
