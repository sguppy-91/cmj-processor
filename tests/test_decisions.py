"""Decision-layer tests: what gets logged and written per decision.

Covers the plan's audit-trail requirements: an accepted trial logs the
raw click time, an adjusted trial sets the flag, a discarded trial
writes nothing, and a re-run from a logged decision reproduces the
original metrics exactly.
"""
import pytest

from cmj.app.decisions import (
    Decision,
    apply_boundary_overrides,
    apply_decision,
    decision_from_row,
)
from cmj.app.inspector import nearest_boundary, snap_to_second
from cmj.export import COLUMNS, result_row
from cmj.pipeline import run_pipeline

from conftest import WEIGHING_START_S

META = {"participant": "P001", "session": "T1", "trial": "1"}


def test_accept_logs_raw_click_time(synth_trial, synth_config, synth_result):
    """The logged weighing_start_s is the raw click time (which need not
    fall on a sample), never the derived sample time."""
    raw_click = 0.237  # between samples at 1000 Hz
    decision = Decision(weighing_start_s=raw_click, action="accept")
    result = apply_decision(decision, synth_trial, synth_config)
    # The pipeline snapped to the nearest sample...
    assert result.weighing.start_time_s == pytest.approx(0.237, abs=1e-3)
    # ...but the row logs the raw click exactly.
    row = result_row(result, decision, META)
    assert row["weighing_start_s"] == raw_click


def test_discard_writes_nothing(synth_trial, synth_config, synth_result):
    decision = Decision(weighing_start_s=WEIGHING_START_S, action="discard")
    assert apply_decision(decision, synth_trial, synth_config) is None
    with pytest.raises(ValueError, match="Discarded trials"):
        result_row(synth_result, decision, META)


@pytest.mark.parametrize(
    "action,overrides,expected",
    [
        ("accept", {}, False),
        ("adjust", {}, True),
        ("accept", {"braking_end": 700}, True),
    ],
)
def test_adjusted_flag(synth_trial, synth_config, action, overrides, expected):
    decision = Decision(WEIGHING_START_S, action, boundary_overrides=overrides)  # type: ignore[arg-type]
    result = apply_decision(decision, synth_trial, synth_config)
    row = result_row(result, decision, META)
    assert row["adjusted"] is expected


def test_replay_reproduces_metrics_exactly(synth_trial, synth_config):
    """A logged decision replayed through the pipeline must reproduce the
    original metrics exactly (the raw click time, not a derived value)."""
    decision = Decision(weighing_start_s=WEIGHING_START_S, action="accept")
    original = apply_decision(decision, synth_trial, synth_config)
    row = result_row(original, decision, META)

    replayed_decision = decision_from_row(row)
    assert replayed_decision.weighing_start_s == decision.weighing_start_s
    replayed = apply_decision(replayed_decision, synth_trial, synth_config)
    assert replayed.metrics == original.metrics


def test_replay_with_overrides_reproduces_metrics(synth_trial, synth_config, synth_result):
    overrides = {"takeoff": synth_result.takeoff.idx - 10}
    decision = Decision(
        WEIGHING_START_S, "adjust", boundary_overrides=overrides
    )
    original = apply_decision(decision, synth_trial, synth_config)
    row = result_row(original, decision, META)
    assert row["boundary_overrides"]

    replayed = apply_decision(decision_from_row(row), synth_trial, synth_config)
    assert replayed.metrics == original.metrics


class TestBoundaryOverrides:
    def test_takeoff_override_recomputes_jump_height(self, synth_result, synth_config):
        new_idx = synth_result.takeoff.idx - 10
        overridden = apply_boundary_overrides(synth_result, {"takeoff": new_idx}, synth_config)
        kin = synth_result.kinematics
        expected_height = (
            kin.velocity[new_idx] ** 2 / (2 * synth_config.gravity)
            + kin.displacement[new_idx]
        )
        assert overridden.takeoff.idx == new_idx
        assert overridden.metrics["jump_height_m"] == pytest.approx(expected_height)
        assert overridden.metrics["total_movement_time_s"] == pytest.approx(
            kin.t[new_idx] - kin.t[0]
        )
        # Untouched metrics stay identical
        assert overridden.metrics["eccentric_displacement_m"] == synth_result.metrics[
            "eccentric_displacement_m"
        ]
        assert any("overrides applied" in w for w in overridden.warnings)

    def test_braking_override_recomputes_braking_force(self, synth_result, synth_config):
        new_idx = synth_result.boundaries["braking_end"] + 10
        overridden = apply_boundary_overrides(
            synth_result, {"braking_end": new_idx}, synth_config
        )
        kin = synth_result.kinematics
        expected = kin.net_force[
            synth_result.boundaries["unweighting_end"] : new_idx
        ].mean()
        assert overridden.boundaries["braking_end"] == new_idx
        assert overridden.metrics["mean_braking_force_n"] == pytest.approx(expected)
        assert overridden.metrics["eccentric_displacement_m"] == pytest.approx(
            kin.displacement[new_idx] - kin.displacement[0]
        )

    def test_ordering_violation_rejected(self, synth_result, synth_config):
        with pytest.raises(ValueError, match="ordering"):
            apply_boundary_overrides(
                synth_result,
                {"braking_end": synth_result.boundaries["unweighting_end"] - 5},
                synth_config,
            )

    def test_unknown_boundary_rejected(self, synth_result, synth_config):
        with pytest.raises(ValueError, match="Unknown boundary"):
            apply_boundary_overrides(synth_result, {"onset": 5}, synth_config)

    def test_out_of_range_rejected(self, synth_result, synth_config):
        with pytest.raises(ValueError, match="out of range"):
            apply_boundary_overrides(
                synth_result, {"takeoff": 10**9}, synth_config
            )


class TestInspectorHelpers:
    """Pure helpers behind the interactive windows."""

    def test_snap_to_second(self):
        assert snap_to_second(1.4) == 1.0
        assert snap_to_second(1.6) == 2.0
        assert snap_to_second(0.0) == 0.0

    def test_nearest_boundary(self, synth_result):
        kin = synth_result.kinematics
        t_unweighting = kin.t[synth_result.boundaries["unweighting_end"]]
        t_takeoff = kin.t[synth_result.takeoff.idx]
        assert nearest_boundary(synth_result, t_unweighting + 0.01) == "unweighting_end"
        assert nearest_boundary(synth_result, t_takeoff - 0.02) == "takeoff"
