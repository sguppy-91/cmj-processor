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
from cmj.processing.takeoff import coarse_takeoff, detect_takeoff, find_landing

FS = 1000.0


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
    without, the trace ends mid-flight at index 650. At 1 kHz the
    landing search starts 250 samples past the coarse take-off
    (index 750), so the confirmed landing on this trace is index 750
    and the flight middle-50% window spans 125 samples.
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


def make_ringdown_trace(
    transient_at: int = 520,
    transient_len: int = 2,
    landing_at: int = 900,
) -> np.ndarray:
    """Flight with a plate ring-down transient (15 N) that must never be
    mistaken for the landing; the real landing ramps up from index 900.

    The transient sits inside the flight's alternating 3/7 N noise, and
    the landing ramp starts at 20 N (above the 10 N coarse threshold)
    so it is sustained through to the end of the recording."""
    fz = np.full(1000, 5.0)
    fz[:380] = 800.0
    fz[380:501] = np.linspace(800.0, 5.0, 121)
    fz[501:landing_at] = np.tile([3.0, 7.0], (landing_at - 501) // 2 + 1)[
        : landing_at - 501
    ]
    fz[transient_at : transient_at + transient_len] = 15.0
    fz[landing_at:] = np.linspace(20.0, 800.0, 1000 - landing_at)
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
        """Landing confirmed at index 750 (search starts 250 samples past
        the coarse take-off), so the flight window is 250 samples and the
        middle-50% window is fz[562:687]: 125 samples of the 3/7
        alternation (63 sevens, 62 threes - mean 5.016 N). The refined
        threshold ~15.06 N first crosses during the drop at index 499,
        one sample before the coarse 10 N crossing."""
        fz = make_takeoff_trace(flight="alternating")
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "refined"
        assert to.idx == 499
        assert to.coarse_idx == 500
        window = fz[562:687]
        assert to.flight_mean_n == pytest.approx(window.mean())
        assert to.flight_sd_n == pytest.approx(window.std(ddof=1))
        assert to.threshold_n == pytest.approx(
            window.mean() + 5.0 * window.std(ddof=1)
        )
        assert warnings == []

    def test_fixed_threshold(self):
        """The manuscript's static threshold (20 N) crosses at index 498."""
        fz = make_takeoff_trace(flight="alternating")
        config = CMJConfig(takeoff_method="fixed_n", takeoff_fixed_n=20.0)
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=config, warnings=warnings)
        assert to.method == "fixed"
        assert to.idx == 498
        assert to.threshold_n == 20.0
        assert warnings == []

    def test_refined_not_crossed_falls_back_to_coarse(self):
        """Constant 5 N flight gives SD 0, threshold 5 N; nothing is below
        it, so the coarse take-off is used and the fallback is logged."""
        fz = make_takeoff_trace(flight="constant")
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert warnings == ["Refined take-off threshold not crossed. Using coarse take-off."]

    def test_no_landing_falls_back_to_coarse(self):
        """Trace ends mid-flight: no landing, flight stats are NaN, and the
        fallback is logged (mirrors the reference script's behaviour)."""
        fz = make_takeoff_trace(flight="alternating", with_landing=False)
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert np.isnan(to.flight_mean_n)
        assert np.isnan(to.flight_sd_n)
        assert warnings


class TestLandingGuard:
    """Two guards against plate ring-down being read as the landing:
    a delayed search (landing_search_min_s) and a sustained-force
    confirmation (landing_confirm_s)."""

    def test_short_transient_after_search_start_is_ignored(self):
        """A 2-sample 15 N transient at index 760 (inside the search
        region, which starts at 750) is not a landing; the real landing
        at 900 is confirmed."""
        fz = make_ringdown_trace(transient_at=760, transient_len=2)
        assert find_landing(fz, coarse_idx=500, fs=FS, config=CMJConfig()) == 900

    def test_long_transient_inside_min_flight_time_is_ignored(self):
        """A 60 ms transient (longer than the 50 ms confirmation) at
        index 520 is only excluded by the delayed search: with the
        search bound removed it would be accepted as the landing."""
        fz = make_ringdown_trace(transient_at=520, transient_len=60)
        assert find_landing(fz, coarse_idx=500, fs=FS, config=CMJConfig()) == 900
        unbounded = CMJConfig(landing_search_min_s=0.0)
        assert find_landing(fz, coarse_idx=500, fs=FS, config=unbounded) == 520

    def test_truncated_landing_ramp_below_confirmation_returns_none(self):
        """A landing ramp cut off 30 samples in never sustains for 50 ms,
        so no landing is confirmed (truncated-file fallback applies)."""
        fz = make_ringdown_trace()
        fz = fz[:930]  # landing ramp runs 900..929 only
        unbounded = CMJConfig(landing_search_min_s=0.0)
        assert find_landing(fz, coarse_idx=500, fs=FS, config=unbounded) is None

    def test_detect_takeoff_refined_with_ringdown_transient(self):
        """End to end: with only the sustained-force guard active, the
        2-sample transient is skipped, the flight window spans real
        flight, and the refined take-off is unchanged from the clean
        trace."""
        fz = make_ringdown_trace(transient_at=520, transient_len=2)
        warnings: list[str] = []
        config = CMJConfig(landing_search_min_s=0.0)
        to = detect_takeoff(
            fz, braking_end=0, coarse_idx=500, fs=FS, config=config, warnings=warnings
        )
        assert to.method == "refined"
        assert to.idx == 499
        assert to.flight_mean_n == pytest.approx(5.0)
        assert warnings == []
