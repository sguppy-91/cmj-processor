"""Jump phase boundary identification: unweighting, braking, propulsion.

Unweighting ends at minimum velocity; braking ends at the first
positive-velocity crossing, per McMahon et al. (2018). Both are searched
only up to the coarse take-off to avoid landing effects.
"""
from __future__ import annotations

import numpy as np

from ..errors import PhaseError


def find_phase_boundaries(
    velocity: np.ndarray, coarse_takeoff_idx: int
) -> dict[str, int]:
    unweighting_end = int(np.argmin(velocity[:coarse_takeoff_idx]))

    pos_vel = np.flatnonzero(velocity[unweighting_end:coarse_takeoff_idx] > 0)
    if pos_vel.size == 0:
        raise PhaseError("Velocity never turned positive before take-off.")
    braking_end = unweighting_end + int(pos_vel[0])

    return {"unweighting_end": unweighting_end, "braking_end": braking_end}
