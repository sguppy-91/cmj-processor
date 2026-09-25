"""Interactive matplotlib windows: weighing-window selection and the
accept/adjust/discard review gate.

The widget code here is deliberately thin: every click is translated into
a call on decisions.py or the pipeline, so the audit-trail behaviour is
tested without GUI widgets. Zoom/pan stay available (the macOS toolbar
works alongside the click handlers); a placement click is ignored while
the toolbar is in zoom/pan mode so inspecting the trace never moves the
window.
"""
from __future__ import annotations

import numpy as np

from ..config import CMJConfig
from ..errors import CMJError
from ..model import AnalysisResult, Trial
from ..pipeline import run_pipeline
from ..plotting import verification_figure
from .decisions import (
    Decision,
    apply_boundary_overrides,
)

OVERRIDABLE = ("unweighting_end", "braking_end", "takeoff")


def snap_to_second(time_s: float) -> float:
    """Snap a clicked time to the nearest whole second."""
    return float(round(time_s))


def nearest_boundary(result: AnalysisResult, clicked_time_s: float) -> str:
    """Name of the overridable boundary whose sample time is nearest."""
    kin = result.kinematics
    candidates = {
        "unweighting_end": result.boundaries["unweighting_end"],
        "braking_end": result.boundaries["braking_end"],
        "takeoff": result.takeoff.idx,
    }
    return min(
        candidates, key=lambda name: abs(kin.t[candidates[name]] - clicked_time_s)
    )


def _pyplot():
    import matplotlib.pyplot as plt

    return plt


def _toolbar_busy(fig) -> bool:
    toolbar = fig.canvas.toolbar
    return bool(toolbar and toolbar.mode)


def _button(fig, label, x, y, callback, color="0.85"):
    """A matplotlib Button that stays alive as long as its figure.

    The canvas's callback registry stores only a weak reference to a
    Button, so a button whose return value is discarded is
    garbage-collected and its callback silently disconnects - it renders
    but never fires. Keeping the widget on the figure pins it for the
    figure's lifetime.
    """
    from matplotlib.widgets import Button

    btn = Button(fig.add_axes([x, y, 0.10, 0.05]), label, color=color, hovercolor="0.95")
    btn.on_clicked(callback)
    if not hasattr(fig, "_cmj_buttons"):
        fig._cmj_buttons = []
    fig._cmj_buttons.append(btn)
    return btn


def select_weighing_window(
    trial: Trial, config: CMJConfig, message: str | None = None
) -> float | None:
    """Click to place the 1 s weighing window; the span is drawn before
    the decision is accepted. Returns the raw click time, or None if
    cancelled. 'Snap' toggles rounding to the nearest whole second."""
    plt = _pyplot()
    duration = config.weighing_duration_s
    max_start = float(trial.t[-1] - duration)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(trial.t, trial.fz, lw=0.8)
    ax.set_title(
        (message + "\n" if message else "")
        + "Click on the trace to place the 1 s weighing window "
        "(zoom/pan first if needed), then Accept"
    )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Force (N)")
    ax.grid(True, alpha=0.3)

    state: dict = {"start": None, "snap": False, "done": False}
    artists: list = []

    def redraw() -> None:
        for a in artists:
            a.remove()
        artists.clear()
        if state["start"] is not None:
            artists.append(
                ax.axvspan(state["start"], state["start"] + duration, color="green", alpha=0.15)
            )
            artists.append(ax.axvline(state["start"], color="green", lw=1.5))

    def on_click(event):
        if event.inaxes is not ax or event.xdata is None or state["done"]:
            return
        if _toolbar_busy(fig):
            return
        x = float(event.xdata)
        if state["snap"]:
            x = snap_to_second(x)
        state["start"] = min(x, max_start)
        redraw()
        fig.canvas.draw_idle()

    def on_accept(_):
        if state["start"] is None:
            ax.set_title("Place the window first: click on the trace, then Accept")
            fig.canvas.draw_idle()
            return
        state["done"] = True
        plt.close(fig)

    def on_cancel(_):
        state["start"] = None
        state["done"] = True
        plt.close(fig)

    def on_snap(_):
        state["snap"] = not state["snap"]
        snap_btn.label.set_text(f"Snap: {'on' if state['snap'] else 'off'}")
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", on_click)
    snap_btn = _button(fig, "Snap: off", 0.83, 0.02, on_snap)
    _button(fig, "Accept", 0.71, 0.02, on_accept, color="palegreen")
    _button(fig, "Cancel", 0.94, 0.02, on_cancel, color="lightcoral")

    plt.show(block=True)
    return state["start"]


