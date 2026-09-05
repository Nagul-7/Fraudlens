# Phase 3 notes - model + evaluation

## What was built

```bash
source venv/bin/activate
python -m model.train      # ~60 s CPU -> model/model.txt, model_no_chains.txt, calibrator.pkl
python -m model.evaluate   # ~15 s -> docs/metrics.md + 2 charts
```

- `model/config.py`   - split dates, LightGBM params, K values, paths
- `model/common.py`   - loading, the temporal split, and the top-K metric, shared so
  the model, both baselines, the ablation and the oracle are scored by identical code
- `model/train.py`    - trains the main model, fits the calibrator, trains the ablation
- `model/evaluate.py` - all test-set metrics, drift analysis, importance, ablation
- Outputs: `model/model.txt`, `model/model_no_chains.txt`, `model/calibrator.pkl`,
  `model/features.json`, `docs/metrics.md`, `docs/feature_importance.png`,
  `docs/drift_hitrate.png`

## Split (never random)

| slice | rows | dates | used for |
|---|---|---|---|
| train | 819,568 | 2025-01-01 to 2025-10-10 | fitting trees |
| validation | 60,816 | 2025-10-11 to 2025-10-31 | early stopping + isotonic calibration ONLY |
| test | 176,656 | 2025-11-01 to 2025-12-31 | untouched until `evaluate.py` |

Class imbalance is handled with `scale_pos_weight = 18.9` (the train negative/positive
ratio). Nothing is resampled, so the test set keeps its true 5.04% positive rate.

## Headline results (test months 11-12)

hit-rate@K = of the districts that actually had a cash-out in a 6-hour window, what
share sat in our top K. Averaged over windows with at least one cash-out.

| K (share of India) | model | b2 trailing heat | b1 static 25 | oracle |
|---|---|---|---|---|
| 10 (1.4%) | 26.0% | 21.8% | 11.5% | 31.6% |
| 25 (3.5%) | **55.8%** | 52.2% | 27.7% | 73.1% |
| 50 (6.9%) | **78.9%** | 59.0% | 36.6% | 97.6% |

PR-AUC: model 0.741, ablation 0.621, b2 0.477, b1 0.223, random 0.050.

The model beats both baselines at every K, which is what PLAN.md required. Two honest
qualifications we should say out loud:

- **At K=25 the margin over trailing heat is only 3.6 points.** Trailing heat is a
  strong baseline here because the generator's self-excitation makes recent history
  genuinely predictive. The margin widens to 19.9 points at K=50.
- **hit-rate@25 cannot reach 100%.** There are 36.5 positive districts per window on
  average, so 25 slots cannot cover them; the oracle ceiling is 73.1%.

## Calibration

Ranking uses the raw score. The isotonic calibrator (fitted on validation only) turns
it into an honest probability: test Brier score 0.0584 raw -> 0.0221 calibrated, and
the reliability table in `metrics.md` tracks the diagonal closely (e.g. cells predicted
0.85 actually fire 87.5% of the time). This matters for Phase 6, where an alert
threshold like 0.8 has to mean something.

## Drift

hit-rate@25 by test week stays between 53.7% and 57.6% across all 9 test weeks, with no
decay at the two hotspot-reshuffle steps inside the test period. The static baseline
sits near 27% throughout.

The sharper test is cash-outs in districts that only became hotspots **after training
ended**:

| cohort | model | ablation | b2 | b1 |
|---|---|---|---|---|
| 7 districts hot only during test months | **70.2%** | 60.9% | 64.2% | **0.0%** |
| 10 districts hot since training rows ended | 87.0% | 80.7% | 87.5% | 17.2% |

b1 scoring exactly 0.0% on the test-only cohort is the headline of this section: a
static watchlist finds none of the new corridors, by construction. The model finds 70%
of them without ever having seen those districts hot.

## Feature importance

Live-chain features take ranks #1, #2, #4, #7, #12 and #17, together **61.2% of total
gain**. `min_chain_age_hours` alone is 25.3%: the model has learned the cash-out timing
curve (median ~14 h after the fraud).

