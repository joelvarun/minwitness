"""Render docs/before_after.png from docs/metrics.json.

Three panels, one row per subject throughout:
  left    oracle calls to reach a verified 1-minimal witness
  middle  the witness, against the lower bound minwitness proves for it
  right   how often the monotonicity assumption failed when checked
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minwitness.report import subject_flags

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e3e2de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
ACCENT = "#4a3aa7"
ALERT = "#e34948"


def style(axis):
    axis.set_facecolor(SURFACE)
    axis.xaxis.grid(True, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(GRID)
    axis.tick_params(colors=MUTED, length=0, labelsize=9)


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def draw(report, out_path):
    subjects = sorted(report["subjects"],
                      key=lambda s: s["methods"]["ddmin"]["calls"])
    labels = [s["name"] for s in subjects]
    rows = range(len(subjects))
    summary = report["summary"]

    figure, axes = plt.subplots(
        1, 3, figsize=(17.0, 7.8), sharey=True,
        gridspec_kw={"width_ratios": [1.45, 1.05, 1.0], "wspace": 0.06})
    figure.patch.set_facecolor(SURFACE)

    height = 0.26
    left = axes[0]
    style(left)
    series = [("ddmin", "ddmin (baseline)", SERIES[0]),
              ("probdd", "ProbDD (prior art)", SERIES[1]),
              ("ddmin+store", "minwitness", SERIES[2])]
    for index, (key, label, colour) in enumerate(series):
        values = [s["methods"][key]["calls"] for s in subjects]
        offsets = [r + (1 - index) * height for r in rows]
        left.barh(offsets, values, height=height * 0.92, color=colour,
                  label=label, linewidth=0)
        for offset, value in zip(offsets, values):
            left.text(value + max(values) * 0.012, offset, str(value),
                      va="center", fontsize=7.4, color=MUTED)
    left.set_yticks(list(rows))
    left.set_yticklabels(labels, fontsize=9.5, color=INK)
    left.set_xlabel("oracle calls to a verified 1-minimal witness", fontsize=9.5,
                    color=MUTED)
    left.set_xlim(0, max(s["methods"]["ddmin"]["calls"] for s in subjects) * 1.14)
    left.legend(frameon=False, fontsize=9, loc="upper center",
                bbox_to_anchor=(0.5, -0.075), ncol=3, labelcolor=MUTED)
    left.set_title("Cost of the reduction", fontsize=11.5, color=INK,
                   loc="left", pad=10)

    middle = axes[1]
    style(middle)
    witness = [s["methods"]["ddmin+store"]["witness_units"] for s in subjects]
    bounds = [s["methods"]["ddmin+store"]["bound"] for s in subjects]
    middle.barh(list(rows), witness, height=height * 2.0, color=ACCENT,
                linewidth=0, label="witness (statements kept)")
    flags = [subject_flags(subject) for subject in subjects]
    for row, (bound, flag) in enumerate(zip(bounds, flags)):
        edge = ALERT if flag["monotone_broken"] else ACCENT
        middle.plot([bound], [row], "D", markersize=6.5, color=SURFACE,
                    markeredgecolor=edge, markeredgewidth=1.8, linestyle="none")
    note_x = max(witness) * 1.14
    for row, (kept, bound, flag) in enumerate(zip(witness, bounds, flags)):
        if flag["proved_minimal"]:
            note = "proved minimal at " + str(kept)
        elif flag["monotone_broken"]:
            note = "not monotone, no proof"
        else:
            note = "bound " + str(bound) + " of " + str(kept)
        middle.text(note_x, row, note, va="center", fontsize=7.8, color=MUTED)
    middle.set_xlim(0, max(witness) * 1.95)
    middle.set_xlabel("statements", fontsize=9.5, color=MUTED)
    handles = [
        Line2D([], [], color=ACCENT, linewidth=7, label="witness (statements kept)"),
        Line2D([], [], marker="D", color=SURFACE, markeredgecolor=ACCENT,
               markeredgewidth=1.8, linestyle="none", markersize=6.5,
               label="proved lower bound"),
        Line2D([], [], marker="D", color=SURFACE, markeredgecolor=ALERT,
               markeredgewidth=1.8, linestyle="none", markersize=6.5,
               label="bound refutes the assumption"),
    ]
    middle.legend(handles=handles, frameon=False, fontsize=8.6,
                  loc="upper center", bbox_to_anchor=(0.5, -0.075), ncol=3,
                  labelcolor=MUTED)
    middle.set_title("What the witness is, and what is proved about it",
                     fontsize=11.5, color=INK, loc="left", pad=10)

    right = axes[2]
    style(right)
    breakers = [s["monotone_probe"]["breakers"] for s in subjects]
    colours = [ALERT if count else "#1baf7a" for count in breakers]
    right.barh(list(rows), breakers, height=height * 2.0, color=colours,
               linewidth=0)
    span = max(breakers + [1])
    for row, (count, subject) in enumerate(zip(breakers, subjects)):
        checked = subject["validation"]["checked"]
        violations = subject["validation"]["violations"]
        rate = 100.0 * violations / checked if checked else 0.0
        note = ("monotone" if not count
                else "%d  (%.1f%% of %d predictions wrong)" % (count, rate, checked))
        right.text(span * 1.06, row, note, va="center", fontsize=7.8, color=MUTED)
    right.set_xlim(0, span * 2.5)
    right.set_xlabel("statements whose re-addition breaks the witness",
                     fontsize=9.5, color=MUTED)
    right.set_title("Monotonicity, measured not assumed", fontsize=11.5,
                    color=INK, loc="left", pad=10)

    headline = ("minwitness: %s oracle calls instead of %s on %d real CPython reduction "
                "tasks (%.1fx) for the same witnesses, and the first lower bound on how "
                "small a reproducer can be"
                % ("{:,}".format(summary["calls"]["ddmin+store"]),
                   "{:,}".format(summary["calls"]["ddmin"]),
                   summary["subjects"], summary["speedup_ddmin"]))
    figure.suptitle(headline, fontsize=12.5, color=INK, x=0.012, ha="left", y=0.985)
    figure.text(0.012, 0.018,
                "Every bar is measured: each oracle call compiles a reduced copy of a real stdlib module and runs the probe. "
                "Python " + report["python"] + ", generated " + report["generated"] + ".",
                fontsize=8.5, color=MUTED, ha="left")
    figure.subplots_adjust(left=0.082, right=0.997, top=0.895, bottom=0.145)
    figure.savefig(out_path, dpi=170, facecolor=SURFACE)
    print("wrote " + out_path)


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join("docs", "metrics.json")
    draw(load(source), os.path.join("docs", "before_after.png"))
