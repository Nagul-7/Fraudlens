"""
Phase 3 - evaluation on the untouched test months (11-12).

Run:  python -m model.evaluate

Headline metric: hit-rate@top-K per 6-hour window - "if police watch the K
riskiest districts each window, what fraction of the districts that actually
had a cash-out did we catch?" - for the model, two baselines and an oracle.
Also: PR-AUC, calibration, drift analysis by test week, hit-rate on districts
that only became hotspots after training, feature importance, and the
ablation without live-chain features.

Writes docs/metrics.md, docs/feature_importance.png, docs/drift_hitrate.png.
"""
import json
import pickle
import sqlite3

import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

from datagen import config as DC
from model import common
from model import config as MC

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#898781"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "legend.frameon": False,
})
N_DISTRICTS = 724


# ---------------------------------------------------------------------------
# Scores for every method, as [n_windows, n_districts] matrices
# ---------------------------------------------------------------------------
def build_scores(test, features, ablation_features):
    booster = lgb.Booster(model_file=MC.MODEL_PATH)
    ablation = lgb.Booster(model_file=MC.ABLATION_MODEL_PATH)
    with open(MC.CALIBRATOR_PATH, "rb") as f:
        calibrator = pickle.load(f)

    raw = booster.predict(test[features])
    test = test.assign(
        model_raw=raw,
        model_prob=calibrator.predict(raw),
        ablation_raw=ablation.predict(test[ablation_features]),
        # b1: the 25 initially known hotspots, then the biggest districts
        b1_static=test["is_hotspot"] * 1000 + test["population_weight"],
        # b2: whoever had the most withdrawals in the past 7 days
        b2_trailing=test["wd_7d"] + 1e-6 * test["population_weight"],
        # oracle: perfect ranking, the ceiling for hit-rate@K
        oracle=test["y_count"].astype(float),
    )
    mats = {c: common.as_window_matrix(test, c) for c in
            ["y", "y_count", "model_raw", "model_prob", "ablation_raw", "b1_static", "b2_trailing", "oracle"]}
    return test, mats, booster


METHODS = [("model", "model_raw", "FraudLens model"),
           ("ablation", "ablation_raw", "model without live-chain features"),
           ("b2", "b2_trailing", "b2: trailing 7-day heat"),
           ("b1", "b1_static", "b1: static 25 hotspots"),
           ("oracle", "oracle", "oracle (perfect ranking)")]


def headline_table(mats):
    rows = []
    for key, col, label in METHODS:
        for k in MC.TOP_KS:
            r = common.hit_rate_at_k(mats[col], mats["y"], k, mats["y_count"])
            rows.append(dict(method=key, label=label, k=k, coverage_of_india=k / N_DISTRICTS,
                             hit_rate=r["hit_rate"], precision=r["precision"],
                             withdrawal_coverage=r["coverage"]))
    return pd.DataFrame(rows)


def new_hotspot_sets(train_end_day, test_start_day):
    """Districts whose FIRST hotspot episode started after the training rows
    end (the trees never saw them hot), and the stricter test-only subset."""
    conn = sqlite3.connect(DC.DB_PATH)
    hist = pd.read_sql("SELECT district_id, start_day, end_day FROM hotspot_history", conn)
    conn.close()
    first = hist.groupby("district_id")["start_day"].min()
    since_train_end = first[first >= train_end_day]
    test_only = first[first >= test_start_day]
    to_mask = lambda ids: np.isin(np.arange(N_DISTRICTS), ids.index.to_numpy())
    return {
        "new since training rows ended": (to_mask(since_train_end), since_train_end),
        "new during test months only": (to_mask(test_only), test_only),
    }


def drift_by_week(mats, test_windows_per_day=4):
    per = {}
    for key, col, _ in METHODS[:4]:
        per[key] = common.hit_rate_at_k(mats[col], mats["y"], 25)["per_window"]
    n_w = len(mats["y"])
    week = np.arange(n_w) // (7 * test_windows_per_day)
    rows = []
    for wk in range(week.max() + 1):
        sel = week == wk
        rows.append(dict(week=wk + 1, days=int(sel.sum() / test_windows_per_day),
                         **{k: float(np.nanmean(v[sel])) for k, v in per.items()}))
    return pd.DataFrame(rows)


