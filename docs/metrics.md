# Metrics (test months 11-12, synthetic data)

> All numbers are measured on the synthetic world from `datagen/`. They show the
> pipeline learns the encoded fraud physics; they are NOT claims about real-world accuracy.

## Setup

- train: 819,568 rows, 2025-01-01 to 2025-10-10, 4.94% positive
- validation (early stopping + isotonic calibration only): 60,816 rows, 2025-10-11 to 2025-10-31
- test (untouched until this script): 176,656 rows = 244 windows x 724 districts, 2025-11-01 to 2025-12-31, 4.96% positive
- positives per test window: mean 35.9 districts (so hit-rate@25 cannot reach 100% - see the oracle row)
- model: LightGBM, 318 trees (early-stopped), scale_pos_weight, 42 features; ablation: 137 trees, 36 features
- rankings use the raw model score; calibrated probabilities (isotonic, fit on validation) are reported below

## Headline: hit-rate@top-K per 6-hour window

"If police watch the K riskiest districts each window, what fraction of the districts
that actually had a fraud cash-out do we catch?" Precision@K = fraction of flagged
districts that had one; withdrawal coverage = share of individual withdrawals inside
flagged districts. Averaged over test windows with at least one cash-out.

### K = 10  (watching 10/724 = 1.4% of India's districts)

| label | hit_rate | precision | withdrawal_coverage |
|---|---|---|---|
| FraudLens model | 26.7% | 87.6% | 41.1% |
| model without live-chain features | 25.8% | 84.6% | 38.4% |
| b2: trailing 7-day heat | 22.1% | 75.7% | 28.7% |
| b1: static 25 hotspots | 10.2% | 35.1% | 11.9% |
| oracle (perfect ranking) | 31.8% | 100.0% | 67.4% |


### K = 25  (watching 25/724 = 3.5% of India's districts)

| label | hit_rate | precision | withdrawal_coverage |
|---|---|---|---|
| FraudLens model | 56.7% | 76.8% | 72.6% |
| model without live-chain features | 55.9% | 75.8% | 71.0% |
| b2: trailing 7-day heat | 53.7% | 73.7% | 68.1% |
| b1: static 25 hotspots | 21.6% | 29.9% | 25.2% |
| oracle (perfect ranking) | 73.4% | 96.0% | 93.3% |


### K = 50  (watching 50/724 = 6.9% of India's districts)

| label | hit_rate | precision | withdrawal_coverage |
|---|---|---|---|
| FraudLens model | 80.3% | 56.4% | 89.0% |
| model without live-chain features | 67.7% | 46.7% | 80.4% |
| b2: trailing 7-day heat | 61.0% | 42.2% | 73.4% |
| b1: static 25 hotspots | 35.1% | 24.6% | 38.3% |
| oracle (perfect ranking) | 98.2% | 69.7% | 99.7% |


## PR-AUC (test)

| method | pr_auc |
|---|---|
| FraudLens model | 0.753 |
| model without live-chain features | 0.646 |
| b2: trailing 7-day heat | 0.503 |
| b1: static 25 hotspots | 0.223 |

Random ranking would score 0.050.

## Calibration (isotonic, fitted on the validation slice only)

- Brier score on test: raw 0.0565 -> calibrated 0.0213 (lower is better; scale_pos_weight inflates raw scores)

| bin | n | mean_predicted | observed |
|---|---|---|---|
| 0.0-0.1 | 162292 | 0.009 | 0.009 |
| 0.1-0.2 | 2959 | 0.152 | 0.144 |
| 0.2-0.3 | 2146 | 0.257 | 0.267 |
| 0.3-0.4 | 1444 | 0.331 | 0.353 |
| 0.4-0.5 | 1369 | 0.433 | 0.461 |
| 0.5-0.6 | 723 | 0.534 | 0.585 |
| 0.6-0.7 | 448 | 0.654 | 0.663 |
| 0.7-0.8 | 2052 | 0.750 | 0.757 |
| 0.8-0.9 | 1113 | 0.879 | 0.837 |
| 0.9-1.0 | 2110 | 0.942 | 0.937 |


## Drift analysis

![drift](drift_hitrate.png)

hit-rate@25 per test week (hotspots are reshuffled by the generator every 30 days):

| week | days | model | ablation | b2 | b1 |
|---|---|---|---|---|---|
| 1 | 7 | 58.1% | 58.2% | 55.3% | 22.4% |
| 2 | 7 | 54.5% | 53.7% | 53.7% | 20.6% |
| 3 | 7 | 55.8% | 55.4% | 53.0% | 21.3% |
| 4 | 7 | 54.9% | 53.5% | 51.4% | 22.8% |
| 5 | 7 | 55.9% | 55.1% | 54.1% | 21.2% |
| 6 | 7 | 58.6% | 58.1% | 55.9% | 21.7% |
| 7 | 7 | 57.0% | 56.2% | 53.3% | 22.4% |
| 8 | 7 | 58.2% | 56.6% | 54.5% | 21.0% |
| 9 | 5 | 57.2% | 56.1% | 51.3% | 21.2% |


