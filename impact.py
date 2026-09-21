"""
Operational impact of the FraudLens ranking, in rupees and hours.

Everything the deck's headline numbers come from. Same test split, same
scoring code and same top-K rule as model/evaluate.py - this only adds the
two questions an officer actually asks:

  1. Of the money that walked out of ATMs, how much was inside the districts
     we told them to watch?
  2. How much warning did the alert give before the first rupee came out?

All figures are on the synthetic world. They measure the ranking, not reality.
"""
import json
import os
import pickle
from pathlib import Path

import lightgbm as lgb
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

WINDOW_HOURS = 6
DB = "data/fraudlens.db"
OUT_JSON = "docs/impact.json"
OUT_MD = "docs/impact.md"


def load_test_scores():
    """Test rows with the model score and the trailing-heat baseline."""
    df = common.load_table()
    _, _, test = common.split(df)
    del df
    with open(MC.FEATURES_PATH) as f:
        meta = json.load(f)
    booster = lgb.Booster(model_file=MC.MODEL_PATH)
    with open(MC.CALIBRATOR_PATH, "rb") as f:
        calibrator = pickle.load(f)

    raw = booster.predict(test[meta["features"]])
    test = test.assign(
        model_raw=raw,
        model_prob=calibrator.predict(raw),
        b2_trailing=test["wd_7d"] + 1e-6 * test["population_weight"],
    )
    return test


