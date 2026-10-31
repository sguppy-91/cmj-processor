"""Take-off detection.

Coarse take-off brackets the flight phase (first Fz below the coarse
threshold). The refined method follows Lake et al. (2018): the flight
phase is bracketed by the first force value below the coarse threshold
and the next force value above it, flight statistics are taken 30 ms
inside each end of that bracket, and take-off is the first sample below
mean + sd_multiplier x SD of the flight window after braking ends.
The fixed method uses a static force threshold. Fallbacks are recorded
as warnings, not silent behaviour.

The bracket is closed by the *next* sample above the coarse
threshold, so a plate ring-down transient above it in early flight
terminates the bracket just as the landing would; when the remaining
window is too short for statistics the coarse take-off is used and the
fallback is logged. Lake et al. (2018) specify no ring-down guards -
matching the published method exactly is the trade-off.
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
    config: CMJConfig,
) -> int | None:
    """Lake et al. (2018), stage 1: the next force value above the
    coarse threshold after take-off closes the flight-phase bracket
    (None if the trace ends first)."""
    above = np.flatnonzero(fz_onset[coarse_idx + 1 :] > config.takeoff_coarse_n)
    if above.size == 0:
        return None
    return coarse_idx + 1 + int(above[0])


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

    coarse_land_idx = find_landing(fz_onset, coarse_idx, config)
    if coarse_land_idx is None:
        warnings.append(
            "No landing detected (force never rose above "
            f"{config.takeoff_coarse_n:g} N after take-off). Using coarse "
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

    # Lake et al. (2018), stage 2: statistics window 30 ms inside each
    # end of the bracketed flight phase.
    trim = int(round(config.takeoff_flight_trim_s * fs))
    win_start = coarse_idx + trim
    win_end = coarse_land_idx - trim
    if win_end - win_start < 2:
        warnings.append(
            "Bracketed flight shorter than "
            f"{2 * config.takeoff_flight_trim_s:g} s leaves no statistics "
            "window. Using coarse take-off."
        )
        return TakeoffInfo(
            idx=coarse_idx,
            method="coarse",
            coarse_idx=coarse_idx,
            flight_mean_n=float("nan"),
            flight_sd_n=float("nan"),
            threshold_n=float("nan"),
        )

    flight_force = fz_onset[win_start:win_end]
    flight_mean = float(flight_force.mean())
    flight_sd = float(flight_force.std(ddof=1))
    threshold = flight_mean + config.sd_multiplier * flight_sd

    # Take-off = first sample below the refined threshold after braking ends
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
