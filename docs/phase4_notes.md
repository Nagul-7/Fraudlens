# Phase 4 notes - prediction API

## What was built

```bash
source venv/bin/activate
uvicorn api.main:app --reload        # http://127.0.0.1:8000
# interactive docs: http://127.0.0.1:8000/docs
```

- `api/state.py`   - loads the model, calibrator and feature table once at startup;
  precomputes every score; holds the demo clock and the live-chain holdings
- `api/reasons.py` - turns LightGBM feature contributions into readable reason
  codes and a recommended action
- `api/main.py`    - the FastAPI app, CORS enabled for the Phase 5 dashboard

Startup takes about 10 s: score 263,536 district-windows, then build 365,659
live-chain holdings.

## Two guarantees built into the API

**Everything served is out-of-sample.** The demo clock starts at
2025-11-01T00:00, the first window of the held-out test period, and
`resolve_window` returns HTTP 400 for any earlier window:

```
GET /heatmap?window=2025-06-01T00:00:00
400 {"detail":"window 2025-06-01 00:00:00 is before the test period starts
     (2025-11-01T00:00:00). The API only serves out-of-sample windows."}
```

The one exception is the drill-down sparkline, which may reach back up to 30
days into the calibration period so the chart is never empty. Every point
carries an `is_out_of_sample` flag rather than hiding the distinction.

**Scores are calibrated probabilities.** `risk` is the isotonic-calibrated
probability from Phase 3, so `threshold=0.8` genuinely means "about 80% of
these fire". Ranking uses the raw score underneath, because isotonic
regression creates ties that would otherwise scramble the top-K ordering.

## Endpoints

| endpoint | purpose |
|---|---|
| `GET /heatmap?window=&state=&min_risk=` | per-district risk + rank for one window, joins to the GeoJSON on `district_id` |
| `GET /alerts?window=&threshold=&limit=&state=` | ranked alerts with reason codes and recommended actions |
| `GET /districts/{id}?window=&history_days=` | drill-down: score, sparkline, recent events, live chains |
| `GET /simulate/state` | where the clock is |
| `POST /simulate/advance?steps=&threshold=` | advance the clock and rescore |
| `POST /simulate/reset` | back to the start of the test period |
| `GET /health`, `GET /` | liveness and index |

`window` accepts `current` (default), an ISO timestamp, or a raw window index.

### Response times (measured)

| endpoint | time |
|---|---|
| `/heatmap` | 17-32 ms |
| `/alerts` | 8-14 ms |
| `/districts/{id}` (current window) | 40-57 ms |
| `POST /simulate/advance` | ~780 ms |

`pred_contrib` (SHAP) costs ~760 ms for 724 rows, versus 4 ms for a plain
prediction, so contributions are cached per window and the cache is warmed at
startup and on every clock change. The advance call deliberately absorbs that
cost so the read endpoints the dashboard polls stay in the tens of milliseconds.
A drill-down on some other, uncached window pays the 760 ms once.

## Sample responses

### `GET /alerts?threshold=0.8` (trimmed to one alert)

```json
{
  "window_start": "2025-11-01T00:00:00",
  "is_out_of_sample": true,
  "threshold": 0.8,
  "n_alerts": 10,
  "alerts": [{
    "district_id": 304, "name": "Kargil", "state": "Ladakh",
    "risk": 0.8878, "rank": 1,
    "money_in_flight_display": "Rs 12.0L", "active_chains": 23,
    "reason_codes": [
      {"feature": "hrs_since_wd_here", "value": 0.122, "contribution": 3.8518,
       "reason": "last cash-out here was 7 min ago - corridor still hot"},
      {"feature": "n_active_accounts_here", "value": 25.0, "contribution": 2.3713,
       "reason": "25 mule account(s) here currently holding funds"},
      {"feature": "money_in_flight_here", "value": 1195261.4, "contribution": 0.5628,
       "reason": "Rs 12.0L in flight across 23 active chain(s) here"}
    ],
    "recommended_action": [
      "Deploy a field team to the district's main ATM clusters this window",
      "Alert Bank of Baroda, HDFC, SBI to flag 7 ATMs here and hold withdrawals linked to the 23 chain(s) carrying Rs 12.0L",
      "Pre-file freeze requests via CFCFRMS for the holding accounts listed in the drill-down"
    ]
  }]
}
```

Every `reason` is rendered from the model's own `contribution` for that row and
that row's real feature value. Nothing is hardcoded per district. Change the
model and the reasons change with it.

