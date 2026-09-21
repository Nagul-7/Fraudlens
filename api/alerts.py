"""
Phase 6 - alert engine, role-based scoping, and dispatch messages.

Three things live here:

1. AlertStore - alerts are created when the clock advances and a district's
   risk crosses the threshold. Each carries the evidence that produced it
   (reason codes from the model's own contributions) and a status the operator
   can change: new -> acknowledged | dismissed.

2. Role scoping. Three roles see genuinely different slices of the data:
     I4C     - everything, all 724 districts
     STATE   - one state's districts only, plus a cross-jurisdiction inbox
     BANK    - no crime intelligence at all; only that bank's own ATMs and
               accounts, with freeze recommendations
   This is data segregation, not a UI filter: the scoping happens here, on the
   server, so a bank response never contains another institution's data or the
   underlying crime intelligence.

3. Dispatch - the SMS/email text an officer would actually receive. Nothing is
   sent anywhere; the message is logged and returned so it can be shown.
"""
import itertools
from datetime import datetime

import pandas as pd

from api import reasons as R

ROLES = ("I4C", "STATE", "BANK")
STATUSES = ("new", "acknowledged", "dismissed")

# Why the segregation exists - surfaced in the UI as a tooltip.
SEGREGATION_NOTE = (
    "Role-based data segregation is a legal requirement, not a UI convenience. "
    "A bank may see only its own accounts and ATMs and never the underlying "
    "crime intelligence; a State LEA may see only districts in its own "
    "jurisdiction. Cross-jurisdiction information is shared as a specific "
    "referral, not as open access to another state's caseload."
)


class Alert:
    _ids = itertools.count(1)

    def __init__(self, row, window_idx, window_start, codes, actions, state_name, district_name):
        self.alert_id = next(Alert._ids)
        self.district_id = int(row["district_id"])
        self.district = district_name
        self.state = state_name
        self.window_idx = int(window_idx)
        self.window_start = window_start
        self.risk = round(float(row["risk"]), 4)
        self.rank = int(row["rank"])
        self.money_in_flight = float(row["money_in_flight_here"])
        self.active_chains = int(row["n_active_chains_here"])
        self.active_accounts = int(row["n_active_accounts_here"])
        self.reason_codes = codes
        self.recommended_action = actions
        self.status = "new"
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.dispatched = []

    def to_dict(self):
        return {
            "alert_id": self.alert_id, "district_id": self.district_id,
            "district": self.district, "state": self.state,
            "window_idx": self.window_idx, "window_start": self.window_start,
            "risk": self.risk, "rank": self.rank,
            "money_in_flight": self.money_in_flight,
            "money_in_flight_display": R.rupees(self.money_in_flight),
            "active_chains": self.active_chains, "active_accounts": self.active_accounts,
            "reason_codes": self.reason_codes, "recommended_action": self.recommended_action,
            "status": self.status, "created_at": self.created_at,
            "dispatched": self.dispatched,
        }


class AlertStore:
    def __init__(self):
        self.alerts = []

    def create_for_window(self, state, window_idx, threshold):
        """One alert per district crossing `threshold` in this window."""
        rows = state.window_rows(window_idx).reset_index(drop=True)
        contrib = state.contributions(window_idx)
        hits = rows.index[rows["risk"] >= threshold].tolist()
        hits.sort(key=lambda i: -rows.at[i, "risk_raw"])
        made = []
        for i in hits:
            row = rows.loc[i]
            d = int(row["district_id"])
            codes = R.reason_codes(contrib[i], row, state.features)
            alert = Alert(
                row, window_idx, state.window_start(window_idx).isoformat(),
                codes, R.recommended_action(row, codes, state),
                state.district_state[d], state.district_name[d],
            )
            self.alerts.append(alert)
            made.append(alert)
        return made

    def get(self, alert_id):
        return next((a for a in self.alerts if a.alert_id == alert_id), None)

    def visible(self, role, state_name=None):
        """Alerts this role is allowed to see. A bank sees none: alerts are
        crime intelligence."""
        if role == "BANK":
            return []
        if role == "STATE":
            return [a for a in self.alerts if a.state == state_name]
        return list(self.alerts)

    def counts(self, role, state_name=None):
        vis = self.visible(role, state_name)
        return {s: sum(1 for a in vis if a.status == s) for s in STATUSES} | {"total": len(vis)}


# ---------------------------------------------------------------------------
# Dispatch: the message an officer would actually receive
# ---------------------------------------------------------------------------
def sms_for_alert(alert):
    top = alert.reason_codes[0]["reason"] if alert.reason_codes else "elevated risk"
    when = pd.Timestamp(alert.window_start)
    # Plenty of alerts fire on recent cash-out activity with no money currently
    # parked in the district. Saying "0 chains holding Rs 0" would read as a bug
    # on an officer's phone, so that clause is simply omitted.
    money = (f"{alert.active_chains} mule chain(s) holding "
             f"{R.rupees(alert.money_in_flight)} here. "
             if alert.active_chains > 0 else "")
    return (
        f"[I4C FraudLens] HIGH RISK {alert.district}, {alert.state} "
        f"{when:%d-%b %H:%M}-{when + pd.Timedelta(hours=6):%H:%M}. "
        f"Predicted cash-out risk {alert.risk * 100:.0f}%. "
        f"{money}"
        f"Reason: {top}. "
        f"Action: deploy to ATM clusters, alert bank nodal officers. "
        f"Ref ALERT-{alert.alert_id:05d}. SYNTHETIC DEMO DATA."
    )


