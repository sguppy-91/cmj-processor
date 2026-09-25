"""Pure accept/adjust/discard decision logic - no widgets, fully testable.

The GUI widgets only translate clicks into calls into this module. Every
manual decision is logged as the raw weighing-window click time plus any
boundary overrides, so a re-run from a logged decision reproduces the
original metrics exactly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Literal, Mapping

import numpy as np

from ..config import CMJConfig
from ..model import AnalysisResult, Trial
from ..pipeline import run_pipeline
from ..processing import metrics as metrics_mod

Action = Literal["accept", "adjust", "discard"]

OVERRIDABLE_BOUNDARIES = ("unweighting_end", "braking_end", "takeoff")


@dataclass(frozen=True)
class Decision:
    """The analyst's decision for one trial.

    weighing_start_s is the raw click time, never a derived onset value:
    log the decision, derive everything else at run time.
    """

    weighing_start_s: float
    action: Action
    boundary_overrides: dict[str, int] = field(default_factory=dict)


def apply_decision(
    decision: Decision,
    trial: Trial,
    config: CMJConfig,
    config_preset: str | None = None,
) -> AnalysisResult | None:
    """Run the pipeline from a logged decision.

    Returns None for a discarded trial (nothing gets written).
    """
    if decision.action == "discard":
        return None
    result = run_pipeline(trial, config, decision.weighing_start_s, config_preset)
    if decision.boundary_overrides:
        result = apply_boundary_overrides(result, decision.boundary_overrides, config)
    return result


def apply_boundary_overrides(
    result: AnalysisResult,
    overrides: Mapping[str, int],
    config: CMJConfig,
) -> AnalysisResult:
    """Replace phase/take-off boundaries and recompute the affected metrics.

    Overrides are local (onset-relative) indices. Ordering is validated:
    0 <= unweighting_end <= braking_end <= takeoff < n.
    """
    unknown = set(overrides) - set(OVERRIDABLE_BOUNDARIES)
    if unknown:
        raise ValueError(
            f"Unknown boundary override(s) {sorted(unknown)}; "
            f"overridable: {list(OVERRIDABLE_BOUNDARIES)}"
        )

    n = result.kinematics.t.size
    boundaries = dict(result.boundaries)
    takeoff = result.takeoff
    for key, idx in overrides.items():
        if not isinstance(idx, (int, np.integer)) or not 0 <= idx < n:
            raise ValueError(f"Override {key}={idx!r} out of range 0..{n - 1}")
        if key == "takeoff":
            takeoff = replace(takeoff, idx=int(idx))
        else:
            boundaries[key] = int(idx)

    if not (0 <= boundaries["unweighting_end"] <= boundaries["braking_end"] <= takeoff.idx):
        raise ValueError(
            "Boundary overrides violate phase ordering "
            f"(unweighting_end={boundaries['unweighting_end']}, "
            f"braking_end={boundaries['braking_end']}, takeoff={takeoff.idx})"
        )

    recomputed = metrics_mod.compute_metrics(
        result.kinematics, boundaries, takeoff, result.weighing, config
    )
    warnings = result.warnings + [
        "Boundary overrides applied: "
        + ", ".join(f"{k}={v}" for k, v in sorted(overrides.items()))
    ]
    return replace(
        result,
        boundaries=boundaries,
        takeoff=takeoff,
        metrics=recomputed,
        warnings=warnings,
    )


def decision_from_row(row: Mapping[str, object]) -> Decision:
    """Rebuild a Decision from a logged results-CSV row (for batch replay)."""
    action: Action = "adjust" if str(row.get("adjusted", "")) in ("True", "true", "1") else "accept"
    overrides_raw = str(row.get("boundary_overrides", "") or "")
    overrides = {k: int(v) for k, v in json.loads(overrides_raw).items()} if overrides_raw else {}
    return Decision(
        weighing_start_s=float(row["weighing_start_s"]),
        action=action,
        boundary_overrides=overrides,
    )
