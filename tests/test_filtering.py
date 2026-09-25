"""Filter tests: interior fidelity, noise attenuation, and edge behaviour.

These use noisy, realistic signals rather than clean sinusoids, because
the filter's two documented effects — edge distortion (where onset
detection and the refined take-off operate) and quiet-standing SD
reduction (which shifts the BW +/- SD onset threshold) — only show up
with broadband noise and non-steady edges.
"""
import numpy as np
import pytest

from cmj.config import FilterSpec
from cmj.processing.filtering import lowpass

FS = 1000.0
SPEC = FilterSpec(order=4, cutoff_hz=65.0)


def test_length_and_finiteness_preserved():
    rng = np.random.default_rng(42)
    x = 800.0 + rng.normal(0.0, 20.0, 2000)
    for edge_mode in ("pad", "mirror"):
        y = lowpass(x, FS, FilterSpec(edge_mode=edge_mode))
        assert y.shape == x.shape
        assert np.all(np.isfinite(y))


def test_constant_signal_unchanged():
    x = np.full(1000, 784.8)
    y = lowpass(x, FS, SPEC)
    assert np.allclose(y, x, atol=1e-9)


def test_low_frequency_interior_fidelity_with_noise():
    """A 10 Hz signal buried in broadband noise must be recovered in the
    interior (edge padding excluded) with strong noise attenuation. A
    fourth-order 65 Hz filter passes ~sqrt(65/500) of white-noise power
    at fs = 1000, so the filtered RMSE must drop well below half the
    raw RMSE."""
    rng = np.random.default_rng(7)
    t = np.arange(2000) / FS
    true = 800.0 + 100.0 * np.sin(2 * np.pi * 10.0 * t)
    x = true + rng.normal(0.0, 20.0, t.size)

    y = lowpass(x, FS, SPEC)

    interior = slice(200, 1800)  # exclude 0.2 s at each edge
    raw_rmse = np.sqrt(np.mean((x - true) ** 2))
    filt_rmse = np.sqrt(np.mean((y[interior] - true[interior]) ** 2))
    assert filt_rmse < 0.5 * raw_rmse


def test_quiet_standing_sd_reduced():
    """Filtering reduces quiet-standing SD, which is why its position
    relative to the weighing-window SD calculation is a fixed, documented
    pipeline decision."""
    rng = np.random.default_rng(11)
    x = 800.0 + rng.normal(0.0, 10.0, 3000)

    y = lowpass(x, FS, SPEC)

    assert y.std(ddof=1) < 0.5 * x.std(ddof=1)
    assert abs(y.mean() - x.mean()) < 0.5


def test_edge_distortion_exists_and_decays():
    """A trace that is not steady at the file edge (e.g. force still
    changing at t=0) makes the odd-padded filtfilt edge deviate from the
    true signal. The distortion must be visible (edge error well above
    the interior noise floor) and must decay to the noise floor within
    50 ms."""
    rng = np.random.default_rng(3)
    n = 2000
    t = np.arange(n) / FS
    true = 800.0 + 2.0 * t  # low-frequency ramp: non-steady at both edges
    x = true + rng.normal(0.0, 3.0, n)

    y = lowpass(x, FS, SPEC)

    err = np.abs(y - true)
    err_edge = err[:5].max()
    err_mid = err[500:510].max()
    assert err_edge > 2 * err_mid  # distortion is real, not silently hidden
    assert err[50:100].max() < 0.5 * err_edge  # gone within 50 ms


def test_cutoff_above_nyquist_rejected():
    with pytest.raises(ValueError, match="Nyquist"):
        lowpass(np.ones(100), 100.0, FilterSpec(cutoff_hz=65.0))
