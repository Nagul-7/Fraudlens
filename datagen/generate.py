"""
Phase 1 - synthetic fraud world generator.

Run:  python -m datagen.generate

Builds data/fraudlens.db with these tables:
    districts, district_neighbors, atms, accounts, holidays,
    hotspot_history, complaints, transactions, withdrawals

Everything is driven by datagen/config.py and ONE random seed, so the same
config always produces byte-for-byte the same world.

Time inside the simulation is kept as "minutes since START_DATE" (a float)
and converted to real timestamps only when writing the database.
"""
import os
import sqlite3
import time

import numpy as np
import pandas as pd

from datagen import config as C
from datagen import geo
from datagen import population

MIN_PER_DAY = 24 * 60

# Normalised hour-of-day probabilities (sum to 1) built once from config.
COMPLAINT_HOUR_P = np.array(C.COMPLAINT_HOUR_WEIGHTS) / sum(C.COMPLAINT_HOUR_WEIGHTS)
WITHDRAWAL_HOUR_P = np.array(C.WITHDRAWAL_HOUR_WEIGHTS) / sum(C.WITHDRAWAL_HOUR_WEIGHTS)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def to_timestamp(minutes):
    """Minutes since START_DATE -> pandas Timestamps (works on arrays)."""
    start = pd.Timestamp(C.START_DATE)
    return start + pd.to_timedelta(np.asarray(minutes, dtype=float), unit="m")


def weighted_pick(rng, keys, weights):
    """Pick one key from a dict-style (keys, weights) pair."""
    p = np.array(weights, dtype=float)
    return keys[rng.choice(len(keys), p=p / p.sum())]


def weekday_of(day):
    """0 = Monday ... 6 = Sunday for a simulated day index."""
    return (pd.Timestamp(C.START_DATE) + pd.Timedelta(days=int(day))).weekday()


# ---------------------------------------------------------------------------
# Static world: districts, ATMs, accounts, holidays
# ---------------------------------------------------------------------------
def build_districts(rng):
    """districts table + neighbours from the real GeoJSON, with real population."""
    districts = geo.clean_geojson()
    districts, _ = population.attach_population(districts)

    # Flag the initial hotspots.
    districts["is_hotspot"] = 0
    for state, name in C.INITIAL_HOTSPOTS:
        mask = (districts["state"] == state) & (districts["name"] == name)
        if not mask.any():
            raise ValueError(f"hotspot {state}/{name} not found in GeoJSON")
        districts.loc[mask, "is_hotspot"] = 1

    neighbors = geo.nearest_neighbors(districts)
    cols = ["district_id", "name", "state", "census_code", "lat", "lon",
            "is_hotspot", "population", "population_weight", "population_source"]
    return districts[cols], neighbors


def build_atms(rng, districts):
    """ATMs scattered around each district centroid, count ~ population."""
    rows = []
    banks = list(C.BANKS.keys())
    shares = list(C.BANKS.values())
    for d in districts.itertuples():
        n = max(C.ATMS_MIN, rng.poisson(C.ATMS_PER_DISTRICT * d.population_weight))
        for _ in range(n):
            rows.append({
                "district_id": d.district_id,
                "lat": round(d.lat + rng.uniform(-C.ATM_JITTER_DEG, C.ATM_JITTER_DEG), 5),
                "lon": round(d.lon + rng.uniform(-C.ATM_JITTER_DEG, C.ATM_JITTER_DEG), 5),
                "bank": weighted_pick(rng, banks, shares),
            })
    atms = pd.DataFrame(rows)
    atms.insert(0, "atm_id", np.arange(len(atms)))
    return atms


