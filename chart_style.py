"""Colours and styling for every report chart, defined once.

The same palette as the charts in my Python learning repo. The colours were
checked with a colour-blindness validator, in this fixed order, so neighbouring
colours stay distinguishable for the common types of colour blindness.

Colour follows the STATE: "phone" is the same magenta in every chart, so once
you've learnt it you can read any chart at a glance.
"""
import matplotlib as mpl

from posture import State

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Fixed categorical order. Assign in this order; never cycle past 8.
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
         "#e87ba4", "#008300", "#6250d6", "#e34948"]

STATE_COLORS = {
    State.GOOD: SLOTS[0],
    State.SLOUCH: SLOTS[1],
    State.TOO_CLOSE: SLOTS[2],
    State.TILT: SLOTS[3],
    State.PHONE: SLOTS[4],
}
STATE_LABELS = {
    State.GOOD: "Good posture",
    State.SLOUCH: "Slouching",
    State.TOO_CLOSE: "Too close",
    State.TILT: "Head tilted",
    State.PHONE: "Phone",
}


def apply() -> None:
    """Thin marks, quiet axes and grid, clear text."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "text.color": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.labelcolor": INK_SECONDARY,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "lines.linewidth": 2,
        "legend.frameon": False,
        "legend.fontsize": 9,
    })


def title(ax, text: str, sub: str | None = None) -> None:
    """Title = the takeaway ("You slouch most at 4 pm"), subtitle = what is measured."""
    ax.set_title(text, pad=26 if sub else 12)
    if sub:
        ax.text(0, 1.03, sub, transform=ax.transAxes, color=INK_SECONDARY,
                fontsize=9.5, va="bottom")
