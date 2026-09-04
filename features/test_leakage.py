"""
Automated leakage test for the Phase 2 feature table.

Run:  python -m features.test_leakage

Idea: re-compute EVERY feature for a sample of (district, window) rows with a
deliberately slow, obvious implementation that filters the raw events with
`t_visible < window_start` and nothing else. If the fast pipeline had used any
event at or after the window start, the two would disagree.

Two checks:
  1. fast table == brute force (strict cut-off at window start)
  2. the brute force run with the cut-off moved 6h into the future DOES
     disagree - proving the test would catch a leak if there were one.
"""
import numpy as np
import pandas as pd

from datagen import config as DC
from datagen.geo import haversine_km
from features import config as FC
from features import build as B

N_RANDOM, N_HOTSPOT, N_WITH_CHAINS = 30, 15, 15
TOL = dict(rtol=1e-4, atol=1e-3)


class Sources:
    """Raw events with visibility times, plus static lookups."""

    def __init__(self):
        ev = B.load_events()
        self.cm = ev["complaints"]
        self.tx = ev["transactions"]
        self.wd = ev["withdrawals"]
        self.d = ev["districts"]
        self.n_d = len(self.d)
        self.nb = ev["neighbors"].groupby("district_id")["neighbor_id"].apply(list).to_dict()
        self.atms = ev["atm_counts"].set_index("district_id")["n_atms"].to_dict()
        self.holidays = set(ev["holidays"]["day_index"])
        lat, lon = self.d["lat"].to_numpy(), self.d["lon"].to_numpy()
        self.dist = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
        self.cats = list(DC.FRAUD_CATEGORIES.keys())


