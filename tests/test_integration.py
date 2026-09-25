"""Integration tests against analytically known signals.

A half-sine net-force impulse on a known mass has closed-form velocity and
displacement, which pins down the trapezoidal integration far better than
real data can. A constant net force has exactly linear velocity and
quadratic displacement (the trapezoid rule is exact for both here).
"""
import numpy as np
import pytest

from cmj.model import WeighingInfo
from cmj.processing.integration import integrate

FS = 1000.0


def make_weighing(bw_n: float, mass_kg: float) -> WeighingInfo:
    return WeighingInfo(
        start_time_s=0.0,
        start_idx=0,
        end_idx=0,
        window_s=1.0,
        bw_n=bw_n,
        sd_n=1.0,
        mass_kg=mass_kg,
    )


def test_half_sine_impulse_velocity_and_displacement():
    """Net force A*sin(pi*t/T) on mass m: v(T) = 2AT/(pi*m),
    s(T) = A*T^2/(pi*m); velocity stays constant after the impulse."""
    A, T, m, bw = 500.0, 0.5, 80.0, 800.0
    t = np.arange(int(1.5 * FS)) / FS
    net = A * np.sin(np.pi * t / T)
    net[t > T] = 0.0
    fz = bw + net

    kin = integrate(t, fz, onset_idx=0, weighing=make_weighing(bw, m))

    idx_T = int(T * FS)
    v_expected = 2 * A * T / (np.pi * m)
    s_expected = A * T**2 / (np.pi * m)

    assert kin.velocity[0] == 0.0
    assert kin.displacement[0] == 0.0
    assert abs(kin.velocity[idx_T] - v_expected) < 1e-4
    assert abs(kin.displacement[idx_T] - s_expected) < 1e-4
    # After the impulse net force is zero, so velocity must be constant
    assert np.allclose(kin.velocity[idx_T:], kin.velocity[idx_T], atol=1e-9)
    # Net force column must be fz - BW
    assert np.allclose(kin.net_force, net, atol=1e-9)


def test_constant_net_force_is_exact():
    """Constant net force -> linear velocity (trapezoid-exact) and quadratic
    displacement."""
    a, m, bw = 1.25, 80.0, 800.0
    t = np.arange(int(2.0 * FS)) / FS
    fz = np.full_like(t, bw + a * m)

    kin = integrate(t, fz, onset_idx=0, weighing=make_weighing(bw, m))

    v_expected = a * t
    s_expected = 0.5 * a * t**2
    assert np.allclose(kin.velocity, v_expected, atol=1e-12)
    assert np.allclose(kin.displacement, s_expected, atol=1e-12)


def test_onset_slice_offsets_arrays():
    """A nonzero onset index must slice t/fz and zero the integrals there."""
    a, m, bw = 1.0, 80.0, 800.0
    t = np.arange(3000) / FS
    fz = bw + a * m + 100.0 * np.sin(2 * np.pi * 5 * t)  # nonzero history before onset
    onset_idx = 1000

    kin = integrate(t, fz, onset_idx=onset_idx, weighing=make_weighing(bw, m))

    assert kin.t.size == t.size - onset_idx
    assert np.allclose(kin.t, t[onset_idx:])
    assert np.allclose(kin.fz, fz[onset_idx:])
    assert kin.velocity[0] == 0.0
    assert kin.displacement[0] == 0.0
