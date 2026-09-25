"""Thin tkinter shell: file selection, metadata entry, results summary.

The workflow logic lives in the pipeline, inspector, decisions, and
export modules; this module only translates dialogs into calls.
Multi-run exports (e.g. PASCO) are inspected run by run: participant
and session are asked once per file, the trial label once per run.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from ..config import CMJConfig
from ..errors import CMJError
from ..export import append_result, result_row
from ..readers import read_csv_any
from .decisions import apply_decision
from .inspector import inspect_trial

PRESETS = ("HD-raw", "IJSSC2024")


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
    preset: str,
    results_file: str,
) -> list[dict[str, object]]:
    """Analyse every trial in one file through the interactive flow.
    Returns the rows written (skipped or discarded runs contribute none)."""
    trials = read_csv_any(path)
    multi = len(trials) > 1
    rows: list[dict[str, object]] = []

    for i, trial in enumerate(trials, 1):
        prompt = f"Trial number (run {i} of {len(trials)})" if multi else "Trial number (e.g. 1)"
        label = simpledialog.askstring("Trial", prompt, initialvalue=str(i) if multi else "")
        if label is None:
            continue  # skip this run only
        meta = {"participant": participant, "session": session, "trial": label}

        title = f"{participant} {session} Trial {label}"
        if multi:
            title += f" - Run {i}/{len(trials)}"
        decision = inspect_trial(trial, config, config_preset=preset, title=title)
        if decision is None or decision.action == "discard":
            continue

        result = apply_decision(decision, trial, config, config_preset=preset)
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

    preset = simpledialog.askstring(
        "Config preset", f"Config preset ({', '.join(PRESETS)})", initialvalue=PRESETS[0]
    )
    if preset is None:
        root.destroy()
        return
    try:
        config = CMJConfig.preset(preset)
    except ValueError as e:
        messagebox.showerror("Config", str(e))
        root.destroy()
        return

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
            rows = process_file(path, participant, session, config, preset, results_file)
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
