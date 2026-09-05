"""
Turn raw LightGBM feature contributions into reason codes an officer can read.

Nothing here is hardcoded per district or per alert: we take the model's actual
per-row `pred_contrib` values, pick the features that pushed THIS score up the
most, and render each one with the row's real feature value.
"""
import numpy as np

from features import config as FC

CASHOUT_MEDIAN_H = 14  # from the Phase 1 validation: median fraud -> first cash-out


def rupees(v):
    """Indian-style short money format."""
    v = float(v)
    if v >= 1e7:
        return f"Rs {v / 1e7:.1f}Cr"
    if v >= 1e5:
        return f"Rs {v / 1e5:.1f}L"
    if v >= 1e3:
        return f"Rs {v / 1e3:.0f}K"
    return f"Rs {v:.0f}"


def _hour_block_label(v):
    start = int(v) * FC.WINDOW_HOURS
    return f"{start:02d}:00-{(start + FC.WINDOW_HOURS):02d}:00"


def _ago(hours):
    """Readable elapsed time - '7 min ago' beats '0h ago'."""
    if hours < 1:
        return f"{max(int(round(hours * 60)), 1)} min ago"
    if hours < 48:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f} days ago"


def _chain_age_phrase(v):
    """Wording for min_chain_age_hours - the YOUNGEST chain, not an average."""
    if v <= 2:
        return f"a chain here is only {_ago(v).replace(' ago', '')} old - money just landed"
    if v <= 24:
        near = "near" if 8 <= v <= 20 else "approaching"
        return f"youngest chain here is {v:.0f}h old - {near} the ~{CASHOUT_MEDIAN_H}h cash-out median"
    return f"youngest chain here is {v:.0f}h old"


# feature -> function(value, row) -> human sentence.
TEMPLATES = {
    "money_in_flight_here": lambda v, r: (
        f"{rupees(v)} in flight across {int(r['n_active_chains_here'])} active chain(s) here"),
    "n_active_chains_here": lambda v, r: f"{int(v)} active mule chain(s) holding money here",
    "n_active_accounts_here": lambda v, r: f"{int(v)} mule account(s) here currently holding funds",
    "min_chain_age_hours": lambda v, r: _chain_age_phrase(v),
    "avg_chain_age_hours": lambda v, r: (
        f"active chains here average {v:.0f}h old (cash-out median ~{CASHOUT_MEDIAN_H}h)"),
    "avg_active_hop_here": lambda v, r: (
        f"funds sitting at hop {v:.1f} of the chain - late hops cash out next"),

    "wd_1d": lambda v, r: f"{int(v)} fraud withdrawal(s) here in the past 24h",
    "wd_3d": lambda v, r: f"{int(v)} fraud withdrawal(s) here in the past 3 days",
    "wd_7d": lambda v, r: f"{int(v)} fraud withdrawal(s) here in the past 7 days",
    "wd_30d": lambda v, r: f"{int(v)} fraud withdrawal(s) here in the past 30 days",
    "wd_decay": lambda v, r: f"recent cash-out activity here is elevated (decayed count {v:.1f})",
    "wd_nb_1d": lambda v, r: f"{int(v)} withdrawal(s) in neighbouring districts in the past 24h",
    "wd_nb_7d": lambda v, r: f"{int(v)} withdrawal(s) in neighbouring districts in the past 7 days",
    "hrs_since_wd_here": lambda v, r: (
        f"last cash-out here was {_ago(v)} - corridor still hot"
        if v <= 72 else f"no cash-out here for {v / 24:.0f} days"),
    "hrs_since_wd_nb": lambda v, r: f"a neighbouring district had a cash-out {_ago(v)}",

    "is_active_hotspot_30d": lambda v, r: (
        "district is in the current top-25 corridor list (past 30 days)"
        if v >= 0.5 else "district is outside the current top-25 corridor list"),
    "dist_to_active_hotspot_km": lambda v, r: (
        "district is itself an active corridor" if v <= 1
        else f"{v:.0f} km from the nearest active corridor"),
    "is_hotspot": lambda v, r: ("historically known mule corridor" if v >= 0.5
                                else "not a historically known corridor"),

    "hour_block": lambda v, r: f"{_hour_block_label(v)} is a peak cash-out window",
    "day_of_week": lambda v, r: ["Monday", "Tuesday", "Wednesday", "Thursday",
                                 "Friday", "Saturday", "Sunday"][int(v)] + " pattern",
    "is_weekend": lambda v, r: "weekend" if v >= 0.5 else "weekday",
    "is_holiday": lambda v, r: "bank holiday" if v >= 0.5 else "normal banking day",
    "n_atms": lambda v, r: f"{int(v)} ATMs available for structured withdrawals",
    "population_weight": lambda v, r: f"large population base (weight {v:.1f})",

    "cmp_local_1d": lambda v, r: f"{int(v)} fraud complaint(s) filed by victims here in the past 24h",
    "cmp_local_7d": lambda v, r: f"{int(v)} fraud complaint(s) filed by victims here in the past 7 days",
    "cmp_nb_7d": lambda v, r: f"{int(v)} complaint(s) from neighbouring districts in the past 7 days",
}


def _nationwide_template(feature, v):
    # cmp_nat_<category>_<N>d
    _, _, category, horizon = feature.split("_", 3)
    return f"national {category.replace('_', ' ')} complaint volume: {int(v)} in the past {horizon}"


def describe(feature, value, row):
    if feature in TEMPLATES:
        return TEMPLATES[feature](value, row)
    if feature.startswith("cmp_nat_"):
        return _nationwide_template(feature, value)
    return f"{feature} = {value:.2f}"


def reason_codes(contrib_row, row, features, top_n=3):
    """The `top_n` features that pushed this score UP the most, as sentences.

    contrib_row: one row of pred_contrib (last element is the base value).
    row: the matching feature row (a pandas Series) for real values.
    """
    contribs = np.asarray(contrib_row[:len(features)], dtype=float)
    order = np.argsort(-contribs)
    out = []
    for i in order[:top_n]:
        if contribs[i] <= 0:
            break
        feature = features[i]
        out.append({
            "feature": feature,
            "value": float(row[feature]),
            "contribution": round(float(contribs[i]), 4),
            "reason": describe(feature, float(row[feature]), row),
        })
    return out


def recommended_action(row, codes, state):
    """A concrete next step, driven by the row's own numbers."""
    money = float(row["money_in_flight_here"])
    chains = int(row["n_active_chains_here"])
    district = int(row["district_id"])
    risk = float(row["risk"])

    atms = state.atms_by_district.get(district)
    banks = (atms["bank"].value_counts().head(3).index.tolist() if atms is not None else [])
    bank_text = ", ".join(banks) if banks else "local banks"
    n_atms = state.n_atms.get(district, 0)

    steps = []
    if risk >= 0.8:
        steps.append("Deploy a field team to the district's main ATM clusters this window")
    elif risk >= 0.5:
        steps.append("Put a field team on standby and brief the district cyber cell")
    else:
        steps.append("Monitor - no deployment warranted yet")

    if money > 0 and chains > 0:
        steps.append(f"Alert {bank_text} to flag {n_atms} ATMs here and hold withdrawals "
                     f"linked to the {chains} chain(s) carrying {rupees(money)}")
        steps.append("Pre-file freeze requests via CFCFRMS for the holding accounts listed in the drill-down")
    else:
        steps.append(f"Ask {bank_text} for same-day CCTV retention on {n_atms} ATMs here")
    return steps
