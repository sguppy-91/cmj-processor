"""Phase-boundary and take-off tests on signals with exact known indices.

The synthetic force trace is built from piecewise-linear segments so every
boundary (unweighting/unloading end, yielding end, braking end, coarse
take-off, refined take-off) is an exact integer index, not a tolerance.
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


def make_synthetic_force() -> np.ndarray:
    """600-sample force trace whose dip minimum sits at index 100,
    before the velocity minimum at 149."""
    return np.concatenate(
        [
            np.linspace(800.0, 400.0, 101),  # 0..100: dip, minimum 400 N at 100
            np.linspace(400.0, 2200.0, 499),  # 100..599: braking + propulsion rise
        ]
    )


class TestPhaseBoundaries:
    def test_known_boundaries(self):
        v, coarse = make_synthetic_velocity()
        boundaries = find_phase_boundaries(make_synthetic_force(), v, coarse)
        assert boundaries["unweighting_end"] == 149
        assert boundaries["braking_end"] == 301

    def test_velocity_never_positive_raises(self):
        fz = make_synthetic_force()
        v = np.linspace(0.0, -1.0, 600)
        with pytest.raises(PhaseError, match="never turned positive"):
            find_phase_boundaries(fz, v, 600)


class TestHarryPhaseBoundaries:
    """Harry et al. (2020) taxonomy: unloading ends at the local minimum
    force, the eccentric phase splits at minimum velocity (yielding then
    braking), and braking ends at the first positive-velocity sample."""

    def test_known_boundaries(self):
        v, coarse = make_synthetic_velocity()
        boundaries = find_phase_boundaries(
            make_synthetic_force(), v, coarse, phase_method="harry"
        )
        assert boundaries == {
            "unloading_end": 100,
            "yielding_end": 149,
            "braking_end": 301,
        }

    def test_shared_instants_with_mcmahon(self):
        """Min velocity and first positive velocity are the same instants
        under both taxonomies, only named differently."""
        v, coarse = make_synthetic_velocity()
        fz = make_synthetic_force()
        mcmahon = find_phase_boundaries(fz, v, coarse)
        harry = find_phase_boundaries(fz, v, coarse, phase_method="harry")
        assert mcmahon["unweighting_end"] == harry["yielding_end"]
        assert mcmahon["braking_end"] == harry["braking_end"]
        assert set(mcmahon) == {"unweighting_end", "braking_end"}
        assert set(harry) == {"unloading_end", "yielding_end", "braking_end"}

    def test_no_countermovement_raises(self):
        """Velocity minimum at onset (never dips negative) leaves an empty
        unloading search window: there is no countermovement to split."""
        fz = make_synthetic_force()
        v = np.linspace(0.001, 2.0, 600)  # minimum at index 0
        with pytest.raises(PhaseError, match="no countermovement"):
            find_phase_boundaries(fz, v, 600, phase_method="harry")

    def test_unknown_method_raises(self):
        v, coarse = make_synthetic_velocity()
        with pytest.raises(ValueError, match="Unknown phase method"):
            find_phase_boundaries(
                make_synthetic_force(), v, coarse, phase_method="bogus"
            )


def make_takeoff_trace(
    flight: str = "alternating", with_landing: bool = True
) -> np.ndarray:
    """Force trace with a linear drop from 800 N to flight level.

    Drop spans indices 380..500 (slope 6.625 N/sample):
    - first < 15 N at index 499 (value 11.6)
    - first < 10 N at index 500 (value 5)
    - first < 20 N at index 498 (value 18.25)
    Flight (501..699) is either alternating 3/7 N (mean 5, SD 2) or
    constant 5 N (SD 0, threshold 5, never crossed). With a landing,
    force returns to 800 N from index 700 (the bracket-closing sample
    above 10 N); without, the trace ends mid-flight at index 650.
    Lake et al. (2018) statistics window: 30 ms inside each end of the
    bracket [500, 700] = fz[530:670], 140 samples of the 3/7
    alternation (70 sevens, 70 threes, mean 5.016 N), threshold
    ~15.06 N, first crossed during the drop at index 499.
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
    def test_refined_takeoff_uses_lake_window(self):
        """Lake et al. (2018): statistics window fz[530:670] (30 ms
        inside each end of the bracket [500, 700]); the ~15.06 N
        threshold first crosses during the drop at index 499, one
        sample before the coarse 10 N crossing."""
        fz = make_takeoff_trace(flight="alternating")
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "refined"
        assert to.idx == 499
        assert to.coarse_idx == 500
        window = fz[530:670]
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
        """Trace ends mid-flight: no sample above 10 N closes the bracket,
        flight stats are NaN, and the fallback is logged."""
        fz = make_takeoff_trace(flight="alternating", with_landing=False)
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert np.isnan(to.flight_mean_n)
        assert np.isnan(to.flight_sd_n)
        assert warnings


