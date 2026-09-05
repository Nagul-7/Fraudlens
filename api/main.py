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

from datagen import config as DC
from features import config as FC
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
@app.get("/")
def root():
    return {
        "service": "FraudLens API",
        "data": "SYNTHETIC - see docs/phase1_notes.md",
        "clock": _window_meta(STATE.clock),
        "endpoints": ["/heatmap", "/alerts", "/districts/{district_id}",
                      "/simulate/state", "/simulate/advance", "/docs"],
    }


@app.get("/health")
def health():
    return {"status": "ok" if STATE.loaded else "loading",
            "districts": STATE.n_districts if STATE.loaded else None}


@app.get("/heatmap")
def heatmap(window: str = Query("current", description="'current', an ISO timestamp, or a window index"),
            state: str | None = Query(None, description="filter to one state"),
            min_risk: float = Query(0.0, ge=0.0, le=1.0)):
    """Per-district risk for one 6-hour window, joinable to the district
    GeoJSON on `district_id`."""
    w = _resolve(window)
    rows = STATE.window_rows(w)
    out = pd.DataFrame({
        "district_id": rows["district_id"].to_numpy(),
        "risk": rows["risk"].to_numpy().round(4),
        "rank": rows["rank"].to_numpy(),
    })
    out["name"] = out["district_id"].map(STATE.district_name)
    out["state"] = out["district_id"].map(STATE.district_state)
    if state:
        out = out[out["state"].str.lower() == state.lower()]
        if out.empty:
            raise HTTPException(404, f"no districts in state '{state}'")
    out = out[out["risk"] >= min_risk].sort_values("rank")
    return {
        **_window_meta(w),
        "n_districts": len(out),
        "risk_max": float(out["risk"].max()) if len(out) else 0.0,
        "districts": out.to_dict("records"),
    }


@app.get("/alerts")
def alerts(window: str = Query("current"),
           threshold: float = Query(0.8, ge=0.0, le=1.0),
           limit: int = Query(50, ge=1, le=724),
           state: str | None = Query(None)):
    """Districts whose risk for this window crosses `threshold`, each with the
    top-3 contributing features as reason codes and a recommended action."""
    w = _resolve(window)
    rows = STATE.window_rows(w).reset_index(drop=True)
    contrib = STATE.contributions(w)

    sel = rows.index[rows["risk"] >= threshold].tolist()
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
def district_detail(district_id: int, window: str = Query("current"), history_days: int = Query(30, ge=1, le=30)):
    """Drill-down for one district: current score, risk history for a
    sparkline, recent complaints and withdrawals, and the chains whose money
    is sitting here right now."""
    if district_id not in STATE.district_name:
        raise HTTPException(404, f"district {district_id} not found")
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
                     threshold: float = Query(0.8, ge=0.0, le=1.0)):
    """Advance the clock by `steps` 6-hour windows and rescore.

    Also reports how the PREVIOUS window's predictions actually turned out,
    which is what makes the live demo convincing.
    """
    if STATE.clock >= STATE.last_window:
        raise HTTPException(400, "clock is already at the end of the simulated data")
    previous = STATE.clock
    STATE.clock = min(STATE.clock + steps, STATE.last_window)
    STATE.warm(STATE.clock)          # absorb the SHAP cost here, not in /alerts

    prev_rows = STATE.window_rows(previous)
    flagged = prev_rows[prev_rows["risk"] >= threshold]
    hits = int((flagged["y_count"] > 0).sum())
    rows = STATE.window_rows(STATE.clock)
    top = rows.nlargest(5, "risk_raw")
    return {
        "clock": _window_meta(STATE.clock),
        "advanced_by": int(STATE.clock - previous),
        "previous_window": {
            **_window_meta(previous),
            "n_flagged": len(flagged),
            "n_flagged_correct": hits,
            "precision": round(hits / len(flagged), 4) if len(flagged) else None,
            "actual_withdrawal_districts": int((prev_rows["y_count"] > 0).sum()),
        },
        "now": {
            "n_above_threshold": int((rows["risk"] >= threshold).sum()),
            "top_districts": [{"district_id": int(r.district_id),
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
    return {"clock": _window_meta(STATE.clock)}
