"""Fourth-order zero-lag Butterworth low-pass filter with edge handling.

filtfilt-style zero-lag filtering distorts the signal near the edges of
the recorded window - exactly where onset detection and the refined
take-off threshold operate - so the edge mode is an explicit, testable
choice rather than a library default.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt

from ..config import FilterSpec

_PADTYPES = {"pad": "odd", "mirror": "even"}


def lowpass(x: np.ndarray, fs: float, spec: FilterSpec) -> np.ndarray:
    nyquist = fs / 2.0
    if spec.cutoff_hz >= nyquist:
        raise ValueError(
            f"Filter cutoff {spec.cutoff_hz} Hz must be below the Nyquist "
            f"frequency {nyquist} Hz (fs = {fs})"
        )
    b, a = butter(spec.order, spec.cutoff_hz, btype="low", fs=fs)
    return filtfilt(b, a, x, padtype=_PADTYPES[spec.edge_mode])
