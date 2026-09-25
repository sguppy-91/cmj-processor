"""Verification-figure tests (headless Agg backend)."""
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from cmj.config import CMJConfig  # noqa: E402
from cmj.model import Trial  # noqa: E402
from cmj.pipeline import run_pipeline  # noqa: E402
from cmj.plotting import boundary_times, verification_figure  # noqa: E402

from conftest import WEIGHING_START_S


def teardown_function():
    plt.close("all")


def test_verification_figure_structure(synth_result, synth_config):
    fig, (ax1, ax2) = verification_figure(synth_result, synth_config)
    assert len(fig.axes) == 2
    legend_labels = {label for label in ax1.get_legend_handles_labels()[1]}
    assert "BW" in next(iter(l for l in legend_labels if l.startswith("BW")))
    assert "Take-off" in legend_labels
    assert ax1.get_title()


def test_boundary_times(synth_result):
    times = boundary_times(synth_result)
    assert set(times) == {"onset", "unweighting_end", "braking_end", "takeoff"}
    values = list(times.values())
    assert values == sorted(values)  # temporal order holds


def test_figure_with_coarse_fallback(synth_trial, synth_config):
    """A trace with no landing (coarse take-off, NaN threshold) must still
    plot, with the take-off threshold line skipped."""
    cut = int(synth_trial.fs * 2.1)  # truncate mid-flight: no landing in trace
    truncated = Trial(
        t=synth_trial.t[:cut],
        fz=synth_trial.fz[:cut],
        plate_type=synth_trial.plate_type,
        fs=synth_trial.fs,
        meta={},
    )
    result = run_pipeline(truncated, synth_config, WEIGHING_START_S)
    assert result.takeoff.method == "coarse"

    fig, (ax1, ax2) = verification_figure(result, synth_config)
    labels = {label for label in ax1.get_legend_handles_labels()[1]}
    assert not any("thresh" in l.lower() for l in labels)  # NaN line skipped
    assert result.warnings  # fallback visible on the figure via warning text
