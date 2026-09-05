"""
Real Census-2011 district populations, joined onto our GeoJSON districts.

Why this exists: Phase 1 used a random log-normal population proxy, which
occasionally handed a remote district (Kargil, Leh) a bigger weight than a
metro and let it be drawn as a mule-corridor hotspot. That was the single
least believable thing in the demo.

The join is by district name within state, in three passes:
  1. exact match on a normalised name
  2. alias table for known renames (Gurgaon -> Gurugram, Allahabad -> Prayagraj)
  3. fuzzy match with difflib, accepted only above a similarity cutoff

Districts still unmatched are almost all created AFTER 2011 (our map has 724
districts, the census has 640), so they have no census row by definition. They
fall back to the median population of their own state, which is the right
regional prior for a district carved out of that state.

Run alone to see the join report:  python -m datagen.population
"""
import difflib
import os
import re
import urllib.request

import numpy as np
import pandas as pd

from datagen import config as C

CSV_URL = ("https://raw.githubusercontent.com/nishusharma1608/India-Census-2011-Analysis"
           "/master/india-districts-census-2011.csv")
CSV_PATH = "data/census2011_districts.csv"
FUZZY_CUTOFF = 0.86        # below this we prefer the state-median fallback

# States that did not exist in 2011: look their districts up in the parent state.
STATE_FALLBACK = {
    "Telangana": "Andhra Pradesh",      # carved out of AP in 2014
    "Ladakh": "Jammu and Kashmir",      # carved out of J&K in 2019
}

# Our map holds these as ONE district, while the census splits them into several
# rows; we sum the whole state/UT instead of matching a name.
WHOLE_STATE_DISTRICTS = {("Delhi", "Delhi"), ("Chandigarh", "Chandigarh"),
                         ("Lakshadweep", "Lakshadweep")}

# Census state name -> our GeoJSON state name.
STATE_ALIASES = {
    "JAMMU AND KASHMIR": "Jammu and Kashmir", "NCT OF DELHI": "Delhi",
    "ANDAMAN AND NICOBAR ISLANDS": "Andaman and Nicobar Islands",
    "DADRA AND NAGAR HAVELI": "Dadra and Nagar Haveli and Daman and Diu",
    "DAMAN AND DIU": "Dadra and Nagar Haveli and Daman and Diu",
    "PONDICHERRY": "Puducherry", "ORISSA": "Odisha", "UTTARAKHAND": "Uttarakhand",
    "CHHATTISGARH": "Chhattisgarh", "ANDHRA PRADESH": "Andhra Pradesh",
}

# District renames and spelling differences (our name -> census name).
DISTRICT_ALIASES = {
    "gurugram": "gurgaon", "prayagraj": "allahabad", "ayodhya": "faizabad",
    "bengaluru urban": "bangalore", "bengaluru rural": "bangalore rural",
    "kamrup metropolitan": "kamrup metropolitan", "leh": "leh ladakh",
    "kargil": "kargil", "mumbai": "mumbai suburban", "sivasagar": "sibsagar",
    "hooghly": "hugli", "howrah": "haora", "kolkata": "kolkata",
    "north 24 parganas": "north twenty four parganas",
    "south 24 parganas": "south twenty four parganas",
    "purba bardhaman": "barddhaman", "paschim bardhaman": "barddhaman",
    "cooch behar": "koch bihar", "purba medinipur": "purba medinipur",
    "paschim medinipur": "paschim medinipur", "nuh": "mewat",
    "saraikela-kharsawan": "saraikela kharsawan", "sonipat": "sonipat",
    "gautam buddha nagar": "gautam buddha nagar", "lakhimpur kheri": "kheri",
    "shrawasti": "shrawasti", "sambhal": "moradabad", "hapur": "ghaziabad",
    "shamli": "muzaffarnagar", "amroha": "jyotiba phule nagar",
    "kasganj": "kanshiram nagar", "bhadohi": "sant ravidas nagar",
    "dima hasao": "north cachar hills", "karbi anglong": "karbi anglong",
    "west karbi anglong": "karbi anglong", "kallakurichi": "villupuram",
    "yadgir": "yadgir", "chikkaballapura": "chikkaballapura",
}


