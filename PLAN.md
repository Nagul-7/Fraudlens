# FraudLens — Predictive Cash Withdrawal Intelligence (SIH26184)

**Problem:** Predict likely cyber-fraud cash withdrawal locations in advance from cybercrime complaint data, so LEAs/banks can intervene proactively (deploy teams, pre-alert ATMs, freeze faster via CFCFRMS).

**Honest framing (never violate):** All data is SYNTHETIC. All metrics are measured on the synthetic world and prove the pipeline works — they are NOT claims about real-world accuracy. The system is designed to be "data-ready" for real CFCFRMS feeds.

---

## Operating rules for Claude Code

1. Read this file at the start of every session.
2. Keep it simple: prefer boring, readable code over clever code. The builder is a beginner who must be able to explain every module to judges.
3. After completing each phase, write a short `docs/phaseN_notes.md`: what was built, key decisions, how to run it, 3 likely judge questions + answers.
4. Every phase ends with: code runs end-to-end, committed and pushed.
5. Python 3.10+, single repo, no microservices, no Docker (unless trivial), SQLite for storage, no cloud dependencies. Everything must run on one laptop.

## Tech stack (fixed — do not bikeshed)

- Data/ML: pandas, numpy, networkx, LightGBM, scikit-learn, matplotlib
- API: FastAPI + uvicorn
- Frontend: React (Vite) + Leaflet, district-level choropleth via India districts GeoJSON
- Storage: SQLite (`data/fraudlens.db`) + parquet files for the training table

## Repo structure

```
fraudlens/
  PLAN.md
  README.md
  data/               # generated data (gitignore large files)
  datagen/            # Phase 1: synthetic data engine
  features/           # Phase 2: feature pipeline
  model/              # Phase 3: training + evaluation
  api/                # Phase 4: FastAPI app
  dashboard/          # Phase 5-6: React frontend
  docs/               # phase notes, architecture diagram, demo script
```

---

## Phase 0 — Setup (~30 min)

- Init repo, structure above, .gitignore (data files, node_modules, .env, tokens), venv, requirements.txt, README stub with one-paragraph pitch.
- **Done when:** `pip install -r requirements.txt` works, empty modules importable, first commit pushed.

## Phase 1 — Synthetic data engine (~2.5–3 hrs) — THE FOUNDATION

Generate 12 months of realistic fraud history. Tables (SQLite):

- `districts`: district_id, name, state, lat, lon, is_hotspot (flag ~25 known-style mule corridor districts), population_weight
- `atms`: atm_id, district_id, lat, lon, bank
- `accounts`: account_id, holder_type (victim | mule | clean), district_id, opened_date, kyc_quality (real | rented | forged)
- `complaints`: complaint_id, timestamp, victim_district, fraud_category (UPI, investment, digital_arrest, card, loan_app), amount, first_hop_account
- `transactions`: txn_id, complaint_id, from_account, to_account, amount, timestamp, hop_number
- `withdrawals`: withdrawal_id, complaint_id, atm_id, district_id, amount, timestamp — **ground truth events**

Fraud physics to encode (parameterized in one config file `datagen/config.py`):

1. ~200–400 complaints/day (scaled-down from real 8000/day), amounts log-normal.
2. Each complaint spawns a mule chain: 3–7 hops, splits (1 account fans out to 2–4), transfer delays minutes–hours.
3. Cash-out: 70% of chains end in ATM withdrawals, 2–48 hrs after the fraud, split into multiple withdrawals ≤ ₹50k (structuring).
4. Geography: withdrawals concentrate in hotspot districts (~65%), but hotspots slowly DRIFT over months (adversarial adaptation) and there is background noise everywhere.
5. Self-excitation: a withdrawal in district D raises withdrawal probability in D and neighbors for the next 3–7 days (gang works a corridor until burned), then cools.
6. Weekly/diurnal patterns: more cash-outs early morning / late evening, fewer on bank-holiday-style days.

- **Done when:** `python -m datagen.generate` builds the DB; a `datagen/validate.py` script outputs sanity plots (events over time, geographic distribution, hop histogram, time-to-cashout histogram) into `docs/`.

## Phase 2 — Feature pipeline (~1.5–2 hrs)

Unit of prediction: **(district, 6-hour window)** — will a fraud withdrawal occur? (binary label; also keep count label for later).

