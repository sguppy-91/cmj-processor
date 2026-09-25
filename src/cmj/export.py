"""Results export: one long/wide CSV row per analysed trial.

Schema v1. The row logs the analyst's decision (raw weighing-window click
time, adjusted flag, boundary overrides) alongside the metrics so any
session can replay the exact analysis. Metric names follow the reference
script for now; renaming to manuscript terminology is a schema bump.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .app.decisions import Decision
from .model import AnalysisResult

SCHEMA_VERSION = 1

COLUMNS = [
    "schema_version",
    "participant",
    "session",
    "trial",
    "plate_type",
    "source_file",
    "run",
    "config_preset",
    "weighing_start_s",
    "adjusted",
    "boundary_overrides",
    "onset_strategy",
    "onset_method",
    "takeoff_method",
    "mass_kg",
    "jump_height_m",
    "total_movement_time_s",
    "mean_braking_force_n",
    "eccentric_displacement_m",
    "warnings",
]


def result_row(
    result: AnalysisResult,
    decision: Decision,
    meta: dict[str, str],
) -> dict[str, object]:
    """Flat CSV row for one analysed trial.

    weighing_start_s is logged at microsecond precision - far finer than
    any real click at typical sampling rates - so the value round-trips
    exactly through CSV text and a replayed decision is identical.
    """
    if decision.action == "discard":
        raise ValueError("Discarded trials are never written")
    adjusted = decision.action == "adjust" or bool(decision.boundary_overrides)
    return {
        "schema_version": SCHEMA_VERSION,
        "participant": meta.get("participant", ""),
        "session": meta.get("session", ""),
        "trial": meta.get("trial", ""),
        "plate_type": result.trial.plate_type,
        "source_file": result.trial.meta.get("source_file", ""),
        "run": result.trial.meta.get("run", ""),
        "config_preset": result.config_preset or "",
        "weighing_start_s": round(decision.weighing_start_s, 6),
        "adjusted": adjusted,
        "boundary_overrides": json.dumps(decision.boundary_overrides)
        if decision.boundary_overrides
        else "",
        "onset_strategy": result.onset.strategy,
        "onset_method": result.onset.method,
        "takeoff_method": result.takeoff.method,
        "mass_kg": result.metrics["mass_kg"],
        "jump_height_m": result.metrics["jump_height_m"],
        "total_movement_time_s": result.metrics["total_movement_time_s"],
        "mean_braking_force_n": result.metrics["mean_braking_force_n"],
        "eccentric_displacement_m": result.metrics["eccentric_displacement_m"],
        "warnings": "; ".join(result.warnings),
    }


def append_result(results_path: str | Path, row: dict[str, object]) -> None:
    """Append one row, writing the header only for a new/empty file."""
    path = Path(results_path)
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
        write_header = len(content) == 0
    else:
        write_header = True
    df = pd.DataFrame([row], columns=COLUMNS)
    df.to_csv(path, mode="a", header=write_header, index=False)