def build_accounts(rng, districts):
    """victim / clean / mule accounts. Mules concentrate in hotspots.

    Each account also gets a bank. Real CFCFRMS feeds carry the holding bank,
    and Phase 6's bank-facing view needs it to show an FI only its own
    accounts. It is drawn from a SEPARATE RNG stream (SEED + 1) so adding it
    does not disturb the main sequence - the rest of the world, and therefore
    every Phase 3 metric, stays bit-identical.
    """
    n_d = len(districts)
    pop_p = districts["population_weight"].to_numpy() / districts["population_weight"].sum()
    hotspot_ids = districts.loc[districts["is_hotspot"] == 1, "district_id"].to_numpy()

    def opened_dates(n, max_age_days):
        age = rng.integers(1, max_age_days, size=n)
        return (pd.Timestamp(C.START_DATE) - pd.to_timedelta(age, unit="D")).strftime("%Y-%m-%d")

    frames = []
    # victims + clean: spread by population, real KYC, older accounts
    for holder, n in (("victim", C.N_VICTIM_ACCOUNTS), ("clean", C.N_CLEAN_ACCOUNTS)):
        frames.append(pd.DataFrame({
            "holder_type": holder,
            "district_id": rng.choice(n_d, size=n, p=pop_p),
            "opened_date": opened_dates(n, C.OTHER_ACCOUNT_AGE_DAYS),
            "kyc_quality": "real",
        }))
    # mules: a floor everywhere + a big pool in every hotspot + population extras
    mule_districts = np.concatenate([
        np.repeat(np.arange(n_d), C.MULES_PER_DISTRICT_MIN),
        np.repeat(hotspot_ids, C.MULES_PER_HOTSPOT_EXTRA),
        rng.choice(n_d, size=C.MULES_EXTRA_BY_POPULATION, p=pop_p),
    ])
    n_m = len(mule_districts)
    frames.append(pd.DataFrame({
        "holder_type": "mule",
        "district_id": mule_districts,
        "opened_date": opened_dates(n_m, C.MULE_ACCOUNT_AGE_DAYS),
        "kyc_quality": rng.choice(list(C.MULE_KYC_PROBS.keys()), size=n_m,
                                  p=list(C.MULE_KYC_PROBS.values())),
    }))
    accounts = pd.concat(frames, ignore_index=True)
    accounts.insert(0, "account_id", np.arange(len(accounts)))
    bank_rng = np.random.default_rng(C.SEED + 1)      # independent stream
    accounts["bank"] = bank_rng.choice(list(C.BANKS.keys()), size=len(accounts),
                                       p=np.array(list(C.BANKS.values())) / sum(C.BANKS.values()))
    return accounts


def build_holidays(rng):
    """A few random bank-holiday-style days. Returns (set of day indexes, DataFrame)."""
    days = sorted(rng.choice(C.N_DAYS, size=C.N_RANDOM_HOLIDAYS, replace=False))
    dates = (pd.Timestamp(C.START_DATE) + pd.to_timedelta(days, unit="D")).strftime("%Y-%m-%d")
    df = pd.DataFrame({"day_index": days, "date": dates, "reason": "bank_holiday"})
    return set(int(d) for d in days), df


def is_quiet_day(day, holidays):
    """Sunday or bank holiday: ATM cash-outs are less likely."""
    return weekday_of(day) == 6 or day in holidays


# ---------------------------------------------------------------------------
# Hotspot drift (physics rule 4)
# ---------------------------------------------------------------------------
def build_hotspot_timeline(rng, districts, neighbor_lists):
    """Which districts are ACTIVE hotspots on each day.

    Every DRIFT_EVERY_DAYS, each hotspot may get 'burned' and replaced by a
    neighbour of an existing hotspot (corridor spreading) or a random district.
    Returns (list_of_active_arrays_per_day, hotspot_history DataFrame).
    """
    # brand-new corridors appear where there are people and bank branches, so
    # random replacements are weighted by population ^ HOTSPOT_POP_EXPONENT.
    # With real census population this is what stops a remote district from
    # being drawn as a mule corridor.
    pop_p = districts["population_weight"].to_numpy() ** C.HOTSPOT_POP_EXPONENT
    pop_p = pop_p / pop_p.sum()
    active = set(int(d) for d in districts.loc[districts["is_hotspot"] == 1, "district_id"])
    history = {d: [0, None] for d in active}  # district -> [start_day, end_day]
    per_day = []

    for day in range(C.N_DAYS):
        if day > 0 and day % C.DRIFT_EVERY_DAYS == 0:
            for d in sorted(active):
                if rng.random() >= C.HOTSPOT_RETIRE_PROB:
                    continue
                active.remove(d)
                history[d][1] = day
                # pick a replacement that is not already active
                new = None
                if rng.random() < C.NEW_HOTSPOT_NEAR_PROB and active:
                    anchor = int(rng.choice(sorted(active)))
                    options = [n for n in neighbor_lists[anchor] if n not in active]
                    if options:
                        new = int(rng.choice(options))
                while new is None or new in active:
                    new = int(rng.choice(len(districts), p=pop_p))
                active.add(new)
                history[new] = [day, None]
        per_day.append(np.array(sorted(active)))

    rows = [{"district_id": d, "start_day": s, "end_day": e} for d, (s, e) in history.items()]
    hist = pd.DataFrame(rows).sort_values(["start_day", "district_id"]).reset_index(drop=True)
    hist["start_date"] = (pd.Timestamp(C.START_DATE) + pd.to_timedelta(hist["start_day"], unit="D")).dt.strftime("%Y-%m-%d")
    hist["end_date"] = [None if pd.isna(e) else
                        (pd.Timestamp(C.START_DATE) + pd.Timedelta(days=int(e))).strftime("%Y-%m-%d")
                        for e in hist["end_day"]]
    return per_day, hist


