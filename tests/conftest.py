"""Shared synthetic CMJ trial and analysis fixtures.

The trace is a physically consistent countermovement jump at 1000 Hz:
quiet standing, a 0.4 s unweighting dip to 400 N, a 0.3 s propulsion
rise to 2000 N, a 0.1 s force release, a 0.4 s flight, then a landing
spike and recovery. Seeded noise keeps every fixture deterministic.
"""
import numpy as np
import pytest

from cmj.config import CMJConfig
from cmj.model import Trial
from cmj.pipeline import run_pipeline

FS = 1000.0
BW = 800.0
WEIGHING_START_S = 0.2  # inside the quiet-standing phase


@pytest.fixture(scope="session")
def synth_trial() -> Trial:
    rng = np.random.default_rng(2024)
    n_quiet, n_dip, n_rise, n_release, n_flight, n_land, n_recover = 1200, 300, 350, 100, 400, 100, 500
    fz = np.concatenate(
        [
            BW + rng.normal(0.0, 1.0, n_quiet),          # 0.0 - 1.2 s: quiet standing
            np.linspace(BW, 450.0, n_dip),                # 1.2 - 1.5 s: unweighting
            np.linspace(450.0, 2200.0, n_rise),          # 1.5 - 1.85 s: braking + propulsion
            np.linspace(2200.0, 5.0, n_release),          # 1.85 - 1.95 s: force release
            5.0 + rng.uniform(-1.0, 1.0, n_flight),      # 1.95 - 2.35 s: flight
            np.linspace(6.0, 1600.0, n_land),            # 2.35 - 2.45 s: landing spike
            np.linspace(1600.0, BW, n_recover) + rng.normal(0.0, 1.0, n_recover),
        ]
    )
    t = np.arange(fz.size) / FS
    return Trial(t=t, fz=fz, plate_type="synthetic", fs=FS, meta={"source_file": "synthetic_cmj.csv"})


@pytest.fixture(scope="session")
def synth_config() -> CMJConfig:
    return CMJConfig()


@pytest.fixture(scope="session")
def synth_result(synth_trial, synth_config) -> object:
    return run_pipeline(synth_trial, synth_config, WEIGHING_START_S, config_preset="HD-raw")