class TestFlightBracket:
    """Lake et al. (2018) stage 1: the flight phase is bracketed by the
    first sample below the coarse threshold and the next sample above
    it — there is no delayed search or sustained-force confirmation.
    A ring-down transient above the coarse threshold ends the bracket
    exactly like the landing would."""

    def test_bracket_is_next_sample_above_coarse(self):
        fz = make_takeoff_trace(flight="alternating")
        assert find_landing(fz, coarse_idx=500, config=CMJConfig()) == 700

    def test_no_sample_above_returns_none(self):
        fz = make_takeoff_trace(flight="alternating", with_landing=False)
        assert find_landing(fz, coarse_idx=500, config=CMJConfig()) is None

    def test_early_transient_collapses_the_window(self):
        """A 6-sample 15 N transient 60 ms into flight closes the bracket
        at index 560; the statistics window [530, 530) is empty, so the
        coarse take-off is used and the fallback is logged."""
        fz = make_takeoff_trace(flight="alternating")
        fz[560:566] = 15.0
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        assert to.method == "coarse"
        assert to.idx == 500
        assert any("too short" in w or "leaves no statistics window" in w for w in warnings)

    def test_late_transient_shortens_the_window(self):
        """A single-sample 15 N transient 100 ms into flight closes the
        bracket at index 600; the window fz[530:570] still spans 40 real
        flight samples, so the refined take-off is found as usual."""
        fz = make_takeoff_trace(flight="alternating")
        fz[600] = 15.0
        warnings: list[str] = []
        to = detect_takeoff(fz, braking_end=0, coarse_idx=500, fs=FS, config=CMJConfig(), warnings=warnings)
        window = fz[530:570]
        assert to.method == "refined"
        assert to.flight_mean_n == pytest.approx(window.mean())
        assert to.idx == 499
        assert warnings == []


class TestHarryPipelineIntegration:
    """End to end on the shared synthetic trial: the Harry taxonomy
    reports its own boundary names while the instants shared with the
    McMahon taxonomy (minimum velocity, first positive velocity) keep
    every metric identical."""

    def test_boundary_names_and_order(self, harry_result):
        assert set(harry_result.boundaries) == {
            "unloading_end",
            "yielding_end",
            "braking_end",
        }
        b = harry_result.boundaries
        assert 0 < b["unloading_end"] <= b["yielding_end"] <= b["braking_end"]
        assert b["braking_end"] < harry_result.takeoff.idx

    def test_unloading_sits_at_the_force_dip_bottom(self, harry_result):
        """The synthetic dip bottoms out at 1.5 s (the trace's force
        minimum), so the unloading boundary must land there."""
        kin = harry_result.kinematics
        t_unloading = kin.t[harry_result.boundaries["unloading_end"]]
        assert 1.45 < t_unloading < 1.55

    def test_metrics_match_mcmahon_on_shared_instants(
        self, synth_result, harry_result
    ):
        assert harry_result.metrics == synth_result.metrics
