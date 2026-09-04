"""
Sanity checks for the generated world.

Run:  python -m datagen.validate

Prints row counts and physics checks, and saves four plots into docs/:
    plot_events_over_time.png   daily complaints / withdrawals + hour-of-day
    plot_geography.png          where withdrawals happen (centroid map)
    plot_hop_histogram.png      mule-chain depth
    plot_time_to_cashout.png    hours from fraud to first ATM withdrawal
"""
import sqlite3

import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from datagen import config as C

DOCS = "docs"

# Colours from the project chart palette (one hue per series, muted chrome).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": "sans-serif", "font.size": 10,
    "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "legend.frameon": False,
})


def load(conn, table, parse=()):
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    for col in parse:
        df[col] = pd.to_datetime(df[col])
    return df


def print_row_counts(conn):
    print("row counts")
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for name in names:
        n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name:20s} {n:>10,d}")


def physics_checks(districts, complaints, transactions, withdrawals, hist):
    """Numbers that should match the physics rules in config.py."""
    print("\nphysics checks")
    n_c = len(complaints)
    cashout_chains = withdrawals["complaint_id"].nunique()
    print(f"  complaints/day               {n_c / C.N_DAYS:8.1f}   (target ~{C.COMPLAINTS_PER_DAY})")
    print(f"  chains that cash out         {cashout_chains / n_c:8.1%}   (target {C.CASHOUT_PROB:.0%})")
    print(f"  max single withdrawal        {withdrawals['amount'].max():8,.0f}   (limit {C.WITHDRAWAL_MAX:,})")

    # share of withdrawals inside an ACTIVE hotspot on that day
    day = (withdrawals["timestamp"] - pd.Timestamp(C.START_DATE)).dt.days.to_numpy()
    active = np.zeros((C.N_DAYS + 5, len(districts)), dtype=bool)
    for h in hist.itertuples():
        end = C.N_DAYS + 5 if pd.isna(h.end_day) else int(h.end_day)
        active[int(h.start_day):end, int(h.district_id)] = True
    in_hot = active[np.minimum(day, C.N_DAYS + 4), withdrawals["district_id"].to_numpy()]
    print(f"  withdrawals in active hotspot{in_hot.mean():8.1%}   (target ~{C.HOTSPOT_SHARE:.0%} of chains)")
    print(f"  hotspot episodes (drift)     {len(hist):8d}   ({C.INITIAL_HOTSPOTS.__len__()} initial)")

    depth = transactions.groupby("complaint_id")["hop_number"].max()
    print(f"  chain depth min/mean/max     {depth.min()}/{depth.mean():.1f}/{depth.max()}   (target {C.HOPS_MIN}-{C.HOPS_MAX})")

    first_wd = withdrawals.groupby("complaint_id")["timestamp"].min()
    hours = (first_wd - complaints.set_index("complaint_id").loc[first_wd.index, "timestamp"]).dt.total_seconds() / 3600
    print(f"  fraud->first cash-out hours  p10={hours.quantile(.1):.1f} median={hours.median():.1f} p90={hours.quantile(.9):.1f}")

    hour = withdrawals["timestamp"].dt.hour
    night = hour.isin([5, 6, 7, 8, 19, 20, 21, 22]).mean()
    print(f"  withdrawals in peak hours    {night:8.1%}   (8 of 24 hours; uniform would be 33%)")
    sunday = (withdrawals["timestamp"].dt.weekday == 6).mean()
    print(f"  withdrawals on Sundays       {sunday:8.1%}   (uniform would be 14.3%)")

    # what Phase 2 will predict: does a (district, 6h window) have a withdrawal?
    windows = C.N_DAYS * 4 * len(districts)
    positives = withdrawals.assign(w=withdrawals["timestamp"].dt.floor("6h")) \
        .groupby(["district_id", "w"]).ngroups
    print(f"  positive (district,6h) rate  {positives / windows:8.2%}   of {windows:,} windows")


def plot_events_over_time(complaints, withdrawals):
    horizon = pd.Timestamp(C.START_DATE) + pd.Timedelta(days=C.N_DAYS)
    daily_c = complaints.set_index("timestamp").resample("D").size()[:horizon - pd.Timedelta(days=1)]
    daily_w = withdrawals.set_index("timestamp").resample("D").size()[:horizon - pd.Timedelta(days=1)]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [3, 2]})

    ax1.plot(daily_c.index, daily_c.values, color=BLUE, lw=2, label="complaints")
    ax1.plot(daily_w.index, daily_w.values, color=ORANGE, lw=2, label="ATM withdrawals")
    ax1.set_title("Daily events over the 12-month synthetic history")
    ax1.set_ylabel("events per day")
    ax1.set_ylim(bottom=0)
    ax1.legend(loc="upper left")

    hours = np.arange(24)
    hc = complaints["timestamp"].dt.hour.value_counts().reindex(hours, fill_value=0)
    hw = withdrawals["timestamp"].dt.hour.value_counts().reindex(hours, fill_value=0)
    ax2.bar(hours - 0.2, hc / hc.sum(), width=0.38, color=BLUE, label="complaints")
    ax2.bar(hours + 0.2, hw / hw.sum(), width=0.38, color=ORANGE, label="ATM withdrawals")
    ax2.set_title("Hour-of-day pattern (share of events)")
    ax2.set_xlabel("hour of day")
    ax2.set_xticks(hours)
    ax2.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(f"{DOCS}/plot_events_over_time.png", dpi=130)
    plt.close(fig)