# ---------------------------------------------------------------------------
# The event simulation (physics rules 1, 2, 3, 5, 6)
# ---------------------------------------------------------------------------
def pick_cashout_district(rng, world, day):
    """Where will this chain cash out? Hotspots most of the time, otherwise
    anywhere by population - both tilted by today's self-excitation boost."""
    boost = 1.0 + np.minimum(world["boost"][day], C.EXCITE_CAP)
    if rng.random() < C.HOTSPOT_SHARE:
        ids = world["hotspots_by_day"][day]
        p = boost[ids]
        return int(ids[rng.choice(len(ids), p=p / p.sum())])
    p = world["pop_weight"] * boost
    return int(rng.choice(len(p), p=p / p.sum()))


def excite(world, district, day, rng):
    """A cash-out here raises the odds of more cash-outs nearby for a few days."""
    days = rng.integers(C.EXCITE_DAYS[0], C.EXCITE_DAYS[1] + 1)
    lo, hi = day + 1, min(day + 1 + days, len(world["boost"]))
    world["boost"][lo:hi, district] += C.EXCITE_STRENGTH
    for nb in world["neighbor_lists"][district]:
        world["boost"][lo:hi, nb] += C.EXCITE_STRENGTH * C.EXCITE_NEIGHBOR_FACTOR


def pick_mule(rng, world, day, district=None):
    """A mule account: in a given district, else from hotspots half the time."""
    if district is None and rng.random() < C.MULE_HOTSPOT_PULL:
        hs = world["hotspots_by_day"][day]
        district = int(hs[rng.integers(len(hs))])
    pool = world["mules_by_district"][district] if district is not None else world["all_mules"]
    return int(pool[rng.integers(len(pool))])


def build_chain(rng, world, complaint_id, victim_account, amount, t0, day, cashout_district):
    """Money hops victim -> mule1 -> ... over 3-7 hops with occasional fan-out.

    If cashout_district is given, every account at the LAST hop sits in that
    district (the mules who will walk to the ATMs).
    Returns (transaction rows, list of (final_account, amount, time)).
    """
    n_hops = int(rng.integers(C.HOPS_MIN, C.HOPS_MAX + 1))
    t1 = t0 + rng.uniform(*C.FIRST_HOP_DELAY_MIN)
    mule1 = pick_mule(rng, world, day)
    txns = [(complaint_id, victim_account, mule1, round(amount, 2), t1, 1)]
    frontier = [(mule1, amount, t1)]

    for hop in range(2, n_hops + 1):
        last = hop == n_hops
        new_frontier = []
        for acc, amt, tm in frontier:
            delay = rng.lognormal(np.log(C.HOP_DELAY_MEDIAN_MIN), C.HOP_DELAY_SIGMA)
            t_next = tm + delay
            room = C.MAX_ACCOUNTS_PER_HOP - len(new_frontier)
            if room <= 0:
                # this hop is full: consolidate into an account already at
                # this hop (layering, then merging before cash-out)
                j = int(rng.integers(len(new_frontier)))
                to_acc, amt_there, t_there = new_frontier[j]
                txns.append((complaint_id, acc, to_acc, round(amt, 2), t_next, hop))
                new_frontier[j] = (to_acc, amt_there + amt, max(t_there, t_next))
                continue
            k = 1
            if rng.random() < C.SPLIT_PROB:
                k = int(rng.integers(C.FANOUT_MIN, C.FANOUT_MAX + 1))
            k = min(k, room)
            shares = rng.dirichlet(np.ones(k)) if k > 1 else [1.0]
            for share in shares:
                to_acc = pick_mule(rng, world, day, cashout_district if last else None)
                txns.append((complaint_id, acc, to_acc, round(amt * share, 2), t_next, hop))
                new_frontier.append((to_acc, amt * share, t_next))
        frontier = new_frontier
    return txns, frontier


