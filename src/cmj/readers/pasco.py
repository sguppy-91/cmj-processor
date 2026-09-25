"""PASCO Capstone/SPARK export reader.

PASCO exports can hold multiple runs side by side in one file: each run
has its own column group suffixed 'Run #N' (time, per-channel forces,
the combined Fz, and PASCO's own calculated columns). This reader
produces one Trial per run from the time and combined-Fz columns and
deliberately ignores PASCO's calculated quantities (weight, hangtime,
mass, jump height): body mass and every metric come from the
analyst-driven pipeline instead.

Sampling rate is derived per run from the median sample interval, since
runs in one file can differ in rate and export metadata is not trusted.
Rows where a run has no data (runs end at different times) are dropped
per run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ..errors import FormatError
from ..model import Trial
from .base import Reader, require_columns, sampling_rate

_RUN_RE = re.compile(r"^(?P<name>.+?)\s+Run #(?P<run>\d+)$")
TIME_PREFIX = "Time (s)"
FZ_PREFIX = "Fz (N)"


class PascoReader:
    name = "pasco"

    def sniff(self, columns: list[str]) -> bool:
        return any(c.startswith("Time (s) Run #") for c in columns)

    def read(self, path: str | Path) -> list[Trial]:
        path = Path(path)
        df = pd.read_csv(path, encoding="utf-8-sig")

        run_ids = sorted(
            {int(m.group("run")) for c in df.columns if (m := _RUN_RE.match(c))}
        )
        if not run_ids:
            raise FormatError(f"{path.name}: no 'Run #N' column groups found")

        trials = []
        for run in run_ids:
            tcol = f"{TIME_PREFIX} Run #{run}"
            fzcol = f"{FZ_PREFIX} Run #{run}"
            require_columns(df, [tcol, fzcol], path)

            pair = df[[tcol, fzcol]].dropna()
            t = pair[tcol].to_numpy(dtype=float)
            fz = pair[fzcol].to_numpy(dtype=float)
            if t.size < 2:
                raise FormatError(f"{path.name}: run {run} has fewer than 2 samples")

            trials.append(
                Trial(
                    t=t,
                    fz=fz,
                    plate_type=self.name,
                    fs=sampling_rate(t, path),
                    meta={"source_file": path.name, "run": str(run)},
                )
            )
        return trials
