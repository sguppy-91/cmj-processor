"""Onset-detection tests on piecewise traces with exact known indices.

The BW +/- 5 SD search is bounded by the shape of the force trace
(coarse take-off -> propulsion peak -> dip minimum), per the reference
Excel workbook. These tests pin each bound with exact integer indices:

- a normal countermovement leaves BW downward ('declining');
- a pre-movement force rise is a legitimate 'rising' onset found inside
  the bounded window even though a dip crossing follows;
- a countermovement too gradual to cross a threshold inside the window
  raises OnsetError instead of latching onto the propulsion rise or the
  landing spike (the failure mode of the unbounded search).
"""
import numpy as np
import pytest

from cmj.config import CMJConfig
from cmj.errors import OnsetError
from cmj.model import WeighingInfo
from cmj.processing.onset import detect_onset

FS = 1000.0
BW = 800.0
SD = 2.0  # thresholds: BW +/- 10 N
END_IDX = 100  # search starts at the end of the weighing window

CONFIG = CMJConfig()  # 5 SD, 100 ms backtrack, 10 N coarse take-off


def make_weighing(end_idx: int = END_IDX) -> WeighingInfo:
    return WeighingInfo(
        start_time_s=0.0,
        start_idx=end_idx - 1000,
        end_idx=end_idx,
        window_s=1.0,
        bw_n=BW,
        sd_n=SD,
        mass_kg=BW / 9.81,
    )


def make_trace() -> np.ndarray:
    """Quiet standing to END_IDX, then room for the caller's jump."""
    return np.full(END_IDX, BW)


def finish_trace(fz: list, flight: int = 300) -> np.ndarray:
    """Propulsion peak, force release below 10 N, flight, landing spike."""
    fz.append(np.linspace(2200.0, 5.0, 100))   # release: first < 10 N at -1
    fz.append(np.full(flight, 5.0))            # flight
    fz.append(np.linspace(6.0, 1800.0, 50))    # landing spike
    fz.append(np.full(200, BW))
    return np.concatenate(fz)


def t_for(fz: np.ndarray) -> np.ndarray:
    return np.arange(fz.size) / FS


def test_declining_onset_at_dip_crossing():
    # Dip 800 -> 700 N, one newton per sample: first < 790 N at 789 (offset 10)
    fz = make_trace()
    fz = finish_trace(
        [fz, BW - np.arange(1, 101), np.linspace(700.0, 2200.0, 200)]
    )
    onset = detect_onset(t_for(fz), fz, make_weighing(), CONFIG)
    assert onset.strategy == "declining"
    assert onset.initial_idx == END_IDX + 10
    assert onset.idx == onset.initial_idx - 100  # 100 ms backtrack at 1 kHz


def test_premovement_rise_is_a_rising_onset():
    # Rise 800 -> 830 (first > 810 N at 811, offset 10), settle back to BW,
    # then a normal dip below BW - 5 SD. The rise must win over the dip.
    fz = make_trace()
    fz = finish_trace(
        [
            fz,
            BW + np.arange(1, 31),                    # 801..830
            830.0 - np.arange(1, 31),                # 829..800
            BW - np.arange(1, 101),                  # dip 799..700
            np.linspace(700.0, 2200.0, 200),
        ]
    )
    onset = detect_onset(t_for(fz), fz, make_weighing(), CONFIG)
    assert onset.strategy == "rising"
    assert onset.initial_idx == END_IDX + 10


def test_premovement_rise_found_even_when_dip_is_shallow():
    # Rise above BW + 5 SD, then a dip that never reaches BW - 5 SD:
    # the rising onset inside the window is still found.
    fz = make_trace()
    fz = finish_trace(
        [
            fz,
            BW + np.arange(1, 31),                    # 801..830
            830.0 - np.arange(1, 31),                # 829..800
            BW - np.arange(1, 6),                    # shallow dip 799..795
            np.linspace(795.0, 2200.0, 200),
        ]
    )
    onset = detect_onset(t_for(fz), fz, make_weighing(), CONFIG)
    assert onset.strategy == "rising"
    assert onset.initial_idx == END_IDX + 10


def test_gradual_countermovement_raises_instead_of_latching_onto_propulsion():
    # Dip only to 795 N (never below BW - 5 SD = 790): the bounded window
    # ends at the dip minimum, so the later propulsion rise above 810 N and
    # the landing spike are never candidates. The unbounded search would
    # have returned a bogus 'rising' onset at the propulsion phase.
    fz = make_trace()
    fz = finish_trace(
        [
            fz,
            BW - np.arange(1, 6),                    # shallow dip 799..795
            np.linspace(795.0, 2200.0, 200),
        ]
    )
    with pytest.raises(OnsetError, match="No onset detected"):
        detect_onset(t_for(fz), fz, make_weighing(), CONFIG)


def test_no_takeoff_raises():
    # Force never drops below 10 N: the search cannot be bounded.
    fz = make_trace()
    fz = np.concatenate([fz, BW - np.arange(1, 101), np.linspace(700.0, 2200.0, 200)])
    fz = np.concatenate([fz, np.full(300, BW)])
    with pytest.raises(OnsetError, match="No take-off detected"):
        detect_onset(t_for(fz), fz, make_weighing(), CONFIG)
