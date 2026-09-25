"""Widget-lifecycle tests for the interactive layer.

matplotlib's callback registry stores only a weak reference to a Button,
so a button whose return value is discarded is garbage-collected and its
callback silently disconnects: it renders, but never fires. _button pins
widgets to their figure for the figure's lifetime.
"""
import gc

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backend_bases import MouseEvent  # noqa: E402
from matplotlib.widgets import Button  # noqa: E402

from cmj.app.inspector import _button  # noqa: E402


def teardown_function():
    plt.close("all")


def _click_button_axes(fig, bax):
    """Simulate a full click (press + release) at the axes centre."""
    x, y = bax.transAxes.transform((0.5, 0.5))
    fig.canvas.callbacks.process(
        "button_press_event", MouseEvent("button_press_event", fig.canvas, x, y, 1)
    )
    fig.canvas.callbacks.process(
        "button_release_event", MouseEvent("button_release_event", fig.canvas, x, y, 1)
    )


def test_button_fires_after_gc():
    """A _button-created button must still fire after its local reference
    is dropped and gc runs."""
    fig = plt.figure(figsize=(4, 3))
    calls: list = []
    btn = _button(fig, "Accept", 0.71, 0.02, lambda _: calls.append(1))
    del btn
    gc.collect()

    assert fig._cmj_buttons  # pinned to the figure
    _click_button_axes(fig, fig._cmj_buttons[0].ax)
    assert calls == [1]


def test_unpinned_button_is_the_failure_mode():
    """Documents the bug this guards against: a raw Button whose
    reference is dropped gets collected and never fires."""
    fig = plt.figure(figsize=(4, 3))
    calls: list = []
    btn = Button(fig.add_axes([0.71, 0.02, 0.10, 0.05]), "Accept")
    btn.on_clicked(lambda _: calls.append(1))
    del btn
    gc.collect()

    button_axes = [ax for ax in fig.axes]
    assert len(button_axes) == 1
    _click_button_axes(fig, button_axes[0])
    assert calls == []
