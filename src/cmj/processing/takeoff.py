"""Take-off detection.

Coarse take-off brackets the flight phase (first Fz below the coarse
threshold). The refined method then sets the threshold from the middle
50% of flight (mean + SD multiplier) and searches for the first crossing
after braking ends; the fixed method uses a static force threshold
(2024 IJSSC manuscript: 20 N). Fallbacks are recorded as warnings, not
silent behaviour.
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


def detect_takeoff(
    fz_onset: np.ndarray,
    braking_end: int,
    coarse_idx: int,
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

    land_hits = np.flatnonzero(fz_onset[coarse_idx:] > config.takeoff_coarse_n)
    if land_hits.size == 0:
        warnings.append(
            "No landing detected (force never returned above "
            f"{config.takeoff_coarse_n:g} N). Using coarse take-off."
        )
        return TakeoffInfo(
            idx=coarse_idx,
            method="coarse",
            coarse_idx=coarse_idx,
            flight_mean_n=float("nan"),
            flight_sd_n=float("nan"),
            threshold_n=float("nan"),
        )

    coarse_land_idx = coarse_idx + int(land_hits[0])

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