def _pick_boundary(result: AnalysisResult) -> tuple[str, int] | None:
    """Blocking single-click picker: returns (boundary name, local index)
    for the boundary nearest the clicked time, or None if cancelled."""
    plt = _pyplot()
    kin = result.kinematics
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(kin.t, kin.fz, lw=0.8)
    for name in OVERRIDABLE:
        idx = (
            result.takeoff.idx
            if name == "takeoff"
            else result.boundaries[name]
        )
        ax.axvline(kin.t[idx], lw=1.5,
                   label=name.replace("_", " ").title())
    ax.set_title("Click at the new time for the boundary you want to move "
                 "(nearest boundary wins); close the window to cancel")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Force (N)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    pts = fig.ginput(1, timeout=-1)
    plt.close(fig)
    if not pts:
        return None
    clicked_t = float(pts[0][0])
    name = nearest_boundary(result, clicked_t)
    idx = int((np.abs(kin.t - clicked_t)).argmin())
    return name, idx


def review_result(
    trial: Trial,
    config: CMJConfig,
    weighing_start_s: float,
    config_preset: str | None = None,
    title: str | None = None,
) -> tuple[str, dict[str, int]]:
    """Show the verification figure as an accept / adjust / discard gate.

    Returns ("accept" | "adjust" | "discard", overrides). "adjust" means
    boundary overrides were applied; re-weighing is requested by the
    caller via the returned action "reweigh".
    """
    plt = _pyplot()
    overrides: dict[str, int] = {}

    while True:
        result = run_pipeline(trial, config, weighing_start_s, config_preset)
        if overrides:
            result = apply_boundary_overrides(result, overrides, config)

        display_title = title
        if title and overrides:
            display_title = f"{title} ({len(overrides)} override(s))"
        fig, _ = verification_figure(result, config, title=display_title)
        action: dict = {"value": None}

        def finish(value):
            def handler(_):
                action["value"] = value
                plt.close(fig)

            return handler

        _button(fig, "Accept", 0.71, 0.02, finish("accept"), color="palegreen")
        _button(fig, "Re-weigh", 0.82, 0.02, finish("reweigh"), color="khaki")
        _button(fig, "Override", 0.82, 0.09, finish("override"), color="lightskyblue")
        _button(fig, "Discard", 0.94, 0.02, finish("discard"), color="lightcoral")
        plt.show(block=True)

        value = action["value"]
        if value is None:  # window closed without a button
            return "discard", {}
        if value == "override":
            picked = _pick_boundary(result)
            if picked is not None:
                overrides[picked[0]] = picked[1]
            continue
        if value == "accept" and not overrides:
            return "accept", {}
        if value in ("accept", "adjust"):
            return ("accept" if not overrides else "adjust"), overrides
        return value, {}


def inspect_trial(
    trial: Trial,
    config: CMJConfig,
    config_preset: str | None = None,
    title: str | None = None,
) -> Decision | None:
    """Full interactive flow for one trial: weigh -> verify -> decide.

    Returns a Decision (action may be "discard"), or None if the analyst
    cancelled the weighing-window selection.
    """
    while True:
        start = select_weighing_window(trial, config)
        if start is None:
            return None
        try:
            action, overrides = review_result(
                trial, config, start, config_preset, title=title
            )
        except CMJError as e:
            select_weighing_window(
                trial, config, message=f"Analysis failed: {e}. Re-select the window."
            )
            continue
        if action == "reweigh":
            continue
        return Decision(
            weighing_start_s=start,
            action=action,  # type: ignore[arg-type]
            boundary_overrides=overrides,
        )
