# Phase 7 notes - polish, cold start, release

## What was built

- **README.md** rewritten as the primary deliverable: pitch, screenshots,
  mermaid architecture diagram plus prose walkthrough of all eight phases,
  headline metrics with honest framing, exact run commands, a prominent
  Limitations section, and future work.
- **docs/architecture.png** - the mermaid diagram exported at 2x for slides.
- **docs/demo_script.md** - 3-minute walkthrough with click order, spoken lines,
  timings, likely questions, and a recovery section.
- **Cold-start verification** from a fresh clone.
- Tag `v0.1-sih-prototype`.

## Cold-start verification

A fresh `git clone` into a temp directory, following the README literally.
Everything a stranger needs is either committed or regenerated:

| step | time | result |
|---|---|---|
| `pip install -r requirements.txt` | ~40 s | all deps resolve on Python 3.10 |
| `python -m datagen.generate` | 43.5 s | identical row counts to the working repo |
| `python -m features.build` | 8.1 s | 1,057,040 rows, 4.94% positive |
| `python -m features.test_leakage` | ~20 s | LEAKAGE TEST PASSED |
| `python -m model.train` | 22 s | valid PR-AUC 0.7622 |
| `python -m model.evaluate` | ~5 s | **byte-identical `docs/metrics.md`** |
| `uvicorn api.main:app --port 8000` | 9 s to ready | all endpoints serve |
| `npm install && npm run dev` | ~5 s | dashboard loads, no browser errors |

The byte-identical `metrics.md` is the claim worth making: one seed in
`datagen/config.py` drives the whole world, so anyone can reproduce every number
in the report rather than taking it on trust.

**What a fresh clone contains:** source, the cleaned district GeoJSON (955 KB)
and the Census-2011 CSV (440 KB). **What it does not:** the 195 MB database, the
25 MB feature table, and the model artifacts, all gitignored and rebuilt in
about 75 seconds total.

The diagram was validated by rendering it in a real browser rather than assumed
to parse.

## Two things the cold start changed in the README

1. **Node install guidance.** `apt install nodejs` on Ubuntu 22.04 hung for over
   ten minutes on a third-party repository during Phase 5. The README now gives
   the official-tarball route, which needs no root and no repository, plus the
   `PATH` export the dashboard needs.
2. **Start order is explicit.** The Vite dev server proxies `/api` to port 8000,
   so the README states the backend must be running first and names the port.

## Known limitations of the release itself

- No CI. The leakage test and a cold start are the regression suite, and both
  are run by hand.
- Model artifacts are gitignored, so a clone must train before serving. That is
  75 seconds, but it does mean the repo is not runnable straight from disk.
- The demo script assumes the seeded world. Changing `SEED` changes which
  districts appear, and the script names Deoghar and Jharkhand explicitly.

## Judge Q&As

**Q: Can we run this ourselves, or is it a laptop demo?**
A: Clone it and follow the README. We verified from a fresh clone that the whole
pipeline rebuilds and produces a byte-identical metrics file, so every number in
the report is reproducible rather than asserted. It needs Python 3.10, Node 20
and about 75 seconds of compute. No cloud, no keys, no external services.

**Q: What would you do first with another week?**
A: Persist the alerts with a real audit trail, because that is the one gap that
is a compliance problem rather than a feature gap. After that, the streaming
path, since replaying precomputed windows is the biggest gap between the demo
and something operational.

**Q: What is the weakest claim in your submission?**
A: The drift result. It rests on six districts that became hotspots only during
the test months. The direction is consistent with the design and with the K=50
ablation, but six districts is not a sample, and we would not defend the exact
percentage. The strongest claim is the anti-leakage proof, because it is a test
anyone can run rather than a number we are asking you to believe.