def slow_features(src, district, window_idx, cutoff=None):
    """Every feature for one (district, window), computed the obvious way.

    `cutoff` defaults to the window start T; only events visible strictly
    before the cutoff are allowed to contribute.
    """
    WH = FC.WINDOW_HOURS
    T = window_idx * WH
    cutoff = T if cutoff is None else cutoff
    f = {}

    # --- only events the LEA could have known about ---
    wd = src.wd[src.wd["t_visible"] < cutoff]
    cm = src.cm[src.cm["t_reported"] < cutoff]
    tx = src.tx[src.tx["t_visible"] < cutoff]
    nb = src.nb[district]

    # static + calendar
    row = src.d.iloc[district]
    f["is_hotspot"] = row["is_hotspot"]
    f["n_atms"] = src.atms.get(district, 0)
    f["population_weight"] = row["population_weight"]
    day = T // 24
    dow = (day + B.START.weekday()) % 7
    f["hour_block"] = window_idx % (24 // WH)
    f["day_of_week"] = dow
    f["is_weekend"] = float(dow >= 5)
    f["is_holiday"] = float(day in src.holidays)

    # rolling withdrawals here and in neighbours
    here = wd[wd["district_id"] == district]
    near = wd[wd["district_id"].isin(nb)]
    for L in FC.LOOKBACK_DAYS:
        f[f"wd_{L}d"] = (here["t_visible"] >= T - 24 * L).sum()
    f["wd_decay"] = np.exp(-(T - here["t_visible"]) / FC.DECAY_TAU_HOURS).sum()
    f["wd_nb_1d"] = (near["t_visible"] >= T - 24).sum()
    f["wd_nb_7d"] = (near["t_visible"] >= T - 24 * 7).sum()

    # self-excitation
    f["hrs_since_wd_here"] = min(T - here["t_visible"].max(), FC.HOURS_SINCE_CAP) if len(here) else FC.HOURS_SINCE_CAP
    f["hrs_since_wd_nb"] = min(T - near["t_visible"].max(), FC.HOURS_SINCE_CAP) if len(near) else FC.HOURS_SINCE_CAP

    # active hotspots = top-25 districts by withdrawals in the last 30 days
    recent = wd[wd["t_visible"] >= T - 24 * 30]
    counts = recent.groupby("district_id").size().reindex(range(src.n_d), fill_value=0)
    ranked = sorted(range(src.n_d), key=lambda i: (-counts[i], i))[:FC.N_ACTIVE_HOTSPOTS]
    hot = [i for i in ranked if counts[i] > 0]
    f["is_active_hotspot_30d"] = float(district in hot)
    f["dist_to_active_hotspot_km"] = min(src.dist[district, i] for i in hot) if hot else FC.DIST_CAP_KM

    # complaints nationwide by category, and local
    for L in (1, 3, 7):
        recent_cm = cm[cm["t_reported"] >= T - 24 * L]
        for c in src.cats:
            f[f"cmp_nat_{c}_{L}d"] = (recent_cm["fraud_category"] == c).sum()
    local = cm[cm["victim_district"] == district]
    f["cmp_local_1d"] = (local["t_reported"] >= T - 24).sum()
    f["cmp_local_7d"] = (local["t_reported"] >= T - 24 * 7).sum()
    f["cmp_nb_7d"] = ((cm["victim_district"].isin(nb)) & (cm["t_reported"] >= T - 24 * 7)).sum()

    # live chains: money that is sitting in this district's accounts right now
    cashed_out = set(wd["complaint_id"])                      # chain already cashing out
    alive = cm[cm["t_incident"] + FC.ACTIVE_CHAIN_MAX_AGE_HOURS >= T]
    alive = alive[~alive["complaint_id"].isin(cashed_out)]
    t_alive = tx[tx["complaint_id"].isin(alive["complaint_id"])]
    forwarded = set(zip(t_alive["complaint_id"], t_alive["from_account"]))   # accounts that already passed it on
    received = t_alive[t_alive["district_id"] == district]
    keep = np.fromiter(((c, a) not in forwarded
                        for c, a in zip(received["complaint_id"], received["to_account"])),
                       dtype=bool, count=len(received))
    still_holding = received.loc[keep]
    f["money_in_flight_here"] = still_holding["amount"].sum()
    per_account = still_holding.groupby(["complaint_id", "to_account"])["hop_number"].max()
    f["n_active_accounts_here"] = len(per_account)
    f["avg_active_hop_here"] = per_account.mean() if len(per_account) else 0.0
    chains = still_holding.drop_duplicates("complaint_id")
    ages = T - chains["t_incident"]
    f["n_active_chains_here"] = len(chains)
    f["avg_chain_age_hours"] = ages.mean() if len(chains) else 0.0
    f["min_chain_age_hours"] = ages.min() if len(chains) else FC.ACTIVE_CHAIN_MAX_AGE_HOURS
    return f


def pick_sample(df, src, seed=0):
    """Random rows + hotspot rows + rows with live chains, so non-zero
    features are exercised, not just zeros."""
    rng = np.random.default_rng(seed)
    later = df[df["window_idx"] >= 4 * 35]                    # after the 30-day warm-up
    random_rows = later.sample(N_RANDOM, random_state=int(rng.integers(1e9)))
    hot_ids = src.d.loc[src.d["is_hotspot"] == 1, "district_id"]
    hotspot_rows = later[later["district_id"].isin(hot_ids)].sample(N_HOTSPOT, random_state=int(rng.integers(1e9)))
    chain_rows = later[later["n_active_chains_here"] > 0].sample(N_WITH_CHAINS, random_state=int(rng.integers(1e9)))
    return pd.concat([random_rows, hotspot_rows, chain_rows])


def compare(df_row, slow, cols):
    """Return the list of features whose fast and slow values disagree."""
    bad = []
    for c in cols:
        fast, brute = float(df_row[c]), float(slow[c])
        if not np.isclose(fast, brute, **TOL):
            bad.append((c, fast, brute))
    return bad


def test_features_match_bruteforce(df=None, src=None):
    df = pd.read_parquet(FC.TRAIN_TABLE_PATH) if df is None else df
    src = Sources() if src is None else src
    cols = B.feature_columns(df)
    sample = pick_sample(df, src)
    failures = []
    for _, r in sample.iterrows():
        slow = slow_features(src, int(r["district_id"]), int(r["window_idx"]))
        missing = set(cols) - set(slow)
        assert not missing, f"brute force does not cover: {missing}"
        bad = compare(r, slow, cols)
        if bad:
            failures.append((int(r["district_id"]), int(r["window_idx"]), bad))
    for d, w, bad in failures:
        print(f"  MISMATCH district={d} window={w}: {bad[:5]}")
    assert not failures, f"{len(failures)} of {len(sample)} sampled rows disagree with brute force"
    print(f"  check 1 PASS: {len(sample)} rows x {len(cols)} features match the strict brute force")
    return sample


def test_bruteforce_detects_leak(df=None, src=None, sample=None):
    """Move the cut-off 6h into the future (into the label window). Features
    MUST change for some rows, otherwise this test could never catch a leak."""
    df = pd.read_parquet(FC.TRAIN_TABLE_PATH) if df is None else df
    src = Sources() if src is None else src
    sample = pick_sample(df, src) if sample is None else sample
    cols = B.feature_columns(df)
    changed_rows, changed_feats = 0, set()
    for _, r in sample.iterrows():
        T = int(r["window_idx"]) * FC.WINDOW_HOURS
        leaky = slow_features(src, int(r["district_id"]), int(r["window_idx"]), cutoff=T + FC.WINDOW_HOURS)
        bad = compare(r, leaky, cols)
        if bad:
            changed_rows += 1
            changed_feats.update(c for c, _, _ in bad)
    assert changed_rows > 0, "leaky recomputation changed nothing - test has no teeth"
    print(f"  check 2 PASS: peeking 6h ahead changes {changed_rows}/{len(sample)} rows "
          f"({len(changed_feats)} distinct features) - the test would catch a leak")


def main():
    print("loading table + sources ...")
    df = pd.read_parquet(FC.TRAIN_TABLE_PATH)
    src = Sources()
    print("check 1: fast features == brute force with strict cut-off at window start")
    sample = test_features_match_bruteforce(df, src)
    print("check 2: brute force with cut-off moved into the window must differ")
    test_bruteforce_detects_leak(df, src, sample)
    print("\nLEAKAGE TEST PASSED")


if __name__ == "__main__":
    main()
