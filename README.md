# FraudLens - Predictive Cash Withdrawal Intelligence (SIH26184)

Predicts likely cyber-fraud cash withdrawal locations in advance from
cybercrime complaint data, so law enforcement agencies (LEAs) and banks can
intervene proactively - deploy teams, pre-alert ATMs, freeze faster via
CFCFRMS.

## Status

Work in progress, built phase by phase per `PLAN.md`. Currently: Phase 0
(project setup) complete.

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

Later phases will add generate / train / serve commands here as they are
built.

## Limitations

See `PLAN.md` for the full honesty framing. Short version: synthetic data,
synthetic metrics, prototype for a hackathon (Smart India Hackathon), not a
production fraud system.
