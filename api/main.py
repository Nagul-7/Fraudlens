"""
FraudLens prediction API (Phase 4).

Run:  uvicorn api.main:app --reload
Docs: http://127.0.0.1:8000/docs

Every score served is a CALIBRATED probability from the Phase 3 model, and the
demo clock starts at the first window of the test period, so nothing the
dashboard shows was seen during training.
"""
import sqlite3

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from datagen import config as DC
from features import config as FC
from api import alerts as A
from api import reasons as R
from api.state import STATE

app = FastAPI(
    title="FraudLens API",
    version="0.1",
    description="Predictive cash-withdrawal intelligence. All data is SYNTHETIC; "
                "scores are out-of-sample predictions on the held-out test months.",
)
app.add_middleware(
    CORSMiddleware,            # the Phase 5 dashboard runs on a different port
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    STATE.load()


def _resolve(window):
    try:
        return STATE.resolve_window(window)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _window_meta(w):
    return {
        "window_idx": int(w),
        "window_start": STATE.window_start(w).isoformat(),
        "window_end": (STATE.window_start(w) + pd.Timedelta(hours=FC.WINDOW_HOURS)).isoformat(),
        "is_out_of_sample": bool(w >= STATE.test_start_window),
    }


# ---------------------------------------------------------------------------
# Role scoping. Every endpoint that returns district-level data takes the same
# three params as /feed, validates them with _check_role, and asks
# A.allowed_district_ids() what the caller may see BEFORE building a response.
# The prototype has no login, so the role is asserted by the caller; what this
# guarantees is that a response never contains more than the asserted role is
# entitled to. Production binds the role to an authenticated identity instead.
# ---------------------------------------------------------------------------
# Factories, not shared objects: each route gets its own Query instance.
def q_role():
    return Query("I4C", description="I4C | STATE | BANK - scopes the response to what this role may see")


def q_state_name():
    return Query(None, description="the jurisdiction; required for role=STATE")


def q_bank():
    return Query(None, description="the institution; required for role=BANK")


BANK_DENIED = ("This is crime intelligence and is not available to bank roles. "
               "A bank's operational view is /bank/exposure.")


def _deny_out_of_scope(role, district_id, state_name):
    """403 unless this role may see this district's detail."""
    if role == "BANK":
        raise HTTPException(403, BANK_DENIED)
    if role == "STATE" and STATE.district_state[district_id] != state_name:
        raise HTTPException(403, f"district {district_id} is outside your jurisdiction ({state_name})")


# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "service": "FraudLens API",
        "data": "SYNTHETIC - see docs/phase1_notes.md",
        "clock": _window_meta(STATE.clock),
        "endpoints": ["/heatmap", "/alerts", "/districts/{district_id}",
                      "/simulate/state", "/simulate/advance", "/docs"],
    }


