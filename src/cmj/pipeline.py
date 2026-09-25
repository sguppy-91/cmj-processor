"""Pure analysis pipeline: Trial + config + weighing decision -> AnalysisResult.

No I/O, no GUI. Everything downstream (GUI, CLI, export, plotting) calls
run_pipeline with the analyst's logged weighing-window decision; all other
values are derived at run time.
"""
from __future__ import annotations

from .config import CMJConfig
from .model import AnalysisResult, Trial
from .processing import filtering, integration, metrics, onset, phases, takeoff, weighing


def run_pipeline(
    trial: Trial,
    config: CMJConfig,
    weighing_start_s: float,
    config_preset: str | None = None,
) -> AnalysisResult:
    """Analyse one trial from a raw weighing-window decision.

    weighing_start_s must be the analyst's raw decision (the clicked
    weighing-window start time), never a derived onset value, so logged
    decisions replay honestly through a re-run.
    """
    warnings: list[str] = []

    fz = trial.fz
    if config.filter_spec is not None:
        fz = filtering.lowpass(fz, trial.fs, config.filter_spec)

    weigh = weighing.compute_weighing(trial.t, fz, weighing_start_s, config)
    on = onset.detect_onset(trial.t, fz, weigh, config)
    kin = integration.integrate(trial.t, fz, on.idx, weigh)

    coarse_idx = takeoff.coarse_takeoff(kin.fz, config)
    boundaries = phases.find_phase_boundaries(kin.velocity, coarse_idx)
    to = takeoff.detect_takeoff(kin.fz, boundaries["braking_end"], coarse_idx, config, warnings)
    m = metrics.compute_metrics(kin, boundaries, to, weigh, config)

    return AnalysisResult(
        trial=trial,
        config_preset=config_preset,
        weighing=weigh,
        onset=on,
        takeoff=to,
        boundaries=boundaries,
        kinematics=kin,
        metrics=m,
        warnings=warnings,
    )
