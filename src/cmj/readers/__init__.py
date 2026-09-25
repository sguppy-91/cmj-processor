"""Read raw force plate exports into normalised Trial objects.

read_csv_any() sniffs the file header and dispatches to the matching vendor
reader, returning every trial the file contains (multi-run exports like
PASCO yield several). Pass plate_type= to force a specific reader when
auto-detection is ambiguous or a new export variant is being tested.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..errors import UnknownFormatError
from ..model import Trial
from .base import Reader
from .hawkin import HawkinReader
from .pasco import PascoReader

_READERS: list[Reader] = [HawkinReader(), PascoReader()]


def read_csv_any(path: str | Path, plate_type: str | None = None) -> list[Trial]:
    path = Path(path)
    columns = list(pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns)

    if plate_type is not None:
        reader = next((r for r in _READERS if r.name == plate_type), None)
        if reader is None:
            raise UnknownFormatError(
                f"No reader for plate_type {plate_type!r}; "
                f"available: {sorted(r.name for r in _READERS)}"
            )
    else:
        reader = next((r for r in _READERS if r.sniff(columns)), None)
        if reader is None:
            raise UnknownFormatError(
                f"{path.name}: unrecognised plate export; header: {columns}"
            )

    return reader.read(path)


__all__ = ["read_csv_any", "HawkinReader", "PascoReader"]