def money_matrix(test):
    """Rupees withdrawn per (window, district), aligned to the test matrices."""
    con = sqlite3.connect(DB)
    wd = pd.read_sql(
        "SELECT district_id, amount, timestamp FROM withdrawals", con,
        parse_dates=["timestamp"])
    con.close()

    start = pd.Timestamp(DC.START_DATE)
    wd["window_idx"] = ((wd["timestamp"] - start).dt.total_seconds()
                        // (WINDOW_HOURS * 3600)).astype(int)
    # hours from the start of the window to this withdrawal
    wd["offset_h"] = ((wd["timestamp"] - start).dt.total_seconds() / 3600.0
                      - wd["window_idx"] * WINDOW_HOURS)

    windows = np.sort(test["window_idx"].unique())
    districts = np.sort(test["district_id"].unique())
    w_pos = {w: i for i, w in enumerate(windows)}
    d_pos = {d: i for i, d in enumerate(districts)}

    wd = wd[wd["window_idx"].isin(w_pos) & wd["district_id"].isin(d_pos)]
    wi = wd["window_idx"].map(w_pos).to_numpy()
    di = wd["district_id"].map(d_pos).to_numpy()

    amounts = wd["amount"].to_numpy()
    offsets = wd["offset_h"].to_numpy()
    money = np.zeros((len(windows), len(districts)))
    np.add.at(money, (wi, di), amounts)

    # money still inside the network d hours after the window opened
    offset_money = {}
    for d in (1, 2, 3):
        m = np.zeros_like(money)
        late = offsets >= d
        np.add.at(m, (wi[late], di[late]), amounts[late])
        offset_money[d] = m

    # earliest withdrawal offset per cell -> the warning the alert would have given
    first = np.full((len(windows), len(districts)), np.nan)
    order = np.argsort(-wd["offset_h"].to_numpy())  # write latest first, earliest wins
    np.put_along_axis(first.reshape(-1)[None, :],
                      (wi[order] * len(districts) + di[order])[None, :],
                      wd["offset_h"].to_numpy()[order][None, :], axis=1)
    return money, first, offset_money, len(windows), len(districts)


def topk_mask(score, k):
    order = np.argsort(-score, axis=1, kind="stable")[:, :k]
    flagged = np.zeros(score.shape, dtype=bool)
    np.put_along_axis(flagged, order, True, axis=1)
    return flagged


def main():
    test = load_test_scores()
    money, first_h, offset_money, n_w, n_d = money_matrix(test)

    mats = {c: common.as_window_matrix(test, c)
            for c in ["y", "model_raw", "b2_trailing"]}
    assert mats["y"].shape == money.shape, (mats["y"].shape, money.shape)

    total_money = money.sum()
    n_wd_windows = int((money > 0).any(axis=1).sum())
    results = {
        "test_windows": int(n_w),
        "districts": int(n_d),
        "total_rupees_withdrawn": float(total_money),
        "windows_with_a_cashout": n_wd_windows,
        "by_k": {},
    }

    for k in (10, 25, 50):
        row = {}
        for name, col in (("model", "model_raw"), ("trailing_heat", "b2_trailing")):
            flagged = topk_mask(mats[col], k)
            caught = float((money * flagged).sum())
            row[name] = {
                "rupees_inside_watchlist": caught,
                "share_of_rupees": caught / total_money,
            }
            if name == "model":
                # The alert is available when the window opens (features use only
                # data visible before it). Warning before the FIRST rupee in a
                # caught district is therefore that withdrawal's offset into the
                # window - an honest and deliberately unflattering number.
                hit = flagged & (money > 0)
                lead = first_h[hit]
                lead = lead[~np.isnan(lead)]
                row["lead_time_hours"] = {
                    "median": float(np.median(lead)),
                    "mean": float(np.mean(lead)),
                    "p25": float(np.percentile(lead, 25)),
                    "p75": float(np.percentile(lead, 75)),
                    "n_cells": int(lead.size),
                }
                # What actually matters operationally: if a team takes D hours
                # to be in position, how much of the flagged money is still
                # inside the ATM network when they get there?
                still = {}
                for d in (1, 2, 3):
                    late = np.where(offset_money[d] * flagged > 0,
                                    offset_money[d] * flagged, 0.0).sum()
                    still[d] = {"rupees": float(late),
                                "share_of_flagged": float(late / caught) if caught else 0.0}
                row["recoverable_after_hours"] = still
        row["rupee_margin_pts"] = (row["model"]["share_of_rupees"]
                                   - row["trailing_heat"]["share_of_rupees"]) * 100
        results["by_k"][k] = row

    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)

    cr = lambda x: x / 1e7  # rupees -> crore
    lines = [
        "# Operational impact (test months 11-12, synthetic data)",
        "",
        "> Measured on the synthetic world. These figures describe the ranking's",
        "> operational value, not real-world recovery.",
        "",
        f"- test windows: {n_w} ({n_wd_windows} had at least one cash-out)",
        f"- total withdrawn in the test period: Rs {cr(total_money):.1f} crore",
        "",
        "## Money inside the watchlist",
        "",
        "| watchlist size | share of India | FraudLens | trailing 7-day heat | margin |",
        "|---|---|---|---|---|",
    ]
    for k in (10, 25, 50):
        r = results["by_k"][k]
        lines.append(
            f"| top {k} | {k/724*100:.1f}% | "
            f"Rs {cr(r['model']['rupees_inside_watchlist']):.1f} cr "
            f"({r['model']['share_of_rupees']*100:.1f}%) | "
            f"Rs {cr(r['trailing_heat']['rupees_inside_watchlist']):.1f} cr "
            f"({r['trailing_heat']['share_of_rupees']*100:.1f}%) | "
            f"+{r['rupee_margin_pts']:.1f} pts |")

    lines += ["", "## Warning before the first rupee leaves", "",
              "The alert is available when the 6-hour window opens. This is the gap",
              "to the first withdrawal in a district we flagged - a deliberately",
              "unflattering number, because cash starts moving immediately.", ""]
    for k in (10, 25, 50):
        lt = results["by_k"][k]["lead_time_hours"]
        lines.append(
            f"- top {k}: median {lt['median']*60:.0f} min "
            f"(IQR {lt['p25']*60:.0f}-{lt['p75']*60:.0f} min) over {lt['n_cells']:,} caught district-windows")

    lines += ["", "## Money still in the network when a team arrives", "",
              "The operationally honest question: a team takes time to be in",
              "position. How much of the flagged money has not yet been withdrawn?", "",
              "| watchlist | after 1 h | after 2 h | after 3 h |", "|---|---|---|---|"]
    for k in (10, 25, 50):
        r = results["by_k"][k]["recoverable_after_hours"]
        lines.append(
            f"| top {k} | Rs {cr(r[1]['rupees']):.1f} cr ({r[1]['share_of_flagged']*100:.0f}%) "
            f"| Rs {cr(r[2]['rupees']):.1f} cr ({r[2]['share_of_flagged']*100:.0f}%) "
            f"| Rs {cr(r[3]['rupees']):.1f} cr ({r[3]['share_of_flagged']*100:.0f}%) |")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
