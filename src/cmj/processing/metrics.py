"""Jump metrics.

Jump height from take-off velocity plus COM displacement at take-off
(Chiu & Daehlin, 2020); the remaining metrics mirror the quantities the
reference script reports. Renaming to manuscript terminology happens with
the export-schema step so the parity port stays verbatim.
"""
from __future__ import annotations

import numpy as np

from ..config import CMJConfig
from ..model import Kinematics, TakeoffInfo, WeighingInfo


def compute_metrics(
    kinematics: Kinematics,
    boundaries: dict[str, int],
    takeoff: TakeoffInfo,
    weighing: WeighingInfo,
    config: CMJConfig,
) -> dict[str, float]:
    v_takeoff = kinematics.velocity[takeoff.idx]
    s_takeoff = kinematics.displacement[takeoff.idx]

    return {
        "mass_kg": weighing.mass_kg,
        "jump_height_m": float((v_takeoff**2) / (2 * config.gravity) + s_takeoff),
        "total_movement_time_s": float(
            kinematics.t[takeoff.idx] - kinematics.t[0]
        ),
        "mean_braking_force_n": float(
            kinematics.net_force[
                boundaries["unweighting_end"] : boundaries["braking_end"]
            ].mean()
        ),
        "eccentric_displacement_m": float(
            kinematics.displacement[boundaries["braking_end"]]
            - kinematics.displacement[0]
        ),
    }
