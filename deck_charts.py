"""
The charts the deck actually needs.

Two pictures, both readable by someone who has never heard of machine learning:

  1. money_coverage.png - as the watchlist grows, how much of the stolen cash
     sits inside it. FraudLens against a trailing 7-day heat map.
  2. deployment_window.png - of the money in the top-25 watchlist, how much is
     still inside the ATM network N hours after the alert.

Palette and chrome follow the same system as model/evaluate.py.
"""
import json
import os
import pickle
from pathlib import Path

import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sqlite3

from datagen import config as DC
from model import common
from model import config as MC

# The repo's shared modules read data/, model/ and docs/ by repo-relative path, so run
# from the repo root no matter where this script is launched from.
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, SECOND, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE, "axes.labelcolor": SECOND,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["DejaVu Sans"], "font.size": 12,
    "axes.titlecolor": INK, "axes.titlesize": 15, "axes.titleweight": "bold",
    "legend.frameon": False,
})
WINDOW_HOURS = 6


def load():
    df = common.load_table()
    _, _, test = common.split(df)
    del df
    with open(MC.FEATURES_PATH) as f:
        meta = json.load(f)
    booster = lgb.Booster(model_file=MC.MODEL_PATH)
    test = test.assign(
        model_raw=booster.predict(test[meta["features"]]),
        b2_trailing=test["wd_7d"] + 1e-6 * test["population_weight"])

    con = sqlite3.connect("data/fraudlens.db")
    wd = pd.read_sql("SELECT district_id, amount, timestamp FROM withdrawals",
                     con, parse_dates=["timestamp"])
    con.close()
    start = pd.Timestamp(DC.START_DATE)
    secs = (wd["timestamp"] - start).dt.total_seconds()
    wd["window_idx"] = (secs // (WINDOW_HOURS * 3600)).astype(int)
    wd["offset_h"] = secs / 3600.0 - wd["window_idx"] * WINDOW_HOURS

    windows = np.sort(test["window_idx"].unique())
    districts = np.sort(test["district_id"].unique())
    w_pos = {w: i for i, w in enumerate(windows)}
    d_pos = {d: i for i, d in enumerate(districts)}
    wd = wd[wd["window_idx"].isin(w_pos) & wd["district_id"].isin(d_pos)]
    wi = wd["window_idx"].map(w_pos).to_numpy()
    di = wd["district_id"].map(d_pos).to_numpy()
    amt = wd["amount"].to_numpy()
    off = wd["offset_h"].to_numpy()

    money = np.zeros((len(windows), len(districts)))
    np.add.at(money, (wi, di), amt)
    return test, money, (wi, di, amt, off, money.shape)


def coverage_curve(score, money, ks):
    """Share of all withdrawn rupees inside the top-K districts, per K."""
    order = np.argsort(-score, axis=1, kind="stable")
    total = money.sum()
    ranked = np.take_along_axis(money, order, axis=1)
    cum = np.cumsum(ranked, axis=1).sum(axis=0)
    return np.array([cum[k - 1] / total for k in ks])


def chart_money_coverage(test, money):
    mats = {c: common.as_window_matrix(test, c) for c in ["model_raw", "b2_trailing"]}
    ks = np.arange(1, 101)
    model = coverage_curve(mats["model_raw"], money, ks) * 100
    heat = coverage_curve(mats["b2_trailing"], money, ks) * 100

    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=200)
    ax.plot(ks, model, color=BLUE, lw=2.4, zorder=3)
    ax.plot(ks, heat, color=ORANGE, lw=2.4, zorder=2)

    k = 25
    ax.plot([k, k], [0, model[k - 1]], color=BASELINE, lw=1.2, ls=(0, (3, 3)), zorder=1)
    ax.scatter([k], [model[k - 1]], s=70, color=BLUE, zorder=5,
               edgecolor=SURFACE, linewidth=2)
    ax.annotate(f"25 districts\n{model[k-1]:.0f}% of the stolen cash",
                xy=(k, model[k - 1]), xytext=(k + 7, model[k - 1] - 20),
                color=INK, fontsize=12, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=BASELINE, lw=1.2))

    ax.text(101, model[-1], "  FraudLens", color=BLUE, fontsize=12.5,
            fontweight="bold", va="center")
    ax.text(101, heat[-1] - 3.5, "  Past-week\n  hotspot map", color=ORANGE,
            fontsize=12.5, fontweight="bold", va="center")

    ax.set_title("How much of the stolen cash is inside the districts we ask police to watch")
    ax.set_xlabel("Districts on the watchlist  (out of 724 in India)")
    ax.set_ylabel("Share of all fraud cash-outs (%)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    fig.subplots_adjust(right=0.80)
    fig.savefig("docs/chart_money_coverage.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return model, heat


def chart_deployment_window(test, money, raw):
    """The officer's question: what does an hour of delay cost?

    Wider and shorter than the coverage chart because it sits beside a column
    of text on the impact slide. The per-hour drop is annotated because that
    is the number a control room acts on, not the bar heights.
    """
    wi, di, amt, off, shape = raw
    mats = common.as_window_matrix(test, "model_raw")
    order = np.argsort(-mats, axis=1, kind="stable")[:, :25]
    flagged = np.zeros(shape, dtype=bool)
    np.put_along_axis(flagged, order, True, axis=1)

    hours = [0, 1, 2, 3]
    vals = []
    for h in hours:
        m = np.zeros(shape)
        late = off >= h
        np.add.at(m, (wi[late], di[late]), amt[late])
        vals.append((m * flagged).sum() / 1e7)

    fig, ax = plt.subplots(figsize=(9.6, 4.15), dpi=200)
    xs = np.arange(len(hours))
    bars = ax.bar(xs, vals, width=0.5, color=BLUE, zorder=3)
    for bar in bars:
        bar.set_linewidth(2); bar.set_edgecolor(SURFACE)
    for x, v in zip(xs, vals):
        ax.text(x, v + 2.4, f"Rs {v:.0f} cr", ha="center", color=INK,
                fontsize=13.5, fontweight="bold")

    # What each hour of delay costs: the previous level as a dashed guide over
    # the next bar, with the drop written just beneath it. Kept clear of the
    # value labels, which sit directly on each bar.
    for i in range(len(vals) - 1):
        drop = vals[i] - vals[i + 1]
        ax.plot([i + 0.75, i + 1.25], [vals[i], vals[i]], color=ORANGE, lw=1.6,
                ls=(0, (4, 3)), zorder=4)
        ax.text(i + 1, vals[i] - 7.0, f"−Rs {drop:.0f} cr", ha="center",
                color=ORANGE, fontsize=11.5, fontweight="bold", zorder=5)

    ax.set_title("Every hour of delay costs about Rs 16 crore", fontsize=16)
    ax.set_xticks(xs)
    ax.set_xticklabels(["alert\nissued", "1 hour\nlater", "2 hours\nlater", "3 hours\nlater"])
    ax.set_ylabel("Still in the account,\nstill freezable (Rs crore)", fontsize=11)
    ax.set_ylim(0, max(vals) * 1.28)
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="x", labelsize=11)
    fig.savefig("docs/chart_deployment_window.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return vals


def main():
    test, money, raw = load()
    model, heat = chart_money_coverage(test, money)
    vals = chart_deployment_window(test, money, raw)
    out = {
        "coverage_at": {k: {"model": float(model[k - 1]), "heat": float(heat[k - 1])}
                        for k in (10, 25, 50, 100)},
        "deployment_window_crore": {h: float(v) for h, v in zip([0, 1, 2, 3], vals)},
    }
    with open("docs/deck_chart_data.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
