"""Central configuration for every analysis constant.

All methodological constants live here so docs/methods.md maps one-to-one
onto the code and a published methods section is reproduced exactly by
loading a named preset.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OnsetMethod = Literal["backtrack_ms", "search_last_bw"]
TakeoffMethod = Literal["refined", "fixed_n"]
EdgeMode = Literal["pad", "mirror"]


@dataclass(frozen=True)
class FilterSpec:
    """Zero-lag (filtfilt) low-pass filter specification.

    edge_mode controls how filtfilt's edge distortion — which lands
    exactly where onset detection and the refined take-off threshold
    operate — is handled: 'pad' (odd extension) or 'mirror' (even
    extension). The choice is pinned by synthetic edge tests.
    """

    order: int = 4
    cutoff_hz: float = 50.0
    edge_mode: EdgeMode = "pad"


@dataclass(frozen=True)
class CMJConfig:
    gravity: float = 9.81
    sd_multiplier: float = 5.0
    weighing_duration_s: float = 1.0
    weighing_min_window_s: float = 0.5
    onset_method: OnsetMethod = "backtrack_ms"
    onset_backtrack_s: float = 0.100
    filter_spec: FilterSpec | None = None
    takeoff_method: TakeoffMethod = "refined"
    takeoff_coarse_n: float = 10.0
    takeoff_fixed_n: float = 20.0
    # Landing confirmation. Plate ring-down after take-off can cross the
    # coarse threshold for 1-2 samples; a real landing holds. The
    # landing search is delayed landing_search_min_s into flight (the
    # reference Excel workbook searches from take-off row + 250
    # samples), and a candidate must then stay above the coarse
    # threshold for landing_confirm_s.
    landing_search_min_s: float = 0.25
    landing_confirm_s: float = 0.05

    @classmethod
    def preset(cls, name: str) -> "CMJConfig":
        presets: dict[str, CMJConfig] = {
            # Verbatim port of CMJ_Analysis_Script.py: raw force, BW +/- 5 SD
            # onset with a fixed 100 ms backtrack, flight-phase-refined take-off.
            "HD-raw": cls(),
            # Backward-search methods: 50 Hz fourth-order zero-lag
            # Butterworth (Harry et al., 2022), backward search to the
            # last BW instance (Street et al., 2001), 20 N take-off.
            "bw_search": cls(
                filter_spec=FilterSpec(),
                onset_method="search_last_bw",
                takeoff_method="fixed_n",
            ),
        }
        try:
            return presets[name]
        except KeyError:
            raise ValueError(
                f"Unknown preset {name!r}; available: {sorted(presets)}"
            ) from None