### `GET /districts/246` (Hazaribagh, window 2025-12-15T06:00)

```json
{
  "district_id": 246, "name": "Hazaribagh", "state": "Jharkhand",
  "risk": 0.7485, "rank": 19, "is_hotspot": 0,
  "reason_codes": [
    {"reason": "27 mule account(s) here currently holding funds"},
    {"reason": "Rs 4.9L in flight across 20 active chain(s) here"},
    {"reason": "youngest chain here is 10h old - near the ~14h cash-out median"}
  ],
  "live_chains": {
    "n_chains": 20, "n_accounts": 27, "money_in_flight_display": "Rs 4.9L",
    "chains": [
      {"complaint_id": 96941, "fraud_category": "investment",
       "amount_held_display": "Rs 1.1L", "age_hours": 56.5, "hop": 6, "n_accounts_here": 1},
      {"complaint_id": 97368, "fraud_category": "card",
       "amount_held_display": "Rs 1.0L", "age_hours": 15.7, "hop": 5, "n_accounts_here": 1}
    ]
  },
  "risk_history": [ 121 points, each with risk, actual_withdrawals, is_out_of_sample ],
  "recent_withdrawals": [20 most recent, all strictly before the window start],
  "recent_complaints": [...],
  "atms": {"count": 2, "banks": {"Canara": 1, "Bank of Baroda": 1}}
}
```

Note Hazaribagh has `is_hotspot: 0` - it was never on the static watchlist, and
is ranked 19th purely on live evidence. That is the cold-start case from Phase 3
showing up in the product.

### `POST /simulate/advance` - the live demo

Each advance also grades the window that just closed, which is what makes the
demo convincing:

```
clock -> 2025-11-01T06:00  previous window flagged 10, 9 had a real cash-out (precision 0.90)
clock -> 2025-11-01T12:00  previous window flagged  9, 9 had a real cash-out (precision 1.00)
clock -> 2025-11-01T18:00  previous window flagged 10, 10 had a real cash-out (precision 1.00)
```

## Key decisions

- **Precompute scores, compute explanations on demand.** Scoring 263k rows once
  costs 4 s at startup; computing SHAP for all of them would cost ~4 minutes.
  Caching per window gets both.
- **The API refuses to serve in-sample windows.** It would have been easy to let
  the clock roam the whole year and quietly show training-period scores. The 400
  is deliberate.
- **Reason codes read like an officer wrote them, not a model.** "last cash-out
  here was 7 min ago" rather than "hrs_since_wd_here = 0.122". Both are in the
  payload, so the dashboard can show either.
- **The drill-down reuses the Phase 2 holdings function**, so the chains listed in
  the panel are exactly the ones the model's features counted. No second
  definition of "active chain" to drift out of sync.

## Known limitations

- The clock is a pointer into precomputed data, not a live stream. Real
  deployment would recompute features on arriving CFCFRMS events.
- `recommended_action` is rule-based on top of the model's numbers (thresholds on
  risk and money in flight). It is presentation, not a learned policy.
- No authentication. Phase 6 adds mock role-based views; real auth is out of scope.
- Contributions are in log-odds space, so they rank reasons correctly but do not
  sum to the calibrated probability.

## Judge Q&As

**Q: The dashboard is showing predictions. How do I know they are not just the
model recalling what it memorised in training?**
A: The API physically cannot serve a training window. The clock starts at
2025-11-01, the first window of the held-out test period, and any request for an
earlier window returns HTTP 400. On top of that, each `/simulate/advance` grades
the window that just closed against ground truth, so you watch the accuracy
accumulate live rather than taking our word for it.

**Q: Where do the reason codes come from? Are they written by hand?**
A: They come from LightGBM's `pred_contrib`, which gives the per-feature
contribution to that specific district's score. We take the three features that
pushed the score up most and render each with the row's actual value. The
sentence templates are written by hand, but which features appear, in what order,
for which district, is entirely the model. The raw feature name, value and
contribution ship in the same payload so a technical reviewer can audit the text.

**Q: A 780 ms response is slow. Is this production-ready?**
A: Only the clock advance takes that long, and it is deliberate. Computing SHAP
explanations costs about 760 ms for 724 districts, versus 4 ms to score them. We
pay that once when the clock moves, and cache it, so the endpoints a dashboard
polls answer in 8-57 ms. In production the same trick applies per arriving batch.
What is genuinely not production-ready is the absence of auth, and that the clock
replays precomputed windows instead of consuming a live feed.
