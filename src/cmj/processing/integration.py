"""Net-force integration to velocity and displacement.

Net force (Fz - BW) / mass -> acceleration, trapezoidal integration ->
velocity and displacement, per McMahon et al. (2018).
"""
from __future__ import annotations

import numpy as np

from ..model import Kinematics, WeighingInfo


def integrate(
    t: np.ndarray,
    fz: np.ndarray,
    onset_idx: int,
    weighing: WeighingInfo,
) -> Kinematics:
    t_onset = t[onset_idx:]
    fz_onset = fz[onset_idx:]
    dt = np.diff(t_onset)

    net_force = fz_onset - weighing.bw_n
    acceleration = net_force / weighing.mass_kg
    velocity = np.insert(
        np.cumsum((acceleration[:-1] + acceleration[1:]) / 2 * dt), 0, 0.0
    )
    displacement = np.insert(
        np.cumsum((velocity[:-1] + velocity[1:]) / 2 * dt), 0, 0.0
    )
    return Kinematics(
        t=t_onset,
        fz=fz_onset,
        net_force=net_force,
        velocity=velocity,
        displacement=displacement,
    )