def email_for_alert(alert, atm_count, banks):
    when = pd.Timestamp(alert.window_start)
    lines = [
        f"To: SP Cyber Crime, {alert.district} District, {alert.state}",
        f"Cc: State Cyber Nodal Officer; Bank Nodal Officers ({', '.join(banks) or 'n/a'})",
        f"Subject: PREDICTIVE ALERT ALERT-{alert.alert_id:05d} - "
        f"{alert.district} - window {when:%d %b %Y %H:%M} to {when + pd.Timedelta(hours=6):%H:%M} IST",
        "",
        f"A predictive alert has been raised for {alert.district}, {alert.state}.",
        "",
        f"  Risk score          {alert.risk * 100:.1f}% (calibrated)",
        f"  National rank       {alert.rank} of 724 districts",
        f"  Money in flight     " + (
            f"{R.rupees(alert.money_in_flight)} across {alert.active_chains} chain(s) "
            f"in {alert.active_accounts} account(s)" if alert.active_chains > 0
            else "none currently parked here - alert is driven by recent cash-out activity"),
        f"  ATMs in district    {atm_count}",
        "",
        "Evidence:",
    ]
    lines += [f"  {i}. {c['reason']}" for i, c in enumerate(alert.reason_codes, 1)]
    lines += ["", "Recommended action:"]
    lines += [f"  {i}. {a}" for i, a in enumerate(alert.recommended_action, 1)]
    lines += [
        "",
        "This alert is generated by a predictive model on SYNTHETIC data for "
        "demonstration. It is not an intelligence input for live operations.",
        "-- FraudLens v0.1 (prototype, SIH26184)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cross-jurisdiction: money leaving the state where the complaint was filed
# ---------------------------------------------------------------------------
def cross_jurisdiction(state, window_idx, origin_state, limit=60, fraud_category=None):
    """Chains whose complaint was filed in `origin_state` but whose money now
    sits in a district in a DIFFERENT state.

    This is the coordination gap in the problem statement: the state that took
    the complaint has no visibility of where the cash-out is about to happen,
    and the destination state has no idea a case is heading its way.
    """
    held = state.active_holdings(window_idx)
    if held.empty:
        return []
    cm = state.complaints
    held = held.assign(
        victim_district=held["complaint_id"].map(cm["victim_district"]),
        fraud_category=held["complaint_id"].map(cm["fraud_category"]),
        original_amount=held["complaint_id"].map(cm["amount"]),
    )
    held["origin_state"] = held["victim_district"].map(state.district_state)
    held["dest_state"] = held["district_id"].map(state.district_state)
    out = held[(held["origin_state"] == origin_state) & (held["dest_state"] != origin_state)]
    if fraud_category:                      # the dashboard's category filter
        out = out[out["fraud_category"] == fraud_category]
    if out.empty:
        return []
    grouped = (out.groupby(["complaint_id", "victim_district", "district_id",
                           "fraud_category", "dest_state"], as_index=False)
                  .agg(amount_held=("amount", "sum"), age_hours=("age_hours", "min"),
                       hop=("hop_number", "max")))
    grouped = grouped.sort_values("amount_held", ascending=False).head(limit)

    risk = state.window_rows(window_idx).set_index("district_id")["risk"]
    return [{
        "complaint_id": int(r.complaint_id),
        "origin_district": state.district_name[int(r.victim_district)],
        "origin_district_id": int(r.victim_district),
        "dest_district": state.district_name[int(r.district_id)],
        "dest_district_id": int(r.district_id),
        "dest_state": r.dest_state,
        "fraud_category": r.fraud_category,
        "amount_held": float(r.amount_held),
        "amount_held_display": R.rupees(r.amount_held),
        "age_hours": round(float(r.age_hours), 1),
        "hop": int(r.hop),
        "dest_risk": round(float(risk.get(int(r.district_id), 0.0)), 4),
    } for r in grouped.itertuples()]


# ---------------------------------------------------------------------------
# Bank view: only this institution's own exposure
# ---------------------------------------------------------------------------
def _districts_of_state(state, state_name):
    """District ids in one state, or None when no state is given (= no limit)."""
    if not state_name:
        return None
    return {int(d) for d, st in state.district_state.items() if st == state_name}


def bank_footprint(state, window_idx, bank, state_name=None):
    """The districts a bank is entitled to see: where it operates an ATM, OR
    where one of its accounts is currently holding flagged funds.

    This is the ONE definition of a bank's footprint. /bank/exposure reports it
    as `own_district_ids` and the role-scoped /heatmap filters to it, so the two
    can never disagree about what a bank may see.

    ATMs alone would leave a bank's map blank in a state where it has an exposed
    account but no machines. Districts are matched by id, never by name: five
    district names repeat across states (Aurangabad, Balrampur, Bilaspur,
    Hamirpur, Pratapgarh).
    """
    in_scope = _districts_of_state(state, state_name)
    atm_districts = set(state.atm_districts_by_bank.get(bank, set()))
    if in_scope is not None:
        atm_districts &= in_scope

    account_districts = set()
    held = state.active_holdings(window_idx)
    if not held.empty:
        mine = held[held["account_id"].map(state.account_bank) == bank]
        if in_scope is not None:
            mine = mine[mine["district_id"].isin(in_scope)]
        account_districts = {int(d) for d in mine["district_id"].unique()}
    return atm_districts | account_districts


def allowed_district_ids(state, window_idx, role, state_name=None, bank=None):
    """Which districts may this role see? None means all of them (I4C).

    The server applies this before it builds a response, so out-of-scope
    districts are never sent - the client cannot un-hide what it never received.
    """
    if role == "STATE":
        return _districts_of_state(state, state_name)
    if role == "BANK":
        return bank_footprint(state, window_idx, bank)
    return None


def bank_exposure(state, window_idx, bank, min_risk=0.5, limit=40, state_name=None):
    """What one bank is allowed to see: its own ATMs in districts the model
    rates high risk, and its own accounts currently holding fraud money.

    Deliberately contains NO reason codes, no complaint details and no
    district ranking - a bank gets an operational instruction, not the
    intelligence behind it.

    `state_name` narrows every part of the response - ATM exposure, accounts
    holding funds, and the district footprint - to one state. It has to scope
    all three together: filtering only the map while the account table stayed
    national is how this went wrong the first time.
    """
    in_scope = _districts_of_state(state, state_name)

    rows = state.window_rows(window_idx).set_index("district_id")
    risky = rows[rows["risk"] >= min_risk]
    if in_scope is not None:
        risky = risky[risky.index.isin(in_scope)]

    atm_rows = []
    for d in risky.index:
        atms = state.atms_by_district.get(int(d))
        if atms is None:
            continue
        mine = atms[atms["bank"] == bank]
        if len(mine) == 0:
            continue
        atm_rows.append({
            "district_id": int(d),
            "district": state.district_name[int(d)],
            "state": state.district_state[int(d)],
            "risk": round(float(risky.at[d, "risk"]), 4),
            "our_atms": int(len(mine)),
            "atm_ids": [int(x) for x in mine["atm_id"].head(12)],
        })
    atm_rows.sort(key=lambda r: -r["risk"])

    # our accounts currently holding fraud money
    held = state.active_holdings(window_idx)
    account_rows = []
    if not held.empty:
        held = held.assign(bank=held["account_id"].map(state.account_bank))
        mine = held[held["bank"] == bank]
        if in_scope is not None:
            mine = mine[mine["district_id"].isin(in_scope)]
        if not mine.empty:
            g = (mine.groupby(["account_id", "district_id"], as_index=False)
                     .agg(amount_held=("amount", "sum"), age_hours=("age_hours", "min"),
                          n_chains=("complaint_id", "nunique")))
            g = g.sort_values("amount_held", ascending=False).head(limit)
            for r in g.itertuples():
                account_rows.append({
                    "account_id": int(r.account_id),
                    "district_id": int(r.district_id),
                    "district": state.district_name[int(r.district_id)],
                    "state": state.district_state[int(r.district_id)],
                    "amount_held": float(r.amount_held),
                    "amount_held_display": R.rupees(r.amount_held),
                    "age_hours": round(float(r.age_hours), 1),
                    "n_chains": int(r.n_chains),
                    # the older the chain, the closer to the ~14h cash-out median
                    "recommendation": ("Freeze immediately via CFCFRMS - within the "
                                       "typical cash-out window"
                                       if 6 <= r.age_hours <= 30 else
                                       "Flag and hold pending CFCFRMS confirmation"),
                })
    total = sum(a["amount_held"] for a in account_rows)
    # The only geography a bank is entitled to see risk for. Computed by the
    # shared bank_footprint() so /heatmap and this endpoint cannot disagree. (It
    # covers every district holding the bank's flagged funds; the account table
    # above is capped at `limit` rows, the footprint is not.)
    own_districts = sorted(bank_footprint(state, window_idx, bank, state_name))
    return {
        "bank": bank,
        "state_name": state_name,
        "own_district_ids": own_districts,
        "atm_exposure": atm_rows[:limit],
        "accounts_holding": account_rows,
        "totals": {
            "districts_at_risk": len(atm_rows),
            "our_atms_at_risk": sum(r["our_atms"] for r in atm_rows),
            "accounts_holding": len(account_rows),
            "amount_held": total,
            "amount_held_display": R.rupees(total),
        },
    }


STORE = AlertStore()
