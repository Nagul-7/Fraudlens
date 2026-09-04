# FraudLens - Predictive Cash Withdrawal Intelligence (SIH26184)

Predicts likely cyber-fraud cash withdrawal locations in advance from
cybercrime complaint data, so law enforcement agencies (LEAs) and banks can
intervene proactively - deploy teams, pre-alert ATMs, freeze faster via
CFCFRMS.

## Status

Work in progress, built phase by phase per `PLAN.md`.

- Phase 0 - project setup: done
- Phase 1 - synthetic data engine: done (see `docs/phase1_notes.md`)
- Phase 2 - feature pipeline with leakage test: done (see `docs/phase2_notes.md`)

## Important: this is a synthetic-data prototype

All data used by this project is **synthetically generated** (see
`datagen/`). All metrics reported anywhere in this repo are measured on
that synthetic world - they demonstrate that the pipeline works end to
end, and are **not** claims about real-world fraud prediction accuracy.
The system is designed to be "data-ready": a real CFCFRMS/portal feed can
replace the synthetic generator without changing anything downstream.

## Tech stack

- Data / ML: pandas, numpy, networkx, LightGBM, scikit-learn, matplotlib
- API: FastAPI + uvicorn
- Frontend: React (Vite) + Leaflet
- Storage: SQLite + parquet files, all local (no cloud dependencies)

## Repo structure

```
fraudlens/
  PLAN.md       # phase-by-phase build plan
  data/         # generated data (gitignored - rebuild with datagen)
  datagen/      # Phase 1: synthetic data engine
  features/     # Phase 2: feature pipeline
  model/        # Phase 3: training + evaluation
  api/          # Phase 4: FastAPI app
  dashboard/    # Phase 5-6: React frontend
  docs/         # phase notes, architecture diagram, demo script
```

## How to run

Setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Generate the synthetic world (12 months, ~300 complaints/day, real India
districts) and check it:

```bash
python -m datagen.generate    # ~45 s -> data/fraudlens.db
python -m datagen.validate    # physics checks + plots in docs/
```

All simulation parameters live in `datagen/config.py`, each with a comment on
what it models. One fixed seed makes every run identical.

Build the training table (one row per district x 6-hour window) and prove
no feature uses information from after its window starts:

```bash
python -m features.build          # ~10 s -> data/train_table.parquet
python -m features.test_leakage   # brute-force check, must print LEAKAGE TEST PASSED
```

Later phases will add training and serving commands here.

## Data sources

- District boundaries: public India districts GeoJSON curated by
  [udit-001/india-maps-data](https://github.com/udit-001/india-maps-data)
  (Census-2011 codes, later district splits included). Downloaded once by
  `datagen/geo.py`; a cleaned copy with our `district_id` is committed at
  `data/india_districts.geojson`.
- Everything else (accounts, complaints, transactions, withdrawals) is
  generated. No real personal or transaction data is used anywhere.

## Limitations

See `PLAN.md` for the full honesty framing. Short version: synthetic data,
synthetic metrics, prototype for a hackathon (Smart India Hackathon), not a
production fraud system.
