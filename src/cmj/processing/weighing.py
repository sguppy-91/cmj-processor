"""Body weight and SD from an analyst-specified quiet-standing window."""
from __future__ import annotations

import numpy as np

from ..config import CMJConfig
from ..errors import WeighingWindowError
from ..model import WeighingInfo


def compute_weighing(
    t: np.ndarray,
    fz: np.ndarray,
    start_time_s: float,
    config: CMJConfig,
) -> WeighingInfo:
    """BW and SD from the 1 s window starting nearest to start_time_s.

    start_time_s is the analyst's raw decision (the clicked time); it is
    never replaced by a derived onset value, so a logged decision replays
    honestly through a batch reprocess.
    """
    start_idx = int((np.abs(t - start_time_s)).argmin())
    weigh_end_time = t[start_idx] + config.weighing_duration_s
    end_idx = int((np.abs(t - weigh_end_time)).argmin())
    window_s = t[end_idx] - t[start_idx]
    if window_s < config.weighing_min_window_s:
        raise WeighingWindowError(
            f"Weighing window only {window_s:.2f} s - choose an earlier trim time."
        )

    window = fz[start_idx:end_idx]
    bw = float(window.mean())
    sd = float(window.std(ddof=1))
    return WeighingInfo(
        start_time_s=float(t[start_idx]),
        start_idx=start_idx,
        end_idx=end_idx,
        window_s=float(window_s),
        bw_n=bw,
        sd_n=sd,
        mass_kg=bw / config.gravity,
    )
