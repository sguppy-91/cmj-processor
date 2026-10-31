"""GUI config-composition tests (no windows: build_config is pure).

The GUI composes a named preset plus a phase-identification method at
launch; the logged config_preset label must identify exactly what ran.
"""
import pytest

from cmj.app.gui import build_config
from cmj.config import CMJConfig
from cmj.pipeline import run_pipeline

from conftest import WEIGHING_START_S


def test_default_phase_method_keeps_preset_label():
    config, label = build_config("raw", "mcmahon")
    assert config == CMJConfig.preset("raw")
    assert config.phase_method == "mcmahon"
    assert label == "raw"


def test_harry_phase_method_appends_to_label():
    config, label = build_config("raw", "harry")
    assert config.phase_method == "harry"
    assert config.filter_spec is None  # the rest of the preset is untouched
    assert label == "raw/harry"


def test_harry_label_flows_through_the_pipeline(synth_trial):
    """The GUI-composed config runs unchanged and logs its label."""
    config, label = build_config("raw", "harry")
    result = run_pipeline(synth_trial, config, WEIGHING_START_S, config_preset=label)
    assert set(result.boundaries) == {"unloading_end", "yielding_end", "braking_end"}


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="Unknown preset"):
        build_config("bogus", "mcmahon")


def test_unknown_phase_method_raises():
    with pytest.raises(ValueError, match="Unknown phase method"):
        build_config("raw", "bogus")
