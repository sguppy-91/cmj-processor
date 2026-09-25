"""Core data model: the normalised Trial and analysis result objects.

Every vendor reader produces a Trial; everything downstream (weighing,
onset, integration, phases, take-off, metrics, plotting, export) operates
only on Trial and AnalysisResult, so adding a plate system means writing
a reader, never touching the analysis core.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Trial:
    """A single force-time recording, normalised across plate systems."""

    t: np.ndarray  # seconds, strictly increasing
    fz: np.ndarray  # combined vertical force (N)
    plate_type: str
    fs: float  # sampling rate (Hz), derived from median diff(t)
    meta: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WeighingInfo:
    """Body weight statistics from the analyst-specified quiet-standing window.

    start_time_s is the sample time nearest the analyst's raw decision
    (the clicked weighing-window start), never a derived onset value, so a
    logged decision replays honestly through a re-run.
    """

    start_time_s: float
    start_idx: int
    end_idx: int
    window_s: float
    bw_n: float
    sd_n: float
    mass_kg: float


@dataclass(frozen=True)
class OnsetInfo:
    idx: int  # absolute index into the trial arrays
    strategy: str  # 'rising' | 'declining'
    method: str  # onset method used (config.onset_method)
    initial_idx: int  # first sample beyond BW +/- SD multiplier
    threshold_pos_n: float
    threshold_neg_n: float


@dataclass(frozen=True)
class TakeoffInfo:
    idx: int  # local (onset-relative) index
    method: str  # 'refined' | 'coarse' | 'fixed'
    coarse_idx: int
    flight_mean_n: float  # NaN when no landing was detected
    flight_sd_n: float
    threshold_n: float


@dataclass(frozen=True)
class Kinematics:
    """Onset-onward processed signals used for metrics and plotting."""

    t: np.ndarray
    fz: np.ndarray
    net_force: np.ndarray
    velocity: np.ndarray
    displacement: np.ndarray


@dataclass(frozen=True)
class AnalysisResult:
    trial: Trial
    config_preset: str | None  # named preset used, if any
    weighing: WeighingInfo
    onset: OnsetInfo
    takeoff: TakeoffInfo
    boundaries: dict[str, int]  # local (onset-relative) phase-boundary indices
    kinematics: Kinematics
    metrics: dict[str, float]
    warnings: list[str] = field(default_factory=list)
