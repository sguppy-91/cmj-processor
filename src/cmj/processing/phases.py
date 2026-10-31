"""Jump phase boundary identification.

Two taxonomies, selected by config.phase_method (indices are local,
onset-relative):

- "mcmahon" (McMahon et al., 2018): unweighting ends at minimum COM
  velocity; braking ends at the first positive-velocity sample.
- "harry" (Harry et al., 2020, Table 1): unloading ends at the local
  minimum vertical force (where the summed joint power turns
  negative); the eccentric phase divides at minimum COM velocity into
  yielding (still accelerating downward) and braking (decelerating
  downward); braking ends at the first positive-velocity sample
  (where summed joint power turns positive and the concentric phase
  begins).

Both searches run only up to the coarse take-off to avoid landing
effects.
"""
from __future__ import annotations

import numpy as np

from ..config import PhaseMethod
from ..errors import PhaseError


def find_phase_boundaries(
    fz: np.ndarray,
    velocity: np.ndarray,
    coarse_takeoff_idx: int,
    phase_method: PhaseMethod = "mcmahon",
) -> dict[str, int]:
    min_velocity_idx = int(np.argmin(velocity[:coarse_takeoff_idx]))

    pos_vel = np.flatnonzero(velocity[min_velocity_idx:coarse_takeoff_idx] > 0)
    if pos_vel.size == 0:
        raise PhaseError("Velocity never turned positive before take-off.")
    braking_end = min_velocity_idx + int(pos_vel[0])

    if phase_method == "mcmahon":
        return {"unweighting_end": min_velocity_idx, "braking_end": braking_end}

    if phase_method == "harry":
        # The local minimum force between onset and minimum velocity
        # ends the unloading phase; the search window is [0, min
        # velocity), so a countermovement must exist for it to be
        # non-empty.
        if min_velocity_idx <= 0:
            raise PhaseError(
                "Velocity minimum coincides with onset - no countermovement "
                "found before take-off."
            )
        unloading_end = int(np.argmin(fz[:min_velocity_idx]))
        return {
            "unloading_end": unloading_end,
            "yielding_end": min_velocity_idx,
            "braking_end": braking_end,
        }

    raise ValueError(f"Unknown phase method {phase_method!r}")
