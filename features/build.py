"""
Phase 2 - feature pipeline.

Run:  python -m features.build

One row per (district, 6-hour window) -> data/train_table.parquet

ANTI-LEAKAGE RULE (the most important thing in this file):
  Every feature for window W uses only events VISIBLE strictly before W's
  start time T.
    - a complaint is visible from `reported_at` (not from the incident time)
    - a transaction or withdrawal is visible from
      max(its own timestamp, its complaint's reported_at)
      (nobody traces a mule chain before the victim has reported)
  Labels (y, y_count) use the TRUE withdrawal timestamps inside [T, T+6h).

HOW IT STAYS FAST:
  Time is "hours since day 0". Events are bucketed into a matrix of shape
  [n_windows, n_districts]; rolling counts are cumulative-sum differences, so
  "only windows before W" is true by construction. Live-chain features come
  from a table of money "holdings" (one row per transfer received: which
  account, which district, from when until when the money sat there), built
  ONCE with pandas groupbys and expanded to the windows it overlaps.
"""
import sqlite3
import time

import numpy as np
import pandas as pd

from datagen import config as DC
from datagen.geo import haversine_km
from features import config as FC

START = pd.Timestamp(DC.START_DATE)
WH = FC.WINDOW_HOURS
N_WINDOWS = DC.N_DAYS * 24 // WH
TS_FMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Loading + visibility times
# ---------------------------------------------------------------------------
def hours_since_start(text_series):
    ts = pd.to_datetime(text_series, format=TS_FMT)
    return ((ts - START).dt.total_seconds() / 3600.0).to_numpy()


def load_events(db_path=DC.DB_PATH):
    """Read the DB and attach t (hours since day 0) and t_visible to every event."""
    conn = sqlite3.connect(db_path)
    ev = {
        "districts": pd.read_sql("SELECT * FROM districts ORDER BY district_id", conn),
        "neighbors": pd.read_sql("SELECT district_id, neighbor_id FROM district_neighbors", conn),
        "atm_counts": pd.read_sql("SELECT district_id, COUNT(*) AS n_atms FROM atms GROUP BY district_id", conn),
        "accounts": pd.read_sql("SELECT account_id, district_id FROM accounts", conn),
        "complaints": pd.read_sql("SELECT complaint_id, timestamp, reported_at, victim_district, "
                                  "fraud_category, amount FROM complaints", conn),
        "transactions": pd.read_sql("SELECT complaint_id, from_account, to_account, amount, "
                                    "timestamp, hop_number FROM transactions", conn),
        "withdrawals": pd.read_sql("SELECT complaint_id, district_id, amount, timestamp FROM withdrawals", conn),
        "holidays": pd.read_sql("SELECT day_index FROM holidays", conn),
    }
    conn.close()

    cm, tx, wd = ev["complaints"], ev["transactions"], ev["withdrawals"]
    cm["t_incident"] = hours_since_start(cm["timestamp"])
    cm["t_reported"] = hours_since_start(cm["reported_at"])
    reported = cm.set_index("complaint_id")["t_reported"]
    incident = cm.set_index("complaint_id")["t_incident"]

    tx["t"] = hours_since_start(tx["timestamp"])
    tx["t_visible"] = np.maximum(tx["t"], tx["complaint_id"].map(reported))
    tx["t_incident"] = tx["complaint_id"].map(incident)
    account_district = ev["accounts"].set_index("account_id")["district_id"]
    tx["district_id"] = tx["to_account"].map(account_district)

    wd["t"] = hours_since_start(wd["timestamp"])
    wd["t_visible"] = np.maximum(wd["t"], wd["complaint_id"].map(reported))
    return ev


# ---------------------------------------------------------------------------
# Matrix helpers: everything is [n_windows, n_columns]
# ---------------------------------------------------------------------------
def window_of(t):
    """Window index that CONTAINS time t (hours)."""
    return np.floor(np.asarray(t) / WH).astype(int)


def bucket(t, col, n_cols, weights=None):
    """Sum events into a [N_WINDOWS, n_cols] matrix by the window containing t."""
    w = window_of(t)
    col = np.asarray(col)
    ok = (w >= 0) & (w < N_WINDOWS)
    flat = w[ok] * n_cols + col[ok]
    wts = None if weights is None else np.asarray(weights)[ok]
    return np.bincount(flat, weights=wts, minlength=N_WINDOWS * n_cols).reshape(N_WINDOWS, n_cols)


def rolling_past(m, k_windows):
    """out[w] = sum of m over windows w-k .. w-1 (never includes window w itself)."""
    cs = np.vstack([np.zeros((1, m.shape[1])), np.cumsum(m, axis=0)])  # cs[w] = sum m[:w]
    idx = np.arange(N_WINDOWS)
    return cs[idx] - cs[np.maximum(idx - k_windows, 0)]


