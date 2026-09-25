"""Movement onset detection.

Initial onset at the first sample beyond BW +/- SD multiplier (Owen et al.,
2014), then either a fixed backtrack (chosen to avoid noise-driven
misidentification during the weighing period) or a backward search to the
last BW instance (2024 IJSSC manuscript method).
"""
from __future__ import annotations

import numpy as np

from ..config import CMJConfig
from ..errors import OnsetError
from ..model import OnsetInfo, WeighingInfo


def detect_onset(
    t: np.ndarray,
    fz: np.ndarray,
    weighing: WeighingInfo,
    config: CMJConfig,
) -> OnsetInfo:
    threshold_pos = weighing.bw_n + config.sd_multiplier * weighing.sd_n
    threshold_neg = weighing.bw_n - config.sd_multiplier * weighing.sd_n

    # Search forward from the end of the weighing window
    pos_hits = np.flatnonzero(fz[weighing.end_idx:] > threshold_pos)
    neg_hits = np.flatnonzero(fz[weighing.end_idx:] < threshold_neg)

    if pos_hits.size == 0 and neg_hits.size == 0:
        raise OnsetError("No onset detected within thresholds.")

    if neg_hits.size > 0 and (pos_hits.size == 0 or neg_hits[0] < pos_hits[0]):
        initial_idx = weighing.end_idx + int(neg_hits[0])
        strategy = "declining"
    else:
        initial_idx = weighing.end_idx + int(pos_hits[0])
        strategy = "rising"

    if config.onset_method == "backtrack_ms":
        target_time = t[initial_idx] - config.onset_backtrack_s
        idx = int((np.abs(t - target_time)).argmin())
    elif config.onset_method == "search_last_bw":
        raise NotImplementedError(
            "search_last_bw onset arrives with the manuscript reconciliation step"
        )
    else:
        raise ValueError(f"Unknown onset method {config.onset_method!r}")

    return OnsetInfo(
        idx=idx,
        strategy=strategy,
        method=config.onset_method,
        initial_idx=initial_idx,
        threshold_pos_n=float(threshold_pos),
        threshold_neg_n=float(threshold_neg),
    )
