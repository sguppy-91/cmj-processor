"""Manual onset placement: the rescue path for gradual countermovements.

When the bounded BW +/- 5 SD search raises OnsetError, the analyst places
the onset by clicking; the manual time is logged in the Decision and the
results CSV (schema v2, onset_start_s), and replaying a logged row
reproduces the trial exactly. The gradual fixture dips to 798 N with a
5 SD threshold near 796.5 N, so detection must fail and the manual path
must succeed on the same trace.
"""
import numpy as np
import pytest

from cmj.app.decisions import Decision, apply_decision, decision_from_row
from cmj.config import CMJConfig
from cmj.errors import ExportError, OnsetError
from cmj.export import COLUMNS, SCHEMA_VERSION, append_result, result_row
from cmj.model import Trial, WeighingInfo
from cmj.pipeline import run_pipeline
from cmj.processing.onset import manual_onset

FS = 1000.0
BW = 800.0
WEIGHING_START_S = 0.1
ONSET_S = 1.2  # first sample of the shallow dip
META = {"participant": "P001", "session": "T1", "trial": "1"}


def make_gradual_trial() -> Trial:
    """Quiet standing with a deterministic 10 Hz, 1 N wiggle (window SD
    ~0.71 N, so BW +/- 5 SD ~ 796.5/803.5 N), then a dip to only 798 N
    that never crosses the negative threshold."""
    n_quiet, n_dip, n_rise, n_release, n_flight, n_land = 1200, 300, 350, 100, 400, 100
    t_quiet = np.arange(n_quiet) / FS
    fz = np.concatenate(
        [
            BW + np.sin(2 * np.pi * 10.0 * t_quiet),  # 0.0 - 1.2 s
            np.linspace(BW, 798.0, n_dip),           # 1.2 - 1.5 s: shallow dip
            np.linspace(798.0, 2200.0, n_rise),      # 1.5 - 1.85 s
            np.linspace(2200.0, 5.0, n_release),      # 1.85 - 1.95 s: release
            np.full(n_flight, 5.0),                   # 1.95 - 2.35 s: flight
            np.linspace(6.0, 1600.0, n_land),        # landing spike
        ]
    )
    t = np.arange(fz.size) / FS
    return Trial(t=t, fz=fz, plate_type="synthetic", fs=FS, meta={"source_file": "gradual.csv"})


@pytest.fixture(scope="module")
def gradual_trial() -> Trial:
    return make_gradual_trial()


@pytest.fixture(scope="module")
def config() -> CMJConfig:
    return CMJConfig()


def make_weighing() -> WeighingInfo:
    return WeighingInfo(
        start_time_s=WEIGHING_START_S,
        start_idx=100,
        end_idx=1100,
        window_s=1.0,
        bw_n=BW,
        sd_n=0.7,
        mass_kg=BW / 9.81,
    )


class TestManualOnset:
    def test_nearest_sample_and_labels(self, config):
        t = np.arange(3000) / FS
        onset = manual_onset(t, 1.2344, make_weighing(), config)
        assert onset.idx == 1234  # nearest sample to 1.2344 s at 1 kHz
        assert onset.strategy == "manual"
        assert onset.method == "manual"
        assert onset.initial_idx == onset.idx
        assert onset.threshold_pos_n == pytest.approx(BW + 5 * 0.7)
        assert onset.threshold_neg_n == pytest.approx(BW - 5 * 0.7)

    def test_click_at_end_of_recording_raises(self, config):
        t = np.arange(10) / FS
        with pytest.raises(OnsetError, match="end of the recording"):
            manual_onset(t, 0.02, make_weighing(), config)


class TestPipelineManualOnset:
    def test_detection_fails_on_gradual_trial(self, gradual_trial, config):
        with pytest.raises(OnsetError, match="No onset detected"):
            run_pipeline(gradual_trial, config, WEIGHING_START_S)

    def test_manual_onset_rescues_gradual_trial(self, gradual_trial, config):
        result = run_pipeline(
            gradual_trial, config, WEIGHING_START_S, onset_s=ONSET_S
        )
        assert result.onset.method == "manual"
        assert result.onset.idx == int(ONSET_S * FS)
        assert any("manually" in w for w in result.warnings)
        assert result.metrics["jump_height_m"] > 0.0
        assert all(np.isfinite(v) for v in result.metrics.values())


class TestDecisionAndReplay:
    def test_apply_decision_uses_manual_onset(self, gradual_trial, config):
        decision = Decision(
            weighing_start_s=WEIGHING_START_S, action="adjust", onset_s=ONSET_S
        )
        result = apply_decision(decision, gradual_trial, config, config_preset="HD-raw")
        assert result is not None
        assert result.onset.method == "manual"

    def test_row_logs_manual_onset_and_round_trips(self, gradual_trial, config):
        decision = Decision(
            weighing_start_s=WEIGHING_START_S, action="adjust", onset_s=ONSET_S
        )
        result = apply_decision(decision, gradual_trial, config)
        row = result_row(result, decision, META)

        assert row["schema_version"] == SCHEMA_VERSION
        assert row["onset_start_s"] == ONSET_S
        assert row["adjusted"] is True
        assert row["onset_method"] == "manual"
        assert "manually" in row["warnings"]

        rebuilt = decision_from_row(row)
        assert rebuilt.onset_s == ONSET_S
        replayed = apply_decision(rebuilt, gradual_trial, config)
        assert replayed.metrics == result.metrics

    def test_detected_onset_row_has_empty_onset_start(
        self, synth_trial, synth_config
    ):
        decision = Decision(weighing_start_s=0.2, action="accept")
        result = apply_decision(decision, synth_trial, synth_config)
        row = result_row(result, decision, META)
        assert row["onset_start_s"] == ""
        assert row["adjusted"] is False
        assert decision_from_row(row).onset_s is None


class TestAppendHeaderValidation:
    def test_append_rejects_mismatched_header(self, tmp_path):
        path = tmp_path / "results.csv"
        path.write_text("schema_version,participant,foo\n1,P001,bar\n", encoding="utf-8")
        with pytest.raises(ExportError, match="header"):
            append_result(path, dict.fromkeys(COLUMNS, ""))

    def test_append_accepts_schema_v2_header(self, tmp_path):
        path = tmp_path / "results.csv"
        path.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
        append_result(path, dict.fromkeys(COLUMNS, ""))
        content = path.read_text(encoding="utf-8")
        assert content.count(",".join(COLUMNS)) == 1  # header still written once