def build_withdrawals(rng, world, complaint_id, amount, t0, final_accounts, district):
    """Split the cash-out into structured ATM withdrawals in `district`."""
    cash_total = amount * rng.uniform(*C.CASHOUT_FRACTION)
    delay_h = rng.lognormal(np.log(C.CASHOUT_DELAY_MEDIAN_H), C.CASHOUT_DELAY_SIGMA)
    delay_h = float(np.clip(delay_h, *C.CASHOUT_DELAY_RANGE_H))
    t = t0 + delay_h * 60

    # quiet day? maybe slip to the next day
    day = int(t // MIN_PER_DAY)
    if is_quiet_day(day, world["holidays"]) and rng.random() > C.HOLIDAY_KEEP_PROB:
        day += 1
    # snap the hour to the diurnal pattern, but never before the money arrived
    hour = rng.choice(24, p=WITHDRAWAL_HOUR_P)
    t = day * MIN_PER_DAY + hour * 60 + rng.uniform(0, 60)
    last_hop = max(tm for _, _, tm in final_accounts)
    t = max(t, last_hop + 30)

    atm_pool = world["atms_by_district"][district]
    rows, remaining, i = [], cash_total, 0
    # always at least one withdrawal; stop when what's left is too small
    while (i == 0 or remaining >= C.WITHDRAWAL_MIN / 2) and i < C.MAX_WITHDRAWALS_PER_CHAIN:
        w = min(remaining, rng.uniform(C.WITHDRAWAL_MIN, C.WITHDRAWAL_MAX))
        w = max(C.WITHDRAWAL_ROUND, C.WITHDRAWAL_ROUND * round(w / C.WITHDRAWAL_ROUND))
        acc = final_accounts[i % len(final_accounts)][0]
        atm = int(atm_pool[rng.integers(len(atm_pool))])
        rows.append((complaint_id, atm, district, acc, float(w), t))
        t += rng.uniform(*C.WITHDRAWAL_GAP_MIN)
        remaining -= w
        i += 1
    return rows, int(rows[0][5] // MIN_PER_DAY)


def simulate(rng, world):
    """Day-by-day loop producing complaints, transactions and withdrawals."""
    complaints, transactions, withdrawals = [], [], []
    cats = list(C.FRAUD_CATEGORIES.keys())
    cat_p = np.array(list(C.FRAUD_CATEGORIES.values()))
    cat_p = cat_p / cat_p.sum()
    victim_acc = world["victim_accounts"]
    victim_dist = world["victim_districts"]
    complaint_id = 0

    for day in range(C.N_DAYS):
        n_today = rng.poisson(C.COMPLAINTS_PER_DAY * C.COMPLAINT_WEEKDAY_FACTOR[weekday_of(day)])
        for _ in range(n_today):
            t0 = day * MIN_PER_DAY + rng.choice(24, p=COMPLAINT_HOUR_P) * 60 + rng.uniform(0, 60)
            cat = cats[rng.choice(len(cats), p=cat_p)]
            amount = rng.lognormal(np.log(C.AMOUNT_MEDIAN[cat]), C.AMOUNT_SIGMA)
            amount = max(C.AMOUNT_MIN, 100 * round(amount / 100))
            v = rng.integers(len(victim_acc))
            report_delay = rng.lognormal(np.log(C.REPORT_DELAY_MEDIAN_H), C.REPORT_DELAY_SIGMA) * 60

            cashout = rng.random() < C.CASHOUT_PROB
            target = None
            if cashout:
                # decide the cash-out day first so the district choice sees
                # that day's active hotspots and excitation
                target_day = min(day + 1, C.N_DAYS - 1)
                target = pick_cashout_district(rng, world, target_day)

            txns, final_accounts = build_chain(
                rng, world, complaint_id, int(victim_acc[v]), amount, t0, day, target)
            transactions.extend(txns)

            if cashout:
                rows, cash_day = build_withdrawals(
                    rng, world, complaint_id, amount, t0, final_accounts, target)
                withdrawals.extend(rows)
                excite(world, target, min(cash_day, C.N_DAYS - 1), rng)

            complaints.append((complaint_id, t0, t0 + report_delay, int(victim_dist[v]),
                               int(victim_acc[v]), cat, float(amount), txns[0][2]))
            complaint_id += 1
        if day % 30 == 0:
            print(f"  day {day:3d}: {len(complaints):7d} complaints, "
                  f"{len(transactions):8d} txns, {len(withdrawals):7d} withdrawals")

    complaints = pd.DataFrame(complaints, columns=[
        "complaint_id", "t", "t_reported", "victim_district", "victim_account",
        "fraud_category", "amount", "first_hop_account"])
    complaints["timestamp"] = to_timestamp(complaints.pop("t"))
    complaints["reported_at"] = to_timestamp(complaints.pop("t_reported"))

    transactions = pd.DataFrame(transactions, columns=[
        "complaint_id", "from_account", "to_account", "amount", "t", "hop_number"])
    transactions["timestamp"] = to_timestamp(transactions.pop("t"))
    transactions.insert(0, "txn_id", np.arange(len(transactions)))

    withdrawals = pd.DataFrame(withdrawals, columns=[
        "complaint_id", "atm_id", "district_id", "account_id", "amount", "t"])
    withdrawals["timestamp"] = to_timestamp(withdrawals.pop("t"))
    withdrawals = withdrawals.sort_values("timestamp").reset_index(drop=True)
    withdrawals.insert(0, "withdrawal_id", np.arange(len(withdrawals)))
    return complaints, transactions, withdrawals


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_db(tables):
    """Write every DataFrame to SQLite (replacing the file) and add indexes."""
    if os.path.exists(C.DB_PATH):
        os.remove(C.DB_PATH)
    conn = sqlite3.connect(C.DB_PATH)
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:  # timestamps as plain ISO text for SQLite
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        df.to_sql(name, conn, index=False, if_exists="replace")
    for stmt in [
        "CREATE INDEX ix_complaints_ts ON complaints(timestamp)",
        "CREATE INDEX ix_txn_complaint ON transactions(complaint_id)",
        "CREATE INDEX ix_txn_ts ON transactions(timestamp)",
        "CREATE INDEX ix_wd_ts ON withdrawals(timestamp)",
        "CREATE INDEX ix_wd_district ON withdrawals(district_id)",
        "CREATE INDEX ix_accounts_district ON accounts(district_id)",
    ]:
        conn.execute(stmt)
    conn.commit()
    conn.close()


def main():
    t_start = time.time()
    rng = np.random.default_rng(C.SEED)

    print("building static world ...")
    districts, neighbors = build_districts(rng)
    atms = build_atms(rng, districts)
    accounts = build_accounts(rng, districts)
    holidays, holidays_df = build_holidays(rng)
    neighbor_lists = neighbors.groupby("district_id")["neighbor_id"].apply(list).to_dict()
    hotspots_by_day, hotspot_history = build_hotspot_timeline(rng, districts, neighbor_lists)
    print(f"  {len(districts)} districts, {len(atms)} ATMs, {len(accounts)} accounts, "
          f"{len(hotspot_history)} hotspot episodes")

    mules = accounts[accounts["holder_type"] == "mule"]
    victims = accounts[accounts["holder_type"] == "victim"]
    world = {
        "pop_weight": districts["population_weight"].to_numpy(),
        "neighbor_lists": neighbor_lists,
        "hotspots_by_day": hotspots_by_day,
        "holidays": holidays,
        "boost": np.zeros((C.N_DAYS + 10, len(districts))),  # self-excitation per day
        "mules_by_district": mules.groupby("district_id")["account_id"].apply(np.array).to_dict(),
        "all_mules": mules["account_id"].to_numpy(),
        "atms_by_district": atms.groupby("district_id")["atm_id"].apply(np.array).to_dict(),
        "victim_accounts": victims["account_id"].to_numpy(),
        "victim_districts": victims["district_id"].to_numpy(),
    }

    print("simulating 12 months ...")
    complaints, transactions, withdrawals = simulate(rng, world)

    print("writing database ...")
    tables = {
        "districts": districts, "district_neighbors": neighbors, "atms": atms,
        "accounts": accounts, "holidays": holidays_df, "hotspot_history": hotspot_history,
        "complaints": complaints, "transactions": transactions, "withdrawals": withdrawals,
    }
    write_db(tables)
    for name, df in tables.items():
        print(f"  {name:20s} {len(df):>9,d} rows")
    print(f"done in {time.time() - t_start:.1f}s -> {C.DB_PATH}")


if __name__ == "__main__":
    main()