def plot_drift(weekly, test_start):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for key, color, label in (("model", BLUE, "FraudLens model"),
                              ("b2", AQUA, "b2: trailing 7-day heat"),
                              ("b1", ORANGE, "b1: static 25 hotspots")):
        ax.plot(weekly["week"], weekly[key], color=color, lw=2, marker="o", ms=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=label)
    # the generator reshuffles hotspots every 30 days; mark those dates for context
    start_day = (test_start - pd.Timestamp(DC.START_DATE)).days
    for d in range(start_day, DC.N_DAYS):
        if d % DC.DRIFT_EVERY_DAYS == 0:
            wk = (d - start_day) / 7 + 1
            ax.axvline(wk, color=GRID, lw=1.5)
            ax.annotate("hotspot drift step", (wk, 0.02), xytext=(4, 0),
                        textcoords="offset points", fontsize=8, color=MUTED)
    ax.set_ylim(0, 1)
    ax.set_xticks(weekly["week"])
    ax.set_xlabel("test week (week %d has %d days)" % (weekly["week"].iloc[-1], weekly["days"].iloc[-1]))
    ax.set_ylabel("hit-rate@25 (mean over 6h windows)")
    ax.set_title("Drift: does the ranking keep up as hotspots move? (test months 11-12)")
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(MC.DRIFT_PLOT, dpi=130)
    plt.close(fig)


def ablation_sweep(mats, ks=(5, 10, 25, 40, 50, 75, 100, 150)):
    """Hit-rate for model vs ablation across many K, to show WHERE the
    live-chain features pay off (the delta grows with K)."""
    rows = []
    for k in ks:
        hm = common.hit_rate_at_k(mats["model_raw"], mats["y"], k)["hit_rate"]
        ha = common.hit_rate_at_k(mats["ablation_raw"], mats["y"], k)["hit_rate"]
        ho = common.hit_rate_at_k(mats["oracle"], mats["y"], k)["hit_rate"]
        rows.append(dict(k=k, model=hm, ablation=ha, delta=hm - ha, oracle=ho))
    return pd.DataFrame(rows)


def ablation_mechanism(test, mats, k=50):
    """What kind of district does the full model catch that the ablation misses?
    Compares their trailing heat and live-chain signal against typical positives."""
    def flags(score):
        order = np.argsort(-score, axis=1, kind="stable")[:, :k]
        f = np.zeros_like(mats["y"], dtype=bool)
        np.put_along_axis(f, order, True, axis=1)
        return f
    fm, fa = flags(mats["model_raw"]), flags(mats["ablation_raw"])
    pos = mats["y"] > 0
    won = fm & pos & ~fa
    lost = fa & pos & ~fm
    wd7 = common.as_window_matrix(test, "wd_7d")
    chains = common.as_window_matrix(test, "n_active_chains_here")
    return dict(k=k, won=int(won.sum()), lost=int(lost.sum()),
                wd7_all=float(wd7[pos].mean()), wd7_won=float(wd7[won].mean()),
                chains_all=float(chains[pos].mean()), chains_won=float(chains[won].mean()))


def importance(booster, features):
    gain = booster.feature_importance(importance_type="gain")
    imp = pd.DataFrame({"feature": features, "gain": gain}).sort_values("gain", ascending=False)
    imp["gain_share"] = imp["gain"] / imp["gain"].sum()
    imp["rank"] = np.arange(1, len(imp) + 1)
    imp["group"] = np.where(imp["feature"].isin(MC.LIVE_CHAIN_FEATURES), "live chain",
                   np.where(imp["feature"].str.startswith(MC.NATIONWIDE_COMPLAINT_PREFIX),
                            "nationwide complaints", "other"))
    return imp


def plot_importance(imp):
    top = imp.head(20).iloc[::-1]
    colors = top["group"].map({"live chain": ORANGE, "nationwide complaints": AQUA, "other": BLUE})
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(top["feature"], top["gain_share"], color=colors, height=0.7)
    ax.set_xlabel("share of total gain")
    ax.set_title("Feature importance (gain) - top 20")
    ax.grid(axis="y", visible=False)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="rolling / static / calendar"),
                       Patch(color=ORANGE, label="live-chain features"),
                       Patch(color=AQUA, label="nationwide complaint counts")], loc="lower right")
    fig.tight_layout()
    fig.savefig(MC.IMPORTANCE_PLOT, dpi=130)
    plt.close(fig)


