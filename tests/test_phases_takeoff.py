"""Phase-boundary and take-off tests on signals with exact known indices.

The synthetic force trace is built from piecewise-linear segments so every
boundary (unweighting end, braking end, coarse take-off, refined take-off)
is an exact integer index, not a tolerance.
"""
import numpy as np
import pytest

from cmj.config import CMJConfig
from cmj.errors import PhaseError, TakeoffError
from cmj.processing.phases import find_phase_boundaries
from cmj.processing.takeoff import coarse_takeoff, detect_takeoff


def make_synthetic_velocity() -> tuple[np.ndarray, int]:
    """Velocity with minimum at index 149, zero crossing at 300,
    positive from 301, coarse take-off window ending at 600."""
    v = np.concatenate(
        [
            np.linspace(0.0, -1.0, 150),  # 0..149
            np.linspace(-1.0, 0.0, 151),  # 150..300
            np.linspace(0.001, 2.0, 299),  # 301..599
        ]
    )
    return v, 600


class TestPhaseBoundaries:
    def test_known_boundaries(self):
        v, coarse = make_synthetic_velocity()
        boundaries = find_phase_boundaries(v, coarse)
        assert boundaries["unweighting_end"] == 149
        assert boundaries["braking_end"] == 301

    def test_velocity_never_positive_raises(self):
        v = np.linspace(0.0, -1.0, 600)
        with pytest.raises(PhaseError, match="never turned positive"):
            find_phase_boundaries(v, 600)


def make_takeoff_trace(
    flight: str = "alternating", with_landing: bool = True
) -> np.ndarray:
    """Force trace with a linear drop from 800 N to flight level.

    Drop spans indices 380..500 (slope 6.625 N/sample):
    - first < 15 N at index 499 (value 11.6)
    - first < 10 N at index 500 (value 5)
    - first < 20 N at index 498 (value 18.25)
    Flight (501..699) is either alternating 3/7 N (mean 5, SD 2,
    refined threshold 15) or constant 5 N (SD 0, threshold 5, never
    crossed). With a landing, force returns to 800 N from index 700;
    without, the trace ends mid-flight at index 650.
    """
    fz = np.full(800, 800.0)
    fz[380:501] = np.linspace(800.0, 5.0, 121)
    if flight == "alternating":
        fz[501:700] = np.tile([3.0, 7.0], 100)[: 700 - 501]
    else:
        fz[501:700] = 5.0
    if not with_landing:
        fz = fz[:650]
    return fz


class TestCoarseTakeoff:
    def test_first_below_threshold(self):
        fz = make_takeoff_trace()
        assert coarse_takeoff(fz, CMJConfig()) == 500

    def test_never_below_raises(self):
        with pytest.raises(TakeoffError, match="never dropped below"):
            coarse_takeoff(np.full(100, 800.0), CMJConfig())

    def test_below_at_start_raises(self):
        with pytest.raises(TakeoffError, match="starts mid-flight"):
            coarse_takeoff(np.full(100, 5.0), CMJConfig())


class TestDetectTakeoff:
    def test_refined_takeoff_precedes_coarse(self):
        """Flight middle-50% stats give threshold 15 N; the first crossing
        after braking ends (index 0 here) lands one sample before the
        coarse 10 N crossing."""
        fz = make_takeoff_trace(flight="alternating")
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, config=CMJConfig(), warnings=warnings)
        assert to.method == "refined"
        assert to.idx == 499
        assert to.coarse_idx == 500
        assert to.flight_mean_n == pytest.approx(5.0)
        # Sample SD (ddof=1) of 50 threes and 50 sevens
        assert to.flight_sd_n == pytest.approx(2.0 * np.sqrt(100 / 99))
        assert to.threshold_n == pytest.approx(5.0 + 5.0 * 2.0 * np.sqrt(100 / 99))
        assert warnings == []

    def test_fixed_threshold(self):
        """The manuscript's static threshold (20 N) crosses at index 498."""
        fz = make_takeoff_trace(flight="alternating")
        config = CMJConfig(takeoff_method="fixed_n", takeoff_fixed_n=20.0)
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, config=config, warnings=warnings)
        assert to.method == "fixed"
        assert to.idx == 498
        assert to.threshold_n == 20.0
        assert warnings == []

    def test_refined_not_crossed_falls_back_to_coarse(self):
        """Constant 5 N flight gives SD 0, threshold 5 N; nothing is below
        it, so the coarse take-off is used and the fallback is logged."""
        fz = make_takeoff_trace(flight="constant")
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert warnings == ["Refined take-off threshold not crossed. Using coarse take-off."]

    def test_no_landing_falls_back_to_coarse(self):
        """Trace ends mid-flight: no landing, flight stats are NaN, and the
        fallback is logged (mirrors the reference script's behaviour)."""
        fz = make_takeoff_trace(flight="alternating", with_landing=False)
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert np.isnan(to.flight_mean_n)
        assert np.isnan(to.flight_sd_n)
        assert warnings
