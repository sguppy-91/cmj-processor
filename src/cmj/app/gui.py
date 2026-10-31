"""Thin tkinter shell: file selection, metadata entry, results summary.

The workflow logic lives in the pipeline, inspector, decisions, and
export modules; this module only translates dialogs into calls.
Configuration is chosen at launch: a named preset, then the phase-
identification method; a non-default phase method is appended to the
logged config_preset label. Multi-run exports (e.g. PASCO) are
inspected run by run: participant and session are asked once per file,
the trial label once per run.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, simpledialog

from ..config import CMJConfig
from ..errors import CMJError
from ..export import append_result, result_row
from ..readers import read_csv_any
from .decisions import apply_decision
from .inspector import inspect_trial

PRESETS = ("raw", "bw_search")
PHASE_METHODS = ("mcmahon", "harry")


def build_config(preset: str, phase_method: str) -> tuple[CMJConfig, str]:
    """Config for a named preset plus phase method; returns (config, label).

    A phase method that differs from the preset's own is applied via a
    copy and appended to the label, so the logged config_preset
    identifies exactly what ran (e.g. 'raw/harry').
    """
    if phase_method not in PHASE_METHODS:
        raise ValueError(
            f"Unknown phase method {phase_method!r}; "
            f"available: {list(PHASE_METHODS)}"
        )
    config = CMJConfig.preset(preset)
    if phase_method == config.phase_method:
        return config, preset
    return replace(config, phase_method=phase_method), f"{preset}/{phase_method}"


def _summary(row: dict[str, object]) -> str:
    return (
        f"Mass: {row['mass_kg']:.1f} kg\n"
        f"Jump height: {row['jump_height_m']:.4f} m\n"
        f"Total movement time: {row['total_movement_time_s']:.3f} s\n"
        f"Mean braking force: {row['mean_braking_force_n']:.1f} N\n"
        f"Eccentric displacement: {row['eccentric_displacement_m']:.4f} m"
    )


def process_file(
    path: str,
    participant: str,
    session: str,
    config: CMJConfig,
    label: str,
    results_file: str,
) -> list[dict[str, object]]:
    """Analyse every trial in one file through the interactive flow.
    Returns the rows written (skipped or discarded runs contribute none)."""
    trials = read_csv_any(path)
    multi = len(trials) > 1
    rows: list[dict[str, object]] = []

    for i, trial in enumerate(trials, 1):
        prompt = f"Trial number (run {i} of {len(trials)})" if multi else "Trial number (e.g. 1)"
        label_trial = simpledialog.askstring("Trial", prompt, initialvalue=str(i) if multi else "")
        if label_trial is None:
            continue  # skip this run only
        meta = {"participant": participant, "session": session, "trial": label_trial}

        title = f"{participant} {session} Trial {label_trial}"
        if multi:
            title += f" - Run {i}/{len(trials)}"
        decision = inspect_trial(trial, config, config_preset=label, title=title)
        if decision is None or decision.action == "discard":
            continue

        result = apply_decision(decision, trial, config, config_preset=label)
        if result is None:
            continue
        row = result_row(result, decision, meta)
        append_result(results_file, row)
        rows.append(row)
    return rows


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    results_file = filedialog.asksaveasfilename(
        title="Select results file to append to (or type a new name)",
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")],
    )
    if not results_file:
        root.destroy()
        return

    while True:
        preset = simpledialog.askstring(
            "Config preset",
            f"Config preset ({', '.join(PRESETS)})",
            initialvalue=PRESETS[0],
        )
        if preset is None:
            root.destroy()
            return
        phase_method = simpledialog.askstring(
            "Phase method",
            f"Phase identification method ({', '.join(PHASE_METHODS)})",
            initialvalue=PHASE_METHODS[0],
        )
        if phase_method is None:
            root.destroy()
            return
        try:
            config, label = build_config(preset, phase_method)
        except ValueError as e:
            messagebox.showerror("Config", str(e))
            continue  # re-prompt; a typo no longer ends the session
        break

    while True:
        path = filedialog.askopenfilename(
            title="Select a force plate CSV (Cancel to finish)",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not path:
            break

        participant = simpledialog.askstring("Participant", "Participant code (e.g. P001)")
        if participant is None:
            continue  # skip this file
        session = simpledialog.askstring("Session", "Session (e.g. T1)")
        if session is None:
            continue

        try:
            rows = process_file(path, participant, session, config, label, results_file)
        except CMJError as e:
            messagebox.showerror("CMJ Analysis", str(e))
            continue

        if rows:
            messagebox.showinfo(
                "CMJ Results",
                f"{len(rows)} trial(s) written.\n\n"
                + _summary(rows[-1])
                + f"\n\nResults appended to:\n{results_file}",
            )
        else:
            messagebox.showinfo("CMJ Results", "No trials written (all skipped or discarded).")

    root.destroy()


if __name__ == "__main__":
    main()
