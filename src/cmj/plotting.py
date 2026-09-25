"""Verification figure built from an AnalysisResult only.

Pure plotting: no interaction, no I/O. The inspector and GUI call this
to render the analyst's decision gate.
"""
from __future__ import annotations

import matplotlib.figure
import matplotlib.pyplot as plt
import numpy as np

from .config import CMJConfig
from .model import AnalysisResult

BOUNDARY_TIMES = ("onset", "unweighting_end", "braking_end", "takeoff")
BOUNDARY_COLORS = {
    "onset": "r",
    "unweighting_end": "orange",
    "braking_end": "purple",
    "takeoff": "brown",
}
BOUNDARY_LABELS = {
    "onset": "Onset",
    "unweighting_end": "Unweighting End",
    "braking_end": "Braking End",
    "takeoff": "Take-off",
}


def boundary_times(result: AnalysisResult) -> dict[str, float]:
    """Onset-relative sample times of the four boundaries, for plotting."""
    return {
        "onset": float(result.kinematics.t[0]),
        "unweighting_end": float(result.kinematics.t[result.boundaries["unweighting_end"]]),
        "braking_end": float(result.kinematics.t[result.boundaries["braking_end"]]),
        "takeoff": float(result.kinematics.t[result.takeoff.idx]),
    }


def verification_figure(
    result: AnalysisResult,
    config: CMJConfig,
    title: str | None = None,
) -> tuple[matplotlib.figure.Figure, tuple]:
    """Two-panel verification plot: force-time and velocity/displacement."""
    kin = result.kinematics
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Top panel: force-time
    ax1.plot(kin.t, kin.fz, "b-", label="Force")
    ax1.axhline(y=result.weighing.bw_n, color="g", linestyle="-", linewidth=1,
                label=f'BW ({result.weighing.bw_n:.0f} N)')
    ax1.axhline(y=result.onset.threshold_pos_n, color="k", linestyle="--", linewidth=1,
                label=f"BW+{config.sd_multiplier:g}SD ({result.onset.threshold_pos_n:.0f} N)")
    ax1.axhline(y=result.onset.threshold_neg_n, color="k", linestyle="--", linewidth=1,
                label=f"BW-{config.sd_multiplier:g}SD ({result.onset.threshold_neg_n:.0f} N)")
    if np.isfinite(result.takeoff.threshold_n):
        ax1.axhline(y=result.takeoff.threshold_n, color="m", linestyle=":", linewidth=1,
                    label=f'Take-off thresh ({result.takeoff.threshold_n:.0f} N)')

    times = boundary_times(result)
    for label in BOUNDARY_TIMES:
        ax1.axvline(x=times[label], color=BOUNDARY_COLORS[label], linestyle="-",
                    linewidth=1.5, label=BOUNDARY_LABELS[label])

    if title is None:
        title = f'CMJ Analysis ({result.onset.strategy} onset, {result.takeoff.method} take-off)'
    ax1.set_title(title)
    ax1.set_ylabel("Force (N)")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # Bottom panel: velocity and displacement
    ax2.plot(kin.t, kin.velocity, "r-", label="Velocity (m/s)")
    ax2.plot(kin.t, kin.displacement, "b-", label="Displacement (m)")
    ax2.axhline(y=0, color="k", linestyle="-", linewidth=0.5)
    for label in BOUNDARY_TIMES:
        ax2.axvline(x=times[label], color=BOUNDARY_COLORS[label], linestyle="-", linewidth=1.5)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Velocity / Displacement")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(True, alpha=0.3)

    if result.warnings:
        ax1.text(0.01, 0.02, "\n".join(result.warnings), transform=ax1.transAxes,
                 fontsize=8, color="darkred", va="bottom")

    fig.tight_layout()
    return fig, (ax1, ax2)