def decayed_past(t, col, n_cols, tau):
    """out[w] = sum over past events of exp(-(T_w - t)/tau).

    Exact in continuous time: each event's weight is first expressed at the
    end of its own window, then the whole bucket is aged window by window.
    """
    w = window_of(t)
    end_of_window = (w + 1) * WH
    per_bucket = bucket(t, col, n_cols, weights=np.exp(-(end_of_window - t) / tau))
    a = np.exp(-WH / tau)
    out = np.zeros_like(per_bucket)
    for i in range(1, N_WINDOWS):
        out[i] = out[i - 1] * a + per_bucket[i - 1]
    return out


def hours_since_last(t, col, n_cols):
    """out[w] = T_w - (latest event time before T_w), capped when none."""
    w = window_of(t)
    col = np.asarray(col)
    ok = (w >= 0) & (w < N_WINDOWS)
    latest_in_bucket = np.full((N_WINDOWS, n_cols), -np.inf)
    np.maximum.at(latest_in_bucket, (w[ok], col[ok]), np.asarray(t)[ok])
    latest_before = np.vstack([np.full((1, n_cols), -np.inf),
                               np.maximum.accumulate(latest_in_bucket, axis=0)[:-1]])
    T = (np.arange(N_WINDOWS) * WH)[:, None]
    return np.minimum(T - latest_before, FC.HOURS_SINCE_CAP)


def sum_over_neighbors(m, nb_idx):
    """m is [W, D]; nb_idx is [D, k] -> [W, D] sum of each district's neighbours."""
    return m[:, nb_idx].sum(axis=2)


# ---------------------------------------------------------------------------
# Live-chain features (our differentiator)
# ---------------------------------------------------------------------------
def build_holdings(ev):
    """One row per transfer received: the money sits in `account_id` (in
    `district_id`) from t_in until t_out, where t_out is the earliest of
      - that account forwarding the money on (its first outgoing transfer),
      - the chain's first ATM withdrawal (it is cashing out, no longer 'in flight'),
      - the chain going stale at ACTIVE_CHAIN_MAX_AGE_HOURS after the incident.
    All times are visibility times, so the LEA could actually have known them.
    """
    tx = ev["transactions"]
    forwarded = (tx.groupby(["complaint_id", "from_account"])["t_visible"].min()
                   .rename("t_forwarded").reset_index()
                   .rename(columns={"from_account": "account_id"}))
    first_cashout = ev["withdrawals"].groupby("complaint_id")["t_visible"].min().rename("t_cashout")

    h = tx[["complaint_id", "to_account", "district_id", "amount", "hop_number",
            "t_visible", "t_incident"]].rename(columns={"to_account": "account_id", "t_visible": "t_in"})
    h = h.merge(forwarded, on=["complaint_id", "account_id"], how="left")
    h = h.merge(first_cashout, on="complaint_id", how="left")
    t_stale = h["t_incident"] + FC.ACTIVE_CHAIN_MAX_AGE_HOURS
    h["t_out"] = np.fmin(np.fmin(h["t_forwarded"].fillna(np.inf), h["t_cashout"].fillna(np.inf)), t_stale)
    return h.drop(columns=["t_forwarded", "t_cashout"])


def expand_to_windows(h):
    """Repeat each holding once per window whose START lies in (t_in, t_out]."""
    w_first = window_of(h["t_in"].to_numpy()) + 1        # first start strictly after t_in
    w_last = np.minimum(window_of(h["t_out"].to_numpy()), N_WINDOWS - 1)  # last start <= t_out
    n = np.maximum(w_last - w_first + 1, 0)
    keep = n > 0
    n, w_first = n[keep], w_first[keep]
    src = np.repeat(np.flatnonzero(keep), n)
    offset = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    rows = h.iloc[src].reset_index(drop=True)
    rows["window_idx"] = w_first[np.repeat(np.arange(len(n)), n)] + offset
    return rows