@app.get("/geojson/districts")
def districts_geojson():
    """The district polygons, with `district_id` on every feature so the
    dashboard can join risk scores to shapes. Served from the API rather than
    duplicated into the frontend so there is one copy in the repo."""
    return FileResponse(DC.GEOJSON_PATH, media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/states")
def states():
    """Distinct state names, for the dashboard's filter dropdown."""
    return {"states": sorted(STATE.districts["state"].unique().tolist())}


@app.get("/health")
def health():
    return {"status": "ok" if STATE.loaded else "loading",
            "districts": STATE.n_districts if STATE.loaded else None}


@app.get("/heatmap")
def heatmap(window: str = Query("current", description="'current', an ISO timestamp, or a window index"),
            state: str | None = Query(None, description="narrow to one state (can never widen a role's scope)"),
            fraud_category: str | None = Query(None, description="keep districts holding money from this fraud type"),
            min_risk: float = Query(0.0, ge=0.0, le=1.0),
            role: str = q_role(), state_name: str | None = q_state_name(),
            bank: str | None = q_bank()):
    """Per-district risk for one 6-hour window, joinable to the district
    GeoJSON on `district_id`.

    Scoped by role: STATE gets only its own state's districts; BANK gets only
    its own footprint (the same districts /bank/exposure reports) and no rank or
    chain counts, which are crime intelligence. I4C, or no role, gets everything.
    """
    w = _resolve(window)
    role = _check_role(role, state_name, bank)
    rows = STATE.window_rows(w)
    out = pd.DataFrame({
        "district_id": rows["district_id"].to_numpy(),
        "risk": rows["risk"].to_numpy().round(4),
        "rank": rows["rank"].to_numpy(),
        "active_chains": rows["n_active_chains_here"].to_numpy().astype(int),
    })
    out["name"] = out["district_id"].map(STATE.district_name)
    out["state"] = out["district_id"].map(STATE.district_state)

    allowed = A.allowed_district_ids(STATE, w, role, state_name, bank)
    if allowed is not None:
        out = out[out["district_id"].isin(allowed)]

    if state:
        if state.lower() not in {x.lower() for x in STATE.districts["state"]}:
            raise HTTPException(404, f"no districts in state '{state}'")
        if role == "STATE" and state.lower() != state_name.lower():
            raise HTTPException(403, f"state '{state}' is outside your jurisdiction ({state_name})")
        out = out[out["state"].str.lower() == state.lower()]
    if fraud_category:
        keep = STATE.districts_with_category(w, fraud_category)
        out = out[out["district_id"].isin(keep)]
    out = out[out["risk"] >= min_risk].sort_values("rank")
    if role == "BANK":
        out = out.drop(columns=["rank", "active_chains"])
    return {
        **_window_meta(w),
        "role": role,
        "n_districts": len(out),
        "risk_max": float(out["risk"].max()) if len(out) else 0.0,
        "districts": out.to_dict("records"),
    }


@app.get("/alerts")
def alerts(window: str = Query("current"),
           threshold: float = Query(0.8, ge=0.0, le=1.0),
           limit: int = Query(50, ge=1, le=724),
           state: str | None = Query(None),
           role: str = q_role(), state_name: str | None = q_state_name(),
           bank: str | None = q_bank()):
    """Districts whose risk for this window crosses `threshold`, each with the
    top-3 contributing features as reason codes and a recommended action.

    Alerts are crime intelligence: a bank role is refused, a State LEA sees only
    its own state's."""
    w = _resolve(window)
    role = _check_role(role, state_name, bank)
    if role == "BANK":
        raise HTTPException(403, BANK_DENIED)
    rows = STATE.window_rows(w).reset_index(drop=True)
    contrib = STATE.contributions(w)

    allowed = A.allowed_district_ids(STATE, w, role, state_name, bank)
    keep = rows["risk"] >= threshold
    if allowed is not None:
        keep &= rows["district_id"].isin(allowed)
    if state:   # this filter was declared but never applied
        keep &= rows["district_id"].map(STATE.district_state).str.lower() == state.lower()
    sel = rows.index[keep].tolist()
    sel.sort(key=lambda i: -rows.at[i, "risk_raw"])
    sel = sel[:limit]

    items = []
    for i in sel:
        row = rows.loc[i]
        d = int(row["district_id"])
        codes = R.reason_codes(contrib[i], row, STATE.features)
        items.append({
            "district_id": d,
            "name": STATE.district_name[d],
            "state": STATE.district_state[d],
            "risk": round(float(row["risk"]), 4),
            "rank": int(row["rank"]),
            "money_in_flight": float(row["money_in_flight_here"]),
            "money_in_flight_display": R.rupees(row["money_in_flight_here"]),
            "active_chains": int(row["n_active_chains_here"]),
            "reason_codes": codes,
            "recommended_action": R.recommended_action(row, codes, STATE),
        })
    return {**_window_meta(w), "threshold": threshold, "n_alerts": len(items), "alerts": items}


@app.get("/districts/{district_id}")
def district_detail(district_id: int, window: str = Query("current"), history_days: int = Query(30, ge=1, le=30),
                    role: str = q_role(), state_name: str | None = q_state_name(),
                    bank: str | None = q_bank()):
    """Drill-down for one district: current score, risk history for a
    sparkline, recent complaints and withdrawals, and the chains whose money
    is sitting here right now."""
    if district_id not in STATE.district_name:
        raise HTTPException(404, f"district {district_id} not found")
    role = _check_role(role, state_name, bank)
    _deny_out_of_scope(role, district_id, state_name)   # drill-downs carry reason codes and case data
    w = _resolve(window)
    rows = STATE.window_rows(w).reset_index(drop=True)
    # rows are in district_id order, so position == district_id; assert rather than assume
    pos = int(rows.index[rows["district_id"] == district_id][0])
    row = rows.loc[pos]                      # keeps district_id, which the action text needs
    codes = R.reason_codes(STATE.contributions(w)[pos], row, STATE.features)

    # risk history (sparkline). Points before the test start come from the
    # calibration period and are flagged, so nothing is silently in-sample.
    per_day = 24 // FC.WINDOW_HOURS
    first = max(w - history_days * per_day, int(STATE.df["window_idx"].min()))
    hist = STATE.df[(STATE.df["district_id"] == district_id)
                    & (STATE.df["window_idx"] >= first) & (STATE.df["window_idx"] <= w)]
    history = [{"window_start": STATE.window_start(r.window_idx).isoformat(),
                "risk": round(float(r.risk), 4),
                "actual_withdrawals": int(r.y_count),
                "is_out_of_sample": bool(r.window_idx >= STATE.test_start_window)}
               for r in hist.itertuples()]

    # recent real events, strictly before the window start (same rule as features)
    t = w * FC.WINDOW_HOURS
    since = STATE.window_start(w) - pd.Timedelta(days=7)
    conn = sqlite3.connect(DC.DB_PATH)
    recent_wd = pd.read_sql(
        "SELECT withdrawal_id, complaint_id, atm_id, amount, timestamp FROM withdrawals "
        "WHERE district_id = ? AND timestamp < ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 20",
        conn, params=(district_id, STATE.window_start(w).strftime("%Y-%m-%d %H:%M:%S"),
                      since.strftime("%Y-%m-%d %H:%M:%S")))
    recent_cm = pd.read_sql(
        "SELECT complaint_id, fraud_category, amount, reported_at FROM complaints "
        "WHERE victim_district = ? AND reported_at < ? AND reported_at >= ? ORDER BY reported_at DESC LIMIT 20",
        conn, params=(district_id, STATE.window_start(w).strftime("%Y-%m-%d %H:%M:%S"),
                      since.strftime("%Y-%m-%d %H:%M:%S")))
    conn.close()

    # live chains whose money is parked here
    held = STATE.active_holdings(w, district_id)
    chains = (held.groupby("complaint_id")
                  .agg(amount_held=("amount", "sum"), age_hours=("age_hours", "min"),
                       max_hop=("hop_number", "max"), n_accounts=("account_id", "nunique"))
                  .sort_values("amount_held", ascending=False).head(20).reset_index())
    chain_list = []
    for c in chains.itertuples():
        cm = STATE.complaints.loc[c.complaint_id]
        chain_list.append({
            "complaint_id": int(c.complaint_id),
            "fraud_category": cm["fraud_category"],
            "original_amount": float(cm["amount"]),
            "amount_held_here": float(c.amount_held),
            "amount_held_display": R.rupees(c.amount_held),
            "age_hours": round(float(c.age_hours), 1),
            "hop": int(c.max_hop),
            "n_accounts_here": int(c.n_accounts),
        })

    atms = STATE.atms_by_district.get(district_id)
    return {
        **_window_meta(w),
        "district_id": district_id,
        "name": STATE.district_name[district_id],
        "state": STATE.district_state[district_id],
        "is_hotspot": int(row["is_hotspot"]),
        "risk": round(float(row["risk"]), 4),
        "rank": int(row["rank"]),
        "reason_codes": codes,
        "recommended_action": R.recommended_action(row, codes, STATE),
        "live_chains": {
            "n_chains": int(row["n_active_chains_here"]),
            "n_accounts": int(row["n_active_accounts_here"]),
            "money_in_flight": float(row["money_in_flight_here"]),
            "money_in_flight_display": R.rupees(row["money_in_flight_here"]),
            "chains": chain_list,
        },
        "risk_history": history,
        "recent_withdrawals": recent_wd.to_dict("records"),
        "recent_complaints": recent_cm.to_dict("records"),
        "atms": {"count": int(STATE.n_atms.get(district_id, 0)),
                 "banks": (atms["bank"].value_counts().to_dict() if atms is not None else {})},
    }


# ---------------------------------------------------------------------------
# Phase 6: roles, alert feed, dispatch, intelligence report
# ---------------------------------------------------------------------------
def _check_role(role, state_name, bank):
    role = (role or "I4C").upper()
    if role not in A.ROLES:
        raise HTTPException(400, f"unknown role '{role}'; expected one of {A.ROLES}")
    if role == "STATE" and not state_name:
        raise HTTPException(400, "role STATE requires a `state_name` (the jurisdiction)")
    if role == "BANK" and not bank:
        raise HTTPException(400, "role BANK requires a `bank`")
    if state_name and state_name not in set(STATE.districts["state"]):
        raise HTTPException(404, f"unknown state '{state_name}'")
    if bank and bank not in STATE.banks:
        raise HTTPException(404, f"unknown bank '{bank}'")
    return role


@app.get("/roles")
def roles():
    """The mock roles a demo can switch between, and why the split exists."""
    return {
        "roles": [
            {"id": "I4C", "label": "I4C Admin",
             "scope": "All 724 districts, all alerts, national statistics."},
            {"id": "STATE", "label": "State LEA",
             "scope": "Own state's districts and alerts only, plus a "
                      "cross-jurisdiction referral inbox.",
             "options": sorted(STATE.districts["state"].unique().tolist())},
            {"id": "BANK", "label": "Bank / FI",
             "scope": "Own ATMs and own accounts only. No crime intelligence.",
             "options": STATE.banks},
        ],
        "segregation_note": A.SEGREGATION_NOTE,
    }


@app.get("/feed")
def feed(role: str = Query("I4C"), state_name: str | None = Query(None),
         bank: str | None = Query(None), status: str | None = Query(None),
         limit: int = Query(200, ge=1, le=1000)):
    """The notification feed, scoped to the role. Newest first."""
    role = _check_role(role, state_name, bank)
    items = A.STORE.visible(role, state_name)
    if status:
        if status not in A.STATUSES:
            raise HTTPException(400, f"unknown status '{status}'")
        items = [a for a in items if a.status == status]
    items = sorted(items, key=lambda a: a.alert_id, reverse=True)[:limit]
    return {
        "role": role, "state_name": state_name, "bank": bank,
        "counts": A.STORE.counts(role, state_name),
        "alerts": [a.to_dict() for a in items],
        "note": ("Alerts are crime intelligence and are not exposed to bank roles."
                 if role == "BANK" else None),
    }


@app.post("/feed/{alert_id}/status")
def set_alert_status(alert_id: int, status: str = Query(...)):
    """Acknowledge or dismiss an alert."""
    if status not in A.STATUSES:
        raise HTTPException(400, f"status must be one of {A.STATUSES}")
    alert = A.STORE.get(alert_id)
    if not alert:
        raise HTTPException(404, f"alert {alert_id} not found")
    alert.status = status
    return alert.to_dict()


@app.post("/feed/{alert_id}/dispatch")
def dispatch_alert(alert_id: int, channel: str = Query("sms")):
    """Mock SMS/email dispatch: build the exact message an officer would get,
    log it, and return it. Nothing is actually sent anywhere."""
    alert = A.STORE.get(alert_id)
    if not alert:
        raise HTTPException(404, f"alert {alert_id} not found")
    if channel not in ("sms", "email"):
        raise HTTPException(400, "channel must be 'sms' or 'email'")
    atms = STATE.atms_by_district.get(alert.district_id)
    banks = atms["bank"].value_counts().head(3).index.tolist() if atms is not None else []
    if channel == "sms":
        to = f"SP Cyber Crime, {alert.district} (+91-XXXXX-XXXXX)"
        body = A.sms_for_alert(alert)
    else:
        to = f"sp-cyber.{alert.district.lower().replace(' ', '')}@{alert.state.lower().replace(' ', '')}.gov.in"
        body = A.email_for_alert(alert, int(STATE.n_atms.get(alert.district_id, 0)), banks)
    record = {"channel": channel, "to": to, "body": body,
              "sent_at": pd.Timestamp.now().isoformat(timespec="seconds"),
              "delivered": False, "note": "MOCK - logged only, nothing transmitted"}
    alert.dispatched.append(record)
    print(f"[dispatch:{channel}] -> {to}\n{body}\n")
    return record


@app.get("/feed/{alert_id}/report")
def intelligence_report(alert_id: int):
    """Everything the printable Intelligence Report needs, in one call."""
    alert = A.STORE.get(alert_id)
    if not alert:
        raise HTTPException(404, f"alert {alert_id} not found")
    w, d = alert.window_idx, alert.district_id

    held = STATE.active_holdings(w, d)
    chains = []
    if not held.empty:
        g = (held.groupby("complaint_id")
                 .agg(amount_held=("amount", "sum"), age_hours=("age_hours", "min"),
                      hop=("hop_number", "max"), n_accounts=("account_id", "nunique"))
                 .sort_values("amount_held", ascending=False).head(25).reset_index())
        for c in g.itertuples():
            cm = STATE.complaints.loc[c.complaint_id]
            chains.append({
                "complaint_id": int(c.complaint_id),
                "fraud_category": cm["fraud_category"],
                "original_amount": float(cm["amount"]),
                "amount_held": float(c.amount_held),
                "amount_held_display": R.rupees(c.amount_held),
                "age_hours": round(float(c.age_hours), 1),
                "hop": int(c.hop), "n_accounts": int(c.n_accounts),
                "victim_district": STATE.district_name[int(cm["victim_district"])],
                "victim_state": STATE.district_state[int(cm["victim_district"])],
            })

    atms = STATE.atms_by_district.get(d)
    atm_list = ([] if atms is None else
                [{"atm_id": int(r.atm_id), "bank": r.bank,
                  "lat": round(float(r.lat), 4), "lon": round(float(r.lon), 4)}
                 for r in atms.head(20).itertuples()])
    return {
        "alert": alert.to_dict(),
        "reference": f"ALERT-{alert.alert_id:05d}",
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "model_version": "FraudLens v0.1 - LightGBM, isotonic-calibrated "
                         f"({len(STATE.features)} features)",
        "active_chains": chains,
        "atms": atm_list,
        "atm_count": int(STATE.n_atms.get(d, 0)),
        "data_notice": "SYNTHETIC DATA - generated for demonstration (SIH26184). "
                       "Not derived from real complaints, accounts or transactions.",
    }


@app.get("/cross-jurisdiction")
def cross_jurisdiction(state_name: str = Query(..., description="the requesting state"),
                       window: str = Query("current"),
                       fraud_category: str | None = Query(None),
                       limit: int = Query(60, ge=1, le=200)):
    """Money from complaints filed in this state that is now in flight toward a
    district in a DIFFERENT state - the coordination gap the project targets."""
    w = _resolve(window)
    if state_name not in set(STATE.districts["state"]):
        raise HTTPException(404, f"unknown state '{state_name}'")
    items = A.cross_jurisdiction(STATE, w, state_name, limit, fraud_category)
    return {
        **_window_meta(w), "state_name": state_name,
        "fraud_category": fraud_category,
        "n_referrals": len(items),
        "total_amount": sum(i["amount_held"] for i in items),
        "total_amount_display": R.rupees(sum(i["amount_held"] for i in items)),
        "referrals": items,
    }


@app.get("/bank/exposure")
def bank_exposure(bank: str = Query(...), window: str = Query("current"),
                  state_name: str | None = Query(None, description="narrow to one state"),
                  min_risk: float = Query(0.5, ge=0.0, le=1.0)):
    """A bank's own exposure. No crime intelligence: no reason codes, no
    complaint details, no district rankings.

    `state_name` scopes ATMs, accounts and the district footprint together."""
    w = _resolve(window)
    if bank not in STATE.banks:
        raise HTTPException(404, f"unknown bank '{bank}'")
    if state_name and state_name not in set(STATE.districts["state"]):
        raise HTTPException(404, f"unknown state '{state_name}'")
    return {**_window_meta(w),
            **A.bank_exposure(STATE, w, bank, min_risk, state_name=state_name),
            "segregation_note": A.SEGREGATION_NOTE}


@app.get("/simulate/state")
def simulate_state():
    """Where the demo clock is, and how far it can still run."""
    return {
        "clock": _window_meta(STATE.clock),
        "test_period_start": STATE.test_start.isoformat(),
        "last_available": STATE.window_start(STATE.last_window).isoformat(),
        "windows_remaining": int(STATE.last_window - STATE.clock),
        "note": "The clock starts at the first window of the held-out test period, "
                "so every score is an out-of-sample prediction.",
    }


@app.post("/simulate/advance")
def simulate_advance(steps: int = Query(1, ge=1, le=40),
                     threshold: float = Query(0.8, ge=0.0, le=1.0),
                     role: str = q_role(), state_name: str | None = q_state_name(),
                     bank: str | None = q_bank()):
    """Advance the clock by `steps` 6-hour windows and rescore.

    Also reports how the PREVIOUS window's predictions actually turned out,
    which is what makes the live demo convincing.
    """
    role = _check_role(role, state_name, bank)
    if STATE.clock >= STATE.last_window:
        raise HTTPException(400, "clock is already at the end of the simulated data")
    previous = STATE.clock
    STATE.clock = min(STATE.clock + steps, STATE.last_window)
    STATE.warm(STATE.clock)          # absorb the SHAP cost here, not in /alerts
    # districts crossing the threshold in the NEW window become alert records
    new_alerts = A.STORE.create_for_window(STATE, STATE.clock, threshold)

    prev_rows = STATE.window_rows(previous)
    flagged = prev_rows[prev_rows["risk"] >= threshold]
    hits = int((flagged["y_count"] > 0).sum())
    rows = STATE.window_rows(STATE.clock)

    # The dashboard calls this under every role, so the district-level fields
    # are scoped exactly like /feed and /heatmap. A bank gets none of them.
    allowed = A.allowed_district_ids(STATE, STATE.clock, role, state_name, bank) if role == "STATE" else None
    scoped_rows = rows if allowed is None else rows[rows["district_id"].isin(allowed)]
    top = scoped_rows.nlargest(5, "risk_raw")
    shown_alerts = [a for a in new_alerts if role == "I4C" or (role == "STATE" and a.state == state_name)]
    return {
        "clock": _window_meta(STATE.clock),
        "advanced_by": int(STATE.clock - previous),
        # National model-accuracy telemetry: counts only, no district identities.
        # Withheld from banks - a national cash-out count is crime intelligence.
        "previous_window": None if role == "BANK" else {
            **_window_meta(previous),
            "n_flagged": len(flagged),
            "n_flagged_correct": hits,
            "precision": round(hits / len(flagged), 4) if len(flagged) else None,
            "actual_withdrawal_districts": int((prev_rows["y_count"] > 0).sum()),
        },
        "new_alerts": [a.to_dict() for a in shown_alerts],
        "now": {
            "n_above_threshold": (None if role == "BANK"
                                  else int((scoped_rows["risk"] >= threshold).sum())),
            "top_districts": [] if role == "BANK" else [
                {"district_id": int(r.district_id),
                 "name": STATE.district_name[int(r.district_id)],
                 "state": STATE.district_state[int(r.district_id)],
                 "risk": round(float(r.risk), 4)} for r in top.itertuples()],
        },
    }


@app.post("/simulate/reset")
def simulate_reset():
    """Put the clock back to the start of the test period."""
    STATE.clock = STATE.test_start_window
    STATE.warm(STATE.clock)
    A.STORE.alerts.clear()
    return {"clock": _window_meta(STATE.clock)}