The 15 nationwide complaint features contribute **5.8% of gain, best rank #18** - as
predicted at the end of Phase 2, they are identical across districts within a window,
so they can only shift the overall level, never the ranking. Keeping them is cheap and
lets the model modulate national risk level, but they are not doing the work.

## Ablation: what the live-chain features are worth

| K | with | without | delta |
|---|---|---|---|
| 10 | 26.0% | 24.7% | +1.3 |
| 25 | 55.8% | 54.9% | +0.9 |
| 50 | 78.9% | 65.9% | **+13.0** |
| 75 | 85.7% | 69.9% | **+15.8** |

The gain is concentrated deeper in the ranking, and the reason is specific: at K=50 the
full model catches 1,468 positive district-windows the ablation misses (against 238 the
other way). Those catches have a trailing 7-day history of just **4.4 withdrawals versus
79.7** for a typical positive. They are cold districts with no history to rank on,
visible only because stolen money is sitting in their accounts right now.

So the honest framing of the differentiator is not "it makes the top-25 list better" -
it barely does. It is **"it finds cash-outs in districts that trailing heat cannot see
at all."** That is also why it helps most on the newly-drifted hotspots above.

## Key decisions

- **One scoring function for everything.** `common.hit_rate_at_k` scores the model,
  both baselines, the ablation and the oracle. No chance of an accidentally favourable
  comparison.
- **An oracle row in every table.** Without it, "55.8%" looks weak; against a 73.1%
  ceiling it is 76% of what is achievable.
- **Rank on raw score, report calibrated probability.** Isotonic regression is monotone
  so it cannot change the ranking, but it does create ties that would scramble top-K
  ordering.
- **The ablation is a full retrain**, not a feature-zeroing hack, so the remaining 36
  features get a fair chance to compensate.

## Known limitations

- Wall-clock training time in the transcript (~11 h) is the laptop sleeping; actual CPU
  is about 60 s for both models.
- The two cohorts of "new hotspot" districts are small (7 and 10), so those percentages
  are noisy.
- Everything is still synthetic. These numbers validate the pipeline, not real accuracy.
- `y_count` (the count label) is generated but unused so far; a Poisson objective would
  be a natural Phase 7 extension.

## Judge Q&As

**Q: Your model only beats the trailing-heat baseline by 3.6 points at K=25. Is the
machine learning earning its keep?**
A: At K=25, barely - and we say so. The value shows up in two places that matter
operationally. First, deeper in the list: at K=50 the margin is 19.9 points, because the
model finds cold districts with almost no recent history (4.4 trailing withdrawals
versus 79.7 for a typical hit) by seeing that stolen money is currently parked in
accounts there. Second, on newly emerged corridors, where the model gets 70.2% against
the static list's 0.0%. A trailing-heat dashboard is genuinely a decent tool; what it
cannot do is tell you about a district that was quiet last week and is about to be
cashed out tonight.

**Q: How do you know these numbers are not the result of leakage or a lucky split?**
A: Three defences. The split is strictly temporal, with the last three weeks before the
test months held out for early stopping and calibration so the test set is touched
exactly once, by `evaluate.py`. Every feature was already proven leak-free in Phase 2 by
a brute-force test that recomputes all 42 features with a hard cut-off at the window
start. And the whole pipeline is seeded and reproducible: re-running `evaluate.py`
produces a byte-identical `metrics.md`.

**Q: What would change with real CFCFRMS data?**
A: The absolute numbers, certainly - probably downward, because real geography is
messier than our generator and real mule networks reuse accounts across many victims,
which we do not yet model. What we expect to survive is the shape of the result: the
live-chain features should stay dominant, because they encode a mechanical fact rather
than a statistical pattern. Money that must be withdrawn as cash has to be withdrawn
somewhere near where it currently sits, within hours. The feature pipeline consumes the
CFCFRMS transaction trail directly, so swapping the data source needs no changes
downstream.