Features per (district, window):
- Rolling withdrawal counts: last 1d / 3d / 7d / 30d, with exponential decay version
- Rolling complaint counts by fraud category (same windows) — nationwide and in "linked" districts
- Self-excitation feature: time since last withdrawal in district and in neighboring districts
- Static: is_hotspot, ATM count, population_weight, distance to nearest active hotspot
- Mule-graph features (networkx on recent transactions): number of active chains whose latest hop is in an account of this district, average chain depth, fan-out
- Calendar: hour-block, day-of-week, is-weekend

- **Done when:** `python -m features.build` writes `data/train_table.parquet`; a notebook/script prints feature summary stats.

## Phase 3 — Model + evaluation (~1.5 hrs)

- LightGBM binary classifier. Temporal split: train months 1–10, test months 11–12. NEVER random split.
- Class imbalance: downsample negatives in train (keep test untouched); use scale_pos_weight if needed.
- Calibrate probabilities (isotonic or Platt via sklearn).
- Metrics on test: **hit-rate@top-K** (K = 25, 50, 100 district-windows) as headline; PR-AUC; baseline comparison vs "always predict yesterday's hotspots" naive model (must beat it).
- Outputs: `model/model.txt`, `docs/feature_importance.png`, `docs/metrics.md`.
- **Done when:** metrics reproducible via `python -m model.train && python -m model.evaluate`.

## Phase 4 — Prediction API (~1–1.5 hrs)

FastAPI (`api/main.py`):
- `GET /heatmap?window=next_6h` — risk score per district (GeoJSON-joinable)
- `GET /alerts?threshold=0.8` — ranked high-risk district-windows with reason codes (top contributing features)
- `GET /districts/{id}` — drill-down: recent events, risk history, active chains
- `POST /simulate/advance` — advances simulated clock by one window and re-scores (powers the live demo)
- **Done when:** `uvicorn api.main:app` serves all endpoints; documented in FastAPI /docs.

## Phase 5 — Risk heatmap dashboard (~2.5–3 hrs) — DEMO CENTERPIECE

React + Leaflet:
- India district choropleth colored by risk score (green→red), legend
- Time control: current window + "advance clock" button (calls /simulate/advance) so the demo shows risk evolving LIVE
- Filters: state, fraud category, risk threshold
- Click district → side panel: risk score, trend sparkline, recent complaints/withdrawals, active mule chains, "why" (top features)
- **Done when:** dashboard runs on `npm run dev`, talks to API, looks clean and professional (dark theme, official-dashboard feel).

## Phase 6 — Alerts + LEA interface (~1.5–2 hrs)

- Alert engine: when a district's next-window risk crosses threshold → create alert record (district, window, score, reasons, recommended action: "deploy team / notify banks X,Y / watch ATMs list")
- Notification feed panel in dashboard (bell icon, unread count); mock SMS/email by logging + toast
- Mock role-based views: I4C admin (all India), State LEA (own state only), Bank (own ATMs only) — simple role switcher is fine, real auth not needed
- Alert → printable "Intelligence Report" view (this is deliverable c)
- **Done when:** advancing the clock produces alerts that appear in the feed and open as reports.

## Phase 7 — Polish + demo (~1.5 hrs)

- Architecture diagram (mermaid in README + exported PNG)
- README: problem, architecture, how to run, metrics, LIMITATIONS section (synthetic data, what changes with real data), future work (ST-GNN, streaming, CFCFRMS integration)
- `docs/demo_script.md`: 2-minute demo flow; record screen capture
- Final push; tag `v0.1-sih-prototype`
- **Done when:** a stranger could clone, run, and understand the project from README alone.

---

## Learning checkpoints (for the builder, after each phase)

Explain back in your own words: (1) what this module does, (2) one key design decision and why, (3) answer the 3 judge questions in the phase notes. If you can't, re-read the phase notes before moving on.

## Judge-proof honesty lines (memorize)

- "Metrics are on synthetic data that encodes publicly documented fraud patterns; they validate the pipeline, not real-world performance."
- "Headline metric is hit-rate@top-K because police resources are limited — accuracy is meaningless at 99% negative class."
- "The system is designed so real CFCFRMS/portal feeds can replace the generator with zero changes downstream."