def live_chain_features(rows, n_districts):
    """Aggregate expanded holdings to flat arrays indexed by window*D + district."""
    size = N_WINDOWS * n_districts
    key = rows["window_idx"].to_numpy() * n_districts + rows["district_id"].to_numpy()
    rows = rows.assign(key=key)

    def to_flat(series, fill=0.0):
        out = np.full(size, float(fill))   # float, or an int fill would truncate values
        out[series.index.to_numpy()] = series.to_numpy()
        return out

    money = rows.groupby("key")["amount"].sum()

    # one row per (chain, account, window): dedupe keeps the deepest hop
    acc = (rows.sort_values("hop_number", ascending=False)
               .drop_duplicates(["complaint_id", "account_id", "window_idx"]))
    n_accounts = acc.groupby("key").size()
    avg_hop = acc.groupby("key")["hop_number"].mean()

    # one row per (chain, district, window)
    ch = rows.drop_duplicates(["complaint_id", "district_id", "window_idx"])
    age = ch["window_idx"] * WH - ch["t_incident"]
    ch = ch.assign(age=age)
    n_chains = ch.groupby("key").size()
    avg_age = ch.groupby("key")["age"].mean()
    min_age = ch.groupby("key")["age"].min()

    return {
        "n_active_chains_here": to_flat(n_chains),
        "n_active_accounts_here": to_flat(n_accounts),
        "money_in_flight_here": to_flat(money),
        "avg_chain_age_hours": to_flat(avg_age),
        "min_chain_age_hours": to_flat(min_age, fill=FC.ACTIVE_CHAIN_MAX_AGE_HOURS),
        "avg_active_hop_here": to_flat(avg_hop),
    }


# ---------------------------------------------------------------------------
# Static, calendar, hotspot-distance
# ---------------------------------------------------------------------------
def neighbor_index(ev, n_districts):
    nb = ev["neighbors"].sort_values(["district_id", "neighbor_id"])
    return nb["neighbor_id"].to_numpy().reshape(n_districts, -1)


def active_hotspot_features(wd_30d, dist_km):
    """From the PAST 30 days only: which districts are currently hot, and how
    far is each district from the nearest hot one."""
    n_d = wd_30d.shape[1]
    is_active = np.zeros((N_WINDOWS, n_d))
    dist_to_active = np.full((N_WINDOWS, n_d), FC.DIST_CAP_KM)
    for w in range(N_WINDOWS):
        order = np.argsort(-wd_30d[w], kind="stable")[:FC.N_ACTIVE_HOTSPOTS]
        hot = order[wd_30d[w][order] > 0]
        if len(hot):
            is_active[w, hot] = 1
            dist_to_active[w] = dist_km[:, hot].min(axis=1)
    return is_active, dist_to_active