### Cash-outs in districts that were never hot during training

hit-rate@25 restricted to positives in districts whose first hotspot episode started
after the training rows end (day 283, 2025-10-10) or after the
test start (day 304, 2025-11-01). n_windows = test windows containing such a cash-out.

**new since training rows ended** - 11 districts: 106 (day 360), 143 (day 330), 185 (day 300), 192 (day 300), 362 (day 330), 363 (day 360), 383 (day 360), 390 (day 300), 687 (day 300), 693 (day 360), 717 (day 300)

| method | hit_rate_25 | n_windows |
|---|---|---|
| FraudLens model | 87.7% | 242 |
| model without live-chain features | 78.9% | 242 |
| b2: trailing 7-day heat | 88.9% | 242 |
| b1: static 25 hotspots | 26.2% | 242 |


**new during test months only** - 6 districts: 106 (day 360), 143 (day 330), 362 (day 330), 363 (day 360), 383 (day 360), 693 (day 360)

| method | hit_rate_25 | n_windows |
|---|---|---|
| FraudLens model | 63.7% | 177 |
| model without live-chain features | 52.7% | 177 |
| b2: trailing 7-day heat | 55.9% | 177 |
| b1: static 25 hotspots | 45.9% | 177 |


## Feature importance (gain)

![importance](feature_importance.png)

| rank | feature | gain_share | group |
|---|---|---|---|
| 1 | min_chain_age_hours | 26.6% | live chain |
| 2 | n_active_accounts_here | 23.7% | live chain |
| 3 | hrs_since_wd_here | 11.3% | other |
| 4 | wd_decay | 7.0% | other |
| 5 | money_in_flight_here | 7.0% | live chain |
| 6 | population_weight | 3.6% | other |
| 7 | hour_block | 3.0% | other |
| 8 | n_active_chains_here | 2.3% | live chain |
| 9 | wd_nb_7d | 1.7% | other |
| 10 | hrs_since_wd_nb | 1.4% | other |
| 11 | day_of_week | 1.0% | other |
| 12 | dist_to_active_hotspot_km | 0.9% | other |
| 13 | avg_chain_age_hours | 0.9% | live chain |
| 14 | n_atms | 0.6% | other |
| 15 | cmp_nb_7d | 0.6% | other |
| 16 | wd_1d | 0.5% | other |
| 17 | wd_30d | 0.5% | other |
| 18 | cmp_nat_UPI_3d | 0.4% | nationwide complaints |
| 19 | is_hotspot | 0.4% | other |
| 20 | wd_7d | 0.4% | other |


- live-chain features: ranks min_chain_age_hours #1, n_active_accounts_here #2, money_in_flight_here #5, n_active_chains_here #8, avg_chain_age_hours #13, avg_active_hop_here #21 - together 60.8% of total gain
- nationwide complaint features (15): best rank #18, together 5.1% of total gain

## Ablation: remove the six live-chain features

Same recipe, same split, 36 features instead of 42.

| k | with_chains | without | delta |
|---|---|---|---|
| 10 | 26.7% | 25.8% | +0.9% |
| 25 | 56.7% | 55.9% | +0.8% |
| 50 | 80.3% | 67.7% | +12.6% |


PR-AUC with 0.753 vs without 0.646 (a large gap, while the
hit-rate gap at K=25 is small). The reason is that the benefit is concentrated deeper in
the ranking - sweeping K shows where it appears:

| k | model | ablation | delta | oracle |
|---|---|---|---|---|
| 5 | 14.2% | 13.6% | +0.6% | 15.9% |
| 10 | 26.7% | 25.8% | +0.9% | 31.8% |
| 25 | 56.7% | 55.9% | +0.8% | 73.4% |
| 40 | 73.1% | 65.2% | +7.9% | 93.9% |
| 50 | 80.3% | 67.7% | +12.6% | 98.2% |
| 75 | 87.1% | 73.2% | +13.9% | 100.0% |
| 100 | 89.8% | 77.4% | +12.3% | 100.0% |
| 150 | 93.2% | 83.6% | +9.6% | 100.0% |


At K=50 the full model catches 1,429 positive district-windows the ablation misses,
while the ablation catches 248 the full model misses. Those model-only catches are COLD
districts, not the obvious corridors:

| group | wd7 | chains |
|---|---|---|
| all positive district-windows | 81.310 | 12.616 |
| caught by model only (K=50) | 5.529 | 1.945 |


`wd7` = withdrawals in that district over the previous 7 days; `chains` = live chains holding
money there. The districts the live-chain features rescue have almost no recent history
(5.5 vs 81.3 trailing withdrawals), so no amount of trailing heat could rank them.
They are visible only because stolen money is sitting in their accounts right now. That is the
cold-start case the differentiator exists for.