def reliability(prob, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(prob, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        sel = idx == b
        if sel.sum():
            rows.append(dict(bin=f"{edges[b]:.1f}-{edges[b + 1]:.1f}", n=int(sel.sum()),
                             mean_predicted=float(prob[sel].mean()), observed=float(y[sel].mean())))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def as_int(v):
    return str(int(round(float(v))))


def md_table(df, cols, fmt):
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = "".join("| " + " | ".join(fmt[c](r[c]) if c in fmt else str(r[c]) for c in cols) + " |\n"
                   for _, r in df.iterrows())
    return head + body


def main():
    df = common.load_table()
    train, valid, test = common.split(df)
    with open(MC.FEATURES_PATH) as f:
        meta = json.load(f)
    features, ablation_features = meta["features"], meta["ablation_features"]
    del df

    test, mats, booster = build_scores(test, features, ablation_features)
    y_flat = mats["y"].ravel()
    n_windows = len(mats["y"])
    test_start = pd.Timestamp(MC.TEST_START)
    train_end_day = (train["window_start"].max() - pd.Timestamp(DC.START_DATE)).days + 1
    test_start_day = (test_start - pd.Timestamp(DC.START_DATE)).days

    # 1. headline
    head = headline_table(mats)

    # 2. PR-AUC + calibration
    prauc = {key: average_precision_score(y_flat, mats[col].ravel()) for key, col, _ in METHODS[:4]}
    brier_raw = brier_score_loss(y_flat, mats["model_raw"].ravel())
    brier_cal = brier_score_loss(y_flat, mats["model_prob"].ravel())
    rel = reliability(mats["model_prob"].ravel(), y_flat)

    # 3. drift
    weekly = drift_by_week(mats)
    plot_drift(weekly, test_start)
    cohorts = new_hotspot_sets(train_end_day, test_start_day)
    cohort_rows = []
    for name, (mask, first) in cohorts.items():
        for key, col, label in METHODS[:4]:
            r = common.hit_rate_at_k(mats[col], mats["y"], 25, subset=mask)
            cohort_rows.append(dict(cohort=name, n_districts=int(mask.sum()), method=label,
                                    hit_rate_25=r["hit_rate"], n_windows=r["n_windows"]))
    cohort_df = pd.DataFrame(cohort_rows)

    # 4. importance
    imp = importance(booster, features)
    plot_importance(imp)

    # 5. ablation deltas + where they come from
    abl = head.pivot(index="k", columns="method", values="hit_rate")
    sweep = ablation_sweep(mats)
    mech = ablation_mechanism(test, mats)

    # ---- write metrics.md ----
    pct = lambda v: f"{v:.1%}"
    f3 = lambda v: f"{v:.3f}"
    L = []
    L += ["# Metrics (test months 11-12, synthetic data)", "",
          "> All numbers are measured on the synthetic world from `datagen/`. They show the",
          "> pipeline learns the encoded fraud physics; they are NOT claims about real-world accuracy.", "",
          "## Setup", "",
          f"- train: {len(train):,} rows, {train['window_start'].min().date()} to {train['window_start'].max().date()}, {train['y'].mean():.2%} positive",
          f"- validation (early stopping + isotonic calibration only): {len(valid):,} rows, {valid['window_start'].min().date()} to {valid['window_start'].max().date()}",
          f"- test (untouched until this script): {len(test):,} rows = {n_windows} windows x {N_DISTRICTS} districts, {test_start.date()} to {test['window_start'].max().date()}, {test['y'].mean():.2%} positive",
          f"- positives per test window: mean {mats['y'].sum(axis=1).mean():.1f} districts (so hit-rate@25 cannot reach 100% - see the oracle row)",
          f"- model: LightGBM, {meta['best_iteration']} trees (early-stopped), scale_pos_weight, {len(features)} features; ablation: {meta['ablation_best_iteration']} trees, {len(ablation_features)} features",
          f"- rankings use the raw model score; calibrated probabilities (isotonic, fit on validation) are reported below", ""]
    L += ["## Headline: hit-rate@top-K per 6-hour window", "",
          "\"If police watch the K riskiest districts each window, what fraction of the districts",
          "that actually had a fraud cash-out do we catch?\" Precision@K = fraction of flagged",
          "districts that had one; withdrawal coverage = share of individual withdrawals inside",
          "flagged districts. Averaged over test windows with at least one cash-out.", ""]
    for k in MC.TOP_KS:
        sub = head[head["k"] == k]
        L += [f"### K = {k}  (watching {k}/{N_DISTRICTS} = {k / N_DISTRICTS:.1%} of India's districts)", "",
              md_table(sub, ["label", "hit_rate", "precision", "withdrawal_coverage"],
                       {"hit_rate": pct, "precision": pct, "withdrawal_coverage": pct}), ""]
    L += ["## PR-AUC (test)", "",
          md_table(pd.DataFrame([dict(method=label, pr_auc=prauc[key]) for key, _, label in METHODS[:4]]),
                   ["method", "pr_auc"], {"pr_auc": f3}),
          f"Random ranking would score {test['y'].mean():.3f}.", ""]
    L += ["## Calibration (isotonic, fitted on the validation slice only)", "",
          f"- Brier score on test: raw {brier_raw:.4f} -> calibrated {brier_cal:.4f} (lower is better; scale_pos_weight inflates raw scores)", "",
          md_table(rel, ["bin", "n", "mean_predicted", "observed"], {"mean_predicted": f3, "observed": f3}), ""]
    L += ["## Drift analysis", "", f"![drift](drift_hitrate.png)", "",
          "hit-rate@25 per test week (hotspots are reshuffled by the generator every 30 days):", "",
          md_table(weekly, ["week", "days", "model", "ablation", "b2", "b1"],
                   dict({c: pct for c in ["model", "ablation", "b2", "b1"]}, week=as_int, days=as_int)), "",
          "### Cash-outs in districts that were never hot during training", "",
          "hit-rate@25 restricted to positives in districts whose first hotspot episode started",
          f"after the training rows end (day {train_end_day}, {train['window_start'].max().date()}) or after the",
          f"test start (day {test_start_day}, {test_start.date()}). n_windows = test windows containing such a cash-out.", ""]
    for name, (mask, first) in cohorts.items():
        ids = ", ".join(f"{i} (day {int(d)})" for i, d in first.items())
        L += [f"**{name}** - {int(mask.sum())} districts: {ids}", "",
              md_table(cohort_df[cohort_df["cohort"] == name], ["method", "hit_rate_25", "n_windows"], {"hit_rate_25": pct}), ""]
    live_ranks = imp[imp["group"] == "live chain"].sort_values("rank")
    nat = imp[imp["group"] == "nationwide complaints"]
    L += ["## Feature importance (gain)", "", "![importance](feature_importance.png)", "",
          md_table(imp.head(20), ["rank", "feature", "gain_share", "group"], {"gain_share": pct}), "",
          f"- live-chain features: ranks " + ", ".join(f"{r.feature} #{r.rank}" for r in live_ranks.itertuples())
          + f" - together {live_ranks['gain_share'].sum():.1%} of total gain",
          f"- nationwide complaint features (15): best rank #{int(nat['rank'].min())}, together {nat['gain_share'].sum():.1%} of total gain", ""]
    L += ["## Ablation: remove the six live-chain features", "",
          "Same recipe, same split, 36 features instead of 42.", "",
          md_table(pd.DataFrame([dict(k=k, with_chains=abl.loc[k, "model"], without=abl.loc[k, "ablation"],
                                      delta=abl.loc[k, "model"] - abl.loc[k, "ablation"]) for k in MC.TOP_KS]),
                   ["k", "with_chains", "without", "delta"],
                   {"k": as_int, "with_chains": pct, "without": pct, "delta": lambda v: f"{v:+.1%}"}), "",
          f"PR-AUC with {prauc['model']:.3f} vs without {prauc['ablation']:.3f} (a large gap, while the",
          "hit-rate gap at K=25 is small). The reason is that the benefit is concentrated deeper in",
          "the ranking - sweeping K shows where it appears:", "",
          md_table(sweep, ["k", "model", "ablation", "delta", "oracle"],
                   {"k": as_int, "model": pct, "ablation": pct, "delta": lambda v: f"{v:+.1%}", "oracle": pct}), "",
          f"At K={mech['k']} the full model catches {mech['won']:,} positive district-windows the ablation misses,",
          f"while the ablation catches {mech['lost']:,} the full model misses. Those model-only catches are COLD",
          "districts, not the obvious corridors:", "",
          md_table(pd.DataFrame([
              dict(group="all positive district-windows", wd7=mech["wd7_all"], chains=mech["chains_all"]),
              dict(group="caught by model only (K=50)", wd7=mech["wd7_won"], chains=mech["chains_won"])]),
              ["group", "wd7", "chains"], {"wd7": f3, "chains": f3}), "",
          "`wd7` = withdrawals in that district over the previous 7 days; `chains` = live chains holding",
          "money there. The districts the live-chain features rescue have almost no recent history",
          f"({mech['wd7_won']:.1f} vs {mech['wd7_all']:.1f} trailing withdrawals), so no amount of trailing heat could rank them.",
          "They are visible only because stolen money is sitting in their accounts right now. That is the",
          "cold-start case the differentiator exists for.", ""]
    with open(MC.METRICS_PATH, "w") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote {MC.METRICS_PATH}, {MC.DRIFT_PLOT}, {MC.IMPORTANCE_PLOT}")


if __name__ == "__main__":
    main()
