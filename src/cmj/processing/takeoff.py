"""Take-off detection.

Coarse take-off brackets the flight phase (first Fz below the coarse
threshold). The refined method then sets the threshold from the middle
50% of flight (mean + SD multiplier) and searches for the first crossing
after braking ends; the fixed method uses a static force threshold
(2024 IJSSC manuscript: 20 N). Fallbacks are recorded as warnings, not
silent behaviour.

The landing that closes the flight window is confirmed by two guards
against plate ring-down in the first milliseconds of flight, where a
1-2 sample transient above the coarse threshold is common: the search
waits landing_search_min_s into flight (the reference Excel workbook
searches from take-off row + 250 samples), and a candidate must then
stay above the threshold for landing_confirm_s. A confirmed landing
also guarantees the middle-50% window spans real flight samples, so
flight statistics are never computed from a transient or an empty
window.
"""
from __future__ import annotations

import numpy as np

from ..config import CMJConfig
from ..errors import TakeoffError
from ..model import TakeoffInfo


def coarse_takeoff(fz_onset: np.ndarray, config: CMJConfig) -> int:
    below = np.flatnonzero(fz_onset < config.takeoff_coarse_n)
    if below.size == 0:
        raise TakeoffError(
            "No take-off detected (force never dropped below "
            f"{config.takeoff_coarse_n:g} N)."
        )
    idx = int(below[0])
    if idx <= 0:
        raise TakeoffError(
            "Take-off coincides with onset - file likely starts mid-flight."
        )
    return idx


def find_landing(
    fz_onset: np.ndarray,
    coarse_idx: int,
    fs: float,
    config: CMJConfig,
) -> int | None:
    """Index where the landing begins, or None if none is confirmed.

    The search starts landing_search_min_s into flight; the landing is
    the first sample at or after that point whose force stays above the
    coarse threshold for landing_confirm_s consecutive samples. A run
    that reaches the end of the recording counts (a file truncated
    mid-landing still confirms).
    """
    start = coarse_idx + int(round(config.landing_search_min_s * fs))
    if start >= fz_onset.size:
        return None
    n_confirm = max(1, int(round(config.landing_confirm_s * fs)))
    above = (fz_onset[start:] > config.takeoff_coarse_n).astype(int)
    edges = np.diff(np.concatenate(([0], above, [0])))
    run_starts = np.flatnonzero(edges == 1)
    run_ends = np.flatnonzero(edges == -1)
    sustained = (run_ends - run_starts) >= n_confirm
    if run_starts.size == 0 or not sustained.any():
        return None
    return start + int(run_starts[sustained][0])


def detect_takeoff(
    fz_onset: np.ndarray,
    braking_end: int,
    coarse_idx: int,
    fs: float,
    config: CMJConfig,
    warnings: list[str],
) -> TakeoffInfo:
    if config.takeoff_method == "fixed_n":
        hits = np.flatnonzero(fz_onset[braking_end:] < config.takeoff_fixed_n)
        if hits.size == 0:
            warnings.append(
                f"Fixed take-off threshold ({config.takeoff_fixed_n:g} N) not "
                "crossed; using coarse take-off."
            )
            return TakeoffInfo(
                idx=coarse_idx,
                method="coarse",
                coarse_idx=coarse_idx,
                flight_mean_n=float("nan"),
                flight_sd_n=float("nan"),
                threshold_n=float("nan"),
            )
        return TakeoffInfo(
            idx=braking_end + int(hits[0]),
            method="fixed",
            coarse_idx=coarse_idx,
            flight_mean_n=float("nan"),
            flight_sd_n=float("nan"),
            threshold_n=float(config.takeoff_fixed_n),
        )

    coarse_land_idx = find_landing(fz_onset, coarse_idx, fs, config)
    if coarse_land_idx is None:
        warnings.append(
            "No landing detected (force never stayed above "
            f"{config.takeoff_coarse_n:g} N for {config.landing_confirm_s:g} s "
            f"after {config.landing_search_min_s:g} s of flight). Using coarse "
            "take-off."
        )
        return TakeoffInfo(
            idx=coarse_idx,
            method="coarse",
            coarse_idx=coarse_idx,
            flight_mean_n=float("nan"),
            flight_sd_n=float("nan"),
            threshold_n=float("nan"),
        )

    # Middle 50% of the flight phase
    flight_len = coarse_land_idx - coarse_idx
    flight_mid_start = coarse_idx + flight_len // 4
    flight_mid_end = coarse_idx + 3 * flight_len // 4
    flight_force = fz_onset[flight_mid_start:flight_mid_end]
    flight_mean = float(flight_force.mean())
    flight_sd = float(flight_force.std(ddof=1))
    threshold = flight_mean + config.sd_multiplier * flight_sd

    # Refined take-off = first sample below the refined threshold after braking ends
    refined_to = np.flatnonzero(fz_onset[braking_end:] < threshold)
    if refined_to.size == 0:
        warnings.append(
            "Refined take-off threshold not crossed. Using coarse take-off."
        )
        return TakeoffInfo(
            idx=coarse_idx,
            method="coarse",
            coarse_idx=coarse_idx,
            flight_mean_n=flight_mean,
            flight_sd_n=flight_sd,
            threshold_n=float(threshold),
        )

    return TakeoffInfo(
        idx=braking_end + int(refined_to[0]),
        method="refined",
        coarse_idx=coarse_idx,
        flight_mean_n=flight_mean,
        flight_sd_n=flight_sd,
        threshold_n=float(threshold),
    )