def calendar_features(holiday_days):
    w = np.arange(N_WINDOWS)
    day = w * WH // 24
    dow = (day + START.weekday()) % 7
    return {
        "hour_block": (w % (24 // WH)).astype(float),
        "day_of_week": dow.astype(float),
        "is_weekend": (dow >= 5).astype(float),
        "is_holiday": np.isin(day, list(holiday_days)).astype(float),
    }


# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------
def build_table(ev):
    """Return the long-format table: rows ordered by (window_idx, district_id)."""
    d = ev["districts"]
    n_d = len(d)
    cm, tx, wd = ev["complaints"], ev["transactions"], ev["withdrawals"]
    nb_idx = neighbor_index(ev, n_d)
    lat, lon = d["lat"].to_numpy(), d["lon"].to_numpy()
    dist_km = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    per_day = 24 // WH

    feats = {}  # name -> [N_WINDOWS, n_d] matrix (or [N_WINDOWS] vector)

    # --- rolling withdrawal counts (visible times) ---
    wd_counts = bucket(wd["t_visible"], wd["district_id"], n_d)
    for L in FC.LOOKBACK_DAYS:
        feats[f"wd_{L}d"] = rolling_past(wd_counts, L * per_day)
    feats["wd_decay"] = decayed_past(wd["t_visible"], wd["district_id"], n_d, FC.DECAY_TAU_HOURS)
    feats["wd_nb_1d"] = sum_over_neighbors(feats["wd_1d"], nb_idx)
    feats["wd_nb_7d"] = sum_over_neighbors(feats["wd_7d"], nb_idx)

    # --- self-excitation: time since last withdrawal here / nearby ---
    hs = hours_since_last(wd["t_visible"], wd["district_id"], n_d)
    feats["hrs_since_wd_here"] = hs
    feats["hrs_since_wd_nb"] = hs[:, nb_idx].min(axis=2)

    # --- active hotspots inferred from the past 30 days ---
    is_active, dist_active = active_hotspot_features(feats["wd_30d"], dist_km)
    feats["is_active_hotspot_30d"] = is_active
    feats["dist_to_active_hotspot_km"] = dist_active

    # --- complaints: nationwide by category (visible = reported) ---
    cats = list(DC.FRAUD_CATEGORIES.keys())
    cat_idx = cm["fraud_category"].map({c: i for i, c in enumerate(cats)}).to_numpy()
    cm_nat = bucket(cm["t_reported"], cat_idx, len(cats))
    for L in (1, 3, 7):
        r = rolling_past(cm_nat, L * per_day)
        for i, c in enumerate(cats):
            feats[f"cmp_nat_{c}_{L}d"] = r[:, i]          # same for every district
    # --- complaints: local (victim district) and neighbours ---
    cm_local = bucket(cm["t_reported"], cm["victim_district"], n_d)
    feats["cmp_local_1d"] = rolling_past(cm_local, 1 * per_day)
    feats["cmp_local_7d"] = rolling_past(cm_local, 7 * per_day)
    feats["cmp_nb_7d"] = sum_over_neighbors(feats["cmp_local_7d"], nb_idx)

    # --- labels: TRUE withdrawal times inside the window ---
    y_count = bucket(wd["t"], wd["district_id"], n_d)

    # --- flatten everything to (window, district) long format ---
    w_grid, d_grid = np.meshgrid(np.arange(N_WINDOWS), np.arange(n_d), indexing="ij")
    table = {
        "district_id": d_grid.ravel(),
        "window_idx": w_grid.ravel(),
    }
    table["window_start"] = START + pd.to_timedelta(table["window_idx"] * WH, unit="h")
    table["y_count"] = y_count.ravel().astype(np.int16)
    table["y"] = (table["y_count"] > 0).astype(np.int8)

    # static
    atm = ev["atm_counts"].set_index("district_id")["n_atms"].reindex(range(n_d)).fillna(0).to_numpy()
    for name, vec in (("is_hotspot", d["is_hotspot"].to_numpy()),
                      ("n_atms", atm),
                      ("population_weight", d["population_weight"].to_numpy())):
        table[name] = np.tile(vec, N_WINDOWS).astype(np.float32)
    # calendar
    for name, vec in calendar_features(set(ev["holidays"]["day_index"])).items():
        table[name] = np.repeat(vec, n_d).astype(np.float32)
    # matrices
    for name, m in feats.items():
        m = np.asarray(m)
        flat = np.repeat(m, n_d) if m.ndim == 1 else m.ravel()
        table[name] = flat.astype(np.float32)
    # live chains
    holdings = build_holdings(ev)
    rows = expand_to_windows(holdings)
    for name, flat in live_chain_features(rows, n_d).items():
        table[name] = flat.astype(np.float32)

    return pd.DataFrame(table), len(holdings), len(rows)


def feature_columns(df):
    return [c for c in df.columns if c not in ("district_id", "window_idx", "window_start", "y", "y_count")]


def write_summary(df, build_seconds, n_holdings, n_expanded):
    cols = feature_columns(df)
    pos = df["y"] == 1
    lines = [
        "# Feature summary (auto-generated by `python -m features.build`)", "",
        f"- rows: **{len(df):,}** ({df['district_id'].nunique()} districts x {df['window_idx'].nunique()} windows of {WH}h)",
        f"- columns: **{len(df.columns)}** ({len(cols)} features + 2 labels + 3 keys)",
        f"- positive rate (y=1): **{pos.mean():.2%}**; mean withdrawals per positive window: {df.loc[pos, 'y_count'].mean():.2f}",
        f"- holdings: {n_holdings:,} transfers -> {n_expanded:,} (holding, window) rows",
        f"- build time: **{build_seconds:.1f} s**", "",
        "| feature | mean | std | min | max | mean when y=1 | mean when y=0 | lift |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in cols:
        s = df[c].astype(float)
        m1, m0 = s[pos].mean(), s[~pos].mean()
        lift = m1 / m0 if m0 not in (0, np.nan) and not np.isnan(m0) and m0 != 0 else float("nan")
        lines.append(f"| {c} | {s.mean():.3g} | {s.std():.3g} | {s.min():.3g} | {s.max():.3g} "
                     f"| {m1:.3g} | {m0:.3g} | {lift:.2f} |")
    text = "\n".join(lines) + "\n"
    with open(FC.SUMMARY_PATH, "w") as f:
        f.write(text)
    return text


def main():
    t0 = time.time()
    print("loading events ...")
    ev = load_events()
    print(f"  {len(ev['complaints']):,} complaints, {len(ev['transactions']):,} transactions, "
          f"{len(ev['withdrawals']):,} withdrawals  ({time.time() - t0:.1f}s)")

    print("building features ...")
    df, n_holdings, n_expanded = build_table(ev)
    build_seconds = time.time() - t0
    df.to_parquet(FC.TRAIN_TABLE_PATH, index=False)
    print(f"  wrote {FC.TRAIN_TABLE_PATH}")

    text = write_summary(df, build_seconds, n_holdings, n_expanded)
    print()
    print(text)
    print(f"summary written to {FC.SUMMARY_PATH}")


if __name__ == "__main__":
    main()
