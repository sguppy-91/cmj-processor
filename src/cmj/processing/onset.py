"""Movement onset detection.

The BW +/- SD multiplier search is bounded by the shape of the
force-time curve itself (the reference Excel workbook's method), so the
propulsion phase and the landing spike can never be mistaken for onset:

1. Coarse take-off brackets the jump: the first sample below the coarse
   threshold (takeoff_coarse_n).
2. The peak force between the end of the weighing window and the coarse
   take-off bounds the jump.
3. The minimum force between the weighing window and the peak bounds the
   BW +/- SD search window.

Within [weighing end, dip minimum] the initial onset is the first sample
beyond BW +/- SD multiplier (Owen et al., 2014). A pre-movement rise in
force (the athlete shifts weight before the countermovement) is a
legitimate 'rising' onset found inside that window; a countermovement
that never crosses a threshold inside the window raises OnsetError
instead of latching onto the later propulsion rise. The true onset is
then either a fixed backtrack (chosen to avoid noise-driven
misidentification during the weighing period) or a backward search to
the last BW instance (Street et al., 2001 method).
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

    start = weighing.end_idx

    # 1. Coarse take-off brackets the jump (first sample below the coarse threshold)
    below = np.flatnonzero(fz[start:] < config.takeoff_coarse_n)
    if below.size == 0:
        raise OnsetError(
            "No take-off detected (force never dropped below "
            f"{config.takeoff_coarse_n:g} N) - cannot bound the onset search."
        )
    coarse_takeoff_idx = start + int(below[0])
    if coarse_takeoff_idx <= start:
        raise OnsetError(
            "Take-off coincides with the end of the weighing window - "
            "file likely starts mid-flight."
        )

    # 2. Peak force between the weighing window and the coarse take-off
    peak_idx = start + int(np.argmax(fz[start:coarse_takeoff_idx]))

    # 3. Force minimum between the weighing window and the peak bounds the search
    search_end = start + int(np.argmin(fz[start:peak_idx]))

    pos_hits = np.flatnonzero(fz[start:search_end] > threshold_pos)
    neg_hits = np.flatnonzero(fz[start:search_end] < threshold_neg)

    if pos_hits.size == 0 and neg_hits.size == 0:
        raise OnsetError(
            "No onset detected within BW +/- "
            f"{config.sd_multiplier:g} SD between the weighing window and "
            "the force minimum - the countermovement may be too gradual "
            "for the threshold, or the weighing window is contaminated."
        )

    if neg_hits.size > 0 and (pos_hits.size == 0 or neg_hits[0] < pos_hits[0]):
        initial_idx = start + int(neg_hits[0])
        strategy = "declining"
    else:
        initial_idx = start + int(pos_hits[0])
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


def manual_onset(
    t: np.ndarray,
    onset_s: float,
    weighing: WeighingInfo,
    config: CMJConfig,
) -> OnsetInfo:
    """Onset placed by the analyst after detection raised OnsetError.

    idx is the sample nearest the clicked time. strategy and method
    record 'manual' so every downstream output (figure, CSV) shows an
    analyst-placed onset instead of a detected one. Thresholds are still
    computed from the weighing window so the verification figure renders
    the usual BW +/- SD lines.
    """
    idx = int((np.abs(t - onset_s)).argmin())
    if idx >= t.size - 1:
        raise OnsetError(
            "Manual onset must leave at least one sample after it - "
            "the click was at the end of the recording."
        )
    return OnsetInfo(
        idx=idx,
        strategy="manual",
        method="manual",
        initial_idx=idx,
        threshold_pos_n=float(
            weighing.bw_n + config.sd_multiplier * weighing.sd_n
        ),
        threshold_neg_n=float(
            weighing.bw_n - config.sd_multiplier * weighing.sd_n
        ),
    )