def _norm(s):
    """Lowercase, strip punctuation and common suffixes so names compare cleanly."""
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)          # '(', '-', '&' -> space
    s = re.sub(r"\b(district|dist|pradesh)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def download_census():
    if not os.path.exists(CSV_PATH):
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        print(f"downloading Census 2011 districts from {CSV_URL} ...")
        urllib.request.urlretrieve(CSV_URL, CSV_PATH)


def load_census():
    download_census()
    df = pd.read_csv(CSV_PATH, usecols=["District code", "State name", "District name", "Population"])
    df.columns = ["census_code", "state_raw", "name_raw", "population"]
    df["state"] = df["state_raw"].map(lambda s: STATE_ALIASES.get(s.strip().upper(), s.strip().title()))
    df["key"] = df["name_raw"].map(_norm)
    return df


def attach_population(districts, verbose=True):
    """Add a real `population` column to the districts frame.

    Returns (districts_with_population, report_dict).
    """
    census = load_census()
    by_state = {st: g for st, g in census.groupby("state")}
    state_median = census.groupby("state")["population"].median().to_dict()
    national_median = float(census["population"].median())

    pops, how, unmatched, matched_row = [], [], [], []
    for d in districts.itertuples():
        key = _norm(d.name)
        # a state that did not exist in 2011 searches its parent state's rows
        search_state = STATE_FALLBACK.get(d.state, d.state)
        pool = by_state.get(search_state)
        hit, method, row_id = None, None, None

        if (d.state, d.name) in WHOLE_STATE_DISTRICTS:         # 0. whole UT summed
            sub = by_state.get(d.state)
            if sub is not None:
                hit, method = float(sub["population"].sum()), "whole_state_sum"
        if hit is None and pool is not None:
            lookup = dict(zip(pool["key"], zip(pool["population"], pool["census_code"])))
            if key in lookup:                                  # 1. exact
                (hit, row_id), method = lookup[key], "exact"
            elif DISTRICT_ALIASES.get(key) in lookup:          # 2. alias
                (hit, row_id), method = lookup[DISTRICT_ALIASES[key]], "alias"
            else:                                              # 3. fuzzy
                close = difflib.get_close_matches(key, list(lookup), n=1, cutoff=FUZZY_CUTOFF)
                if close:
                    (hit, row_id), method = lookup[close[0]], f"fuzzy:{close[0]}"

        if hit is None:                                        # 4. regional median
            hit = state_median.get(search_state, national_median)
            method = "state_median"
            unmatched.append((d.state, d.name))
        pops.append(float(hit))
        how.append(method)
        matched_row.append(row_id)

    out = districts.copy()
    out["population"] = pops
    out["population_source"] = how
    # Several of our districts can map to ONE census row (a 2011 district that
    # has since been split, e.g. Barddhaman -> Purba + Paschim Bardhaman).
    # Share the parent population between them instead of counting it twice.
    shared = pd.Series(matched_row).value_counts()
    for row_id, n in shared[shared > 1].items():
        if row_id is None:
            continue
        mask = np.array([r == row_id for r in matched_row])
        out.loc[mask, "population"] = out.loc[mask, "population"] / n
        out.loc[mask, "population_source"] = out.loc[mask, "population_source"] + f"/split{n}"
    # population_weight stays the modelling unit: mean 1.0 across districts
    out["population_weight"] = out["population"] / out["population"].mean()

    # Our map has 724 districts against the census's 640, so districts created
    # after 2011 would otherwise ADD population that the parent already counts.
    # Rescale each state so its districts sum to that state's real census total:
    # the national total then comes out right and post-2011 districts get a
    # sensible share of their state rather than an invented one.
    census_state_total = census.groupby("state")["population"].sum().to_dict()
    out["_census_state"] = out["state"].map(lambda st: STATE_FALLBACK.get(st, st))
    for cstate, group in out.groupby("_census_state"):
        target = census_state_total.get(cstate)
        if target and group["population"].sum() > 0:
            out.loc[group.index, "population"] *= target / group["population"].sum()
    out = out.drop(columns="_census_state")
    out["population"] = out["population"].round()
    out["population_weight"] = out["population"] / out["population"].mean()

    counts = pd.Series(how).str.split(":").str[0].value_counts().to_dict()
    report = {"counts": counts, "unmatched": unmatched,
              "total_population": float(out["population"].sum())}
    if verbose:
        print("population join:")
        for k, v in counts.items():
            print(f"  {k:14s} {v:4d}")
        print(f"  total population {report['total_population'] / 1e7:,.1f} crore "
              f"(census 2011 total was 121.1 crore)")
        if unmatched:
            print(f"  {len(unmatched)} districts fell back to their state median "
                  f"(mostly created after 2011):")
            for st, nm in unmatched:
                print(f"      {nm}, {st}")
    return out, report


if __name__ == "__main__":
    from datagen import geo
    d = geo.clean_geojson()
    out, rep = attach_population(d)
    print()
    print("largest 8 by population:")
    print(out.nlargest(8, "population")[["name", "state", "population", "population_weight"]].to_string(index=False))
    print("\nsmallest 5:")
    print(out.nsmallest(5, "population")[["name", "state", "population", "population_weight"]].to_string(index=False))