def plot_geography(districts, withdrawals, hist):
    counts = withdrawals.groupby("district_id").size()
    d = districts.set_index("district_id")
    d["withdrawals"] = counts.reindex(d.index, fill_value=0)
    hot = d["is_hotspot"] == 1                                   # the initial 25
    drifted = d.index.isin(hist["district_id"]) & ~hot           # became hotspots later
    other = ~hot & ~drifted

    fig, ax = plt.subplots(figsize=(9, 9.5))
    ax.grid(False)
    ax.scatter(d["lon"], d["lat"], s=6, color=GRID, zorder=1, label="district (no events)")
    size = 4 + d["withdrawals"] / d["withdrawals"].max() * 400
    ax.scatter(d.loc[other, "lon"], d.loc[other, "lat"], s=size[other], color=BLUE,
               alpha=0.55, edgecolor=SURFACE, lw=0.6, zorder=2, label="other district (background noise)")
    ax.scatter(d.loc[drifted, "lon"], d.loc[drifted, "lat"], s=size[drifted], color=AQUA,
               alpha=0.75, edgecolor=SURFACE, lw=0.6, zorder=3, label="drifted-in hotspot (appeared later)")
    ax.scatter(d.loc[hot, "lon"], d.loc[hot, "lat"], s=size[hot], color=ORANGE,
               alpha=0.8, edgecolor=SURFACE, lw=0.6, zorder=4, label="initial hotspot")
    # one label per hotspot region, offset away from the cluster with a leader line
    regions = {
        "Jamtara belt (Jharkhand)": (["Jharkhand"], (40, -70)),
        "Delhi NCR / Mewat": (["Delhi", "Haryana", "Uttar Pradesh"], (-95, 40)),
        "Bharatpur-Alwar (Rajasthan)": (["Rajasthan"], (-120, -60)),
        "Kolkata metro (West Bengal)": (["West Bengal"], (30, -75)),
        "Lower Assam": (["Assam"], (10, 60)),
    }
    for label, (states, offset) in regions.items():
        grp = d[hot & d["state"].isin(states)]
        ax.annotate(label, (grp["lon"].mean(), grp["lat"].mean()), xytext=offset,
                    textcoords="offset points", fontsize=9, color=INK,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.set_title("Where cash-outs happen: bubble size = withdrawals in 12 months")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_aspect("equal")
    ax.legend(loc="lower left", markerscale=1.0)
    fig.tight_layout()
    fig.savefig(f"{DOCS}/plot_geography.png", dpi=130)
    plt.close(fig)
    return d.sort_values("withdrawals", ascending=False)


def plot_hop_histogram(transactions):
    per_chain = transactions.groupby("complaint_id").agg(
        depth=("hop_number", "max"), n_txns=("txn_id", "size"))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    depth = per_chain["depth"].value_counts().sort_index()
    ax1.bar(depth.index, depth.values, width=0.7, color=BLUE)
    ax1.set_title("Mule-chain depth (hops after the victim)")
    ax1.set_xlabel("hops")
    ax1.set_ylabel("chains")
    n = per_chain["n_txns"].value_counts().sort_index()
    ax2.bar(n.index, n.values, width=0.7, color=BLUE)
    ax2.set_title("Transfers per chain (fan-out makes it > depth)")
    ax2.set_xlabel("transactions in chain")
    fig.tight_layout()
    fig.savefig(f"{DOCS}/plot_hop_histogram.png", dpi=130)
    plt.close(fig)


def plot_time_to_cashout(complaints, withdrawals):
    first_wd = withdrawals.groupby("complaint_id")["timestamp"].min()
    t0 = complaints.set_index("complaint_id").loc[first_wd.index, "timestamp"]
    hours = ((first_wd - t0).dt.total_seconds() / 3600).clip(upper=72)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.hist(hours, bins=np.arange(0, 74, 2), color=ORANGE, edgecolor=SURFACE, lw=0.8)
    ax.axvline(hours.median(), color=INK, lw=1)
    ax.annotate(f"median {hours.median():.1f} h", (hours.median(), ax.get_ylim()[1] * 0.92),
                xytext=(6, 0), textcoords="offset points", fontsize=9, color=INK)
    ax.set_title("Hours from fraud to first ATM withdrawal (the intervention window)")
    ax.set_xlabel("hours after the fraud")
    ax.set_ylabel("cash-out chains")
    fig.tight_layout()
    fig.savefig(f"{DOCS}/plot_time_to_cashout.png", dpi=130)
    plt.close(fig)


def main():
    conn = sqlite3.connect(C.DB_PATH)
    print_row_counts(conn)
    districts = load(conn, "districts")
    complaints = load(conn, "complaints", parse=["timestamp", "reported_at"])
    transactions = load(conn, "transactions", parse=["timestamp"])
    withdrawals = load(conn, "withdrawals", parse=["timestamp"])
    hist = load(conn, "hotspot_history")
    conn.close()

    physics_checks(districts, complaints, transactions, withdrawals, hist)

    plot_events_over_time(complaints, withdrawals)
    ranked = plot_geography(districts, withdrawals, hist)
    plot_hop_histogram(transactions)
    plot_time_to_cashout(complaints, withdrawals)

    ever_hot = set(hist["district_id"])
    print("\ntop 10 districts by withdrawals")
    for row in ranked.head(10).itertuples():
        tag = "initial hotspot" if row.is_hotspot else ("drifted-in hotspot" if row.Index in ever_hot else "")
        print(f"  {row.name:24s} {row.state:18s} {row.withdrawals:6d}  {tag}")
    print(f"\nplots saved to {DOCS}/")


if __name__ == "__main__":
    main()
