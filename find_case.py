"""
Find one real, representative case in the held-out test months for the deck.

"Real" here means real in the synthetic world: an actual complaint, its actual
mule chain, and its actual cash-out, all from months the model never trained
on - not a story written for the slide.

We want a case an I4C officer would recognise:
  - victim and cash-out in DIFFERENT states (the inter-state referral problem)
  - the cash-out district was on FraudLens's top-25 for the window in which the
    first withdrawal happened (so the alert was live before the money came out)
  - an ordinary amount and an ordinary fraud type, not a cherry-picked extreme
"""
import json
import os
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

WINDOW_H = 6


def main():
    df = common.load_table()
    _, _, test = common.split(df)
    del df
    meta = json.load(open(MC.FEATURES_PATH))
    booster = lgb.Booster(model_file=MC.MODEL_PATH)
    test = test.assign(score=booster.predict(test[meta["features"]]))
    test["rank"] = test.groupby("window_idx")["score"].rank(ascending=False, method="first")
    top25 = test[test["rank"] <= 25][["window_idx", "district_id", "rank"]]
    flagged = set(zip(top25["window_idx"], top25["district_id"]))
    rank_of = {(w, d): int(r) for w, d, r in top25.itertuples(index=False)}

    con = sqlite3.connect("data/fraudlens.db")
    dist = pd.read_sql("SELECT district_id, name, state FROM districts", con).set_index("district_id")
    cmp = pd.read_sql("SELECT * FROM complaints", con, parse_dates=["timestamp", "reported_at"])
    wd = pd.read_sql("SELECT complaint_id, district_id, amount, timestamp FROM withdrawals",
                     con, parse_dates=["timestamp"])
    hops = pd.read_sql("SELECT complaint_id, MAX(hop_number) AS hops FROM transactions GROUP BY 1", con)
    con.close()

    start = pd.Timestamp(DC.START_DATE)
    test_start = pd.Timestamp(MC.TEST_START)

    first = (wd.sort_values("timestamp").groupby("complaint_id")
               .agg(cash_district=("district_id", "first"),
                    first_wd=("timestamp", "first"),
                    n_wd=("amount", "size"),
                    cash_total=("amount", "sum"))
               .reset_index())
    c = cmp.merge(first, on="complaint_id").merge(hops, on="complaint_id")
    c = c[c["timestamp"] >= test_start]

    c["victim_state"] = c["victim_district"].map(dist["state"])
    c["cash_state"] = c["cash_district"].map(dist["state"])
    c = c[c["victim_state"] != c["cash_state"]]

    c["wd_window"] = ((c["first_wd"] - start).dt.total_seconds() // (WINDOW_H * 3600)).astype(int)
    c["flagged"] = [(w, d) in flagged for w, d in zip(c["wd_window"], c["cash_district"])]
    c = c[c["flagged"]]
    c["rank"] = [rank_of[(w, d)] for w, d in zip(c["wd_window"], c["cash_district"])]

    c["hours_to_cash"] = (c["first_wd"] - c["timestamp"]).dt.total_seconds() / 3600
    c["window_open"] = start + pd.to_timedelta(c["wd_window"] * WINDOW_H, unit="h")
    c["warning_min"] = (c["first_wd"] - c["window_open"]).dt.total_seconds() / 60

    # representative, not extreme: UPI or card, amount near the median for that
    # type, a chain of typical depth, a cash-out that took a typical number of
    # hours, and a warning window long enough to act on.
    pool = c[c["fraud_category"].isin(["UPI", "card"])
             & c["amount"].between(20000, 120000)
             & c["hops"].between(4, 6)
             & c["hours_to_cash"].between(6, 20)
             & (c["warning_min"] >= 60)]
    print(f"{len(c):,} inter-state chains in the test months cashed out in a district "
          f"FraudLens had already put on its top-25; {len(pool):,} are ordinary cases.\n")

    pick = pool.sort_values(["rank", "amount"]).iloc[len(pool) // 2]
    out = {
        "complaint_id": int(pick["complaint_id"]),
        "fraud_category": pick["fraud_category"],
        "amount": float(pick["amount"]),
        "victim_district": dist.loc[pick["victim_district"], "name"],
        "victim_state": pick["victim_state"],
        "reported_at": str(pick["reported_at"]),
        "fraud_at": str(pick["timestamp"]),
        "hops": int(pick["hops"]),
        "cash_district": dist.loc[pick["cash_district"], "name"],
        "cash_state": pick["cash_state"],
        "window_open": str(pick["window_open"]),
        "first_withdrawal": str(pick["first_wd"]),
        "n_withdrawals": int(pick["n_wd"]),
        "cash_total": float(pick["cash_total"]),
        "rank_in_window": int(pick["rank"]),
        "hours_fraud_to_cash": round(float(pick["hours_to_cash"]), 1),
        "warning_minutes": round(float(pick["warning_min"])),
        "population_count_same_pattern": int(len(c)),
    }
    json.dump(out, open("docs/deck_case.json", "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
