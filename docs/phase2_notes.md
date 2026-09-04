# Phase 2 notes - feature pipeline

## What was built

`python -m features.build` turns the Phase 1 database into one training
table, `data/train_table.parquet`:

| | |
|---|---|
| unit of prediction | (district, 6-hour window) |
| rows | 1,057,040 = 724 districts x 1,460 windows |
| columns | 47 = 42 features + 2 labels (`y`, `y_count`) + 3 keys (`district_id`, `window_idx`, `window_start`) |
| positive rate | 5.04% of windows contain at least one fraud withdrawal (5.4 withdrawals on average when they do) |
| build time | ~7 s (plus ~4 s to load the DB) |
| file size | 25 MB |

Files:
- `features/config.py`  - lookback horizons, decay constant, chain max age, etc.
- `features/build.py`   - the pipeline (matrices + a few groupbys, no per-window loops)
- `features/test_leakage.py` - brute-force re-computation of every feature for
  60 sampled rows; must match the fast table exactly
- `docs/feature_summary.md` - auto-generated stats for every feature (mean, min,
  max, mean when y=1 vs y=0, lift)

## The anti-leakage rule

Every feature for a window starting at time T uses only events **visible
strictly before T**:

| event | visible from |
|---|---|
| complaint | `reported_at` (never the incident time) |
| transaction in a chain | max(transaction time, that complaint's `reported_at`) |
| withdrawal in a chain | max(withdrawal time, that complaint's `reported_at`) |

The second and third rows encode a real-world fact: nobody traces a mule chain
until the victim reports, so a hop that happened an hour ago is still invisible
if the complaint was only filed just now. Labels use the true withdrawal times
inside [T, T+6h).

The rolling features are cumulative-sum differences over past windows, so
"only windows before this one" holds by construction. The live-chain features
use holding intervals that start and end at visibility times.

### Leakage test result (`python -m features.test_leakage`)

```
check 1 PASS: 60 rows x 42 features match the strict brute force
check 2 PASS: peeking 6h ahead changes 60/60 rows (33 distinct features)
LEAKAGE TEST PASSED
```

Check 1 re-computes all 42 features for 60 sampled rows (30 random, 15 in
initial hotspots, 15 with live chains present) using a deliberately plain
implementation that filters `t_visible < T` and nothing else. Check 2 moves the
cut-off 6h into the future and confirms the values change, i.e. the test
would notice a leak. The test already earned its keep: its first run caught a
bug where `min_chain_age_hours` was being truncated to whole hours.

## Feature dictionary

Times are hours; "here" means this district; "visible" means known before the
window starts. Lift = mean value in positive windows / mean in negative windows.

### Static (3)

| feature | meaning | why it predicts cash-outs | lift |
|---|---|---|---|
| `is_hotspot` | district is one of the 25 initially known mule corridors | known corridors cash out far more. It is static, so it cannot follow drift - the rolling features must do that | 20.3 |
| `n_atms` | number of ATMs in the district | more machines = more capacity to structure withdrawals under 50k | 1.2 |
| `population_weight` | synthetic population proxy | background (non-corridor) cash-outs scale with people and accounts | 1.3 |

### Calendar (4) - known in advance, so never leakage

| feature | meaning | why | lift |
|---|---|---|---|
| `hour_block` | 0 = 00-06h, 1 = 06-12h, 2 = 12-18h, 3 = 18-24h | withdrawals peak early morning and late evening | 1.2 |
| `day_of_week` | 0 = Monday ... 6 = Sunday | Sunday cash-outs are rarer and slip to Monday | 0.9 |
| `is_weekend` | Saturday or Sunday | same | 0.8 |
| `is_holiday` | published bank-holiday-style day | ATM refills stop, gangs wait | 0.7 |

### Rolling withdrawals here (5)

| feature | meaning | why | lift |
|---|---|---|---|
| `wd_1d`, `wd_3d`, `wd_7d`, `wd_30d` | visible fraud withdrawals here in the last 1/3/7/30 days | a corridor being worked keeps being worked (self-excitation); the 30-day count tracks the *current* hotspot set even after drift | 22.7 / 20.6 / 19.9 / 18.2 |
| `wd_decay` | same, but each withdrawal weighted exp(-age / 72h) | smooth memory: yesterday counts more than last week | 20.3 |

### Neighbourhood (2)

| feature | meaning | why | lift |
|---|---|---|---|
| `wd_nb_1d`, `wd_nb_7d` | visible withdrawals in the 5 nearest districts | gangs spill over into neighbouring districts; new corridors grow next to old ones | 5.3 / 5.2 |

### Self-excitation timers (2)

| feature | meaning | why | lift |
|---|---|---|---|
| `hrs_since_wd_here` | hours since the last visible withdrawal here (capped at 720) | the excitation cools over 3-7 days; small values mean "hot right now" | 0.26 |
| `hrs_since_wd_nb` | same for the nearest neighbour that had one | spillover version | 0.37 |

### Active hotspots inferred from the past (2)

| feature | meaning | why | lift |
|---|---|---|---|
| `is_active_hotspot_30d` | district is in the top 25 by withdrawals over the past 30 days | a data-driven, drifting version of `is_hotspot` - this is how the model follows adversarial adaptation | 44.8 |
| `dist_to_active_hotspot_km` | km to the nearest such district (0 if itself) | proximity to a live corridor raises risk | 0.48 |

### Complaints (18)

| feature | meaning | why | lift |
|---|---|---|---|
| `cmp_nat_<category>_1d/3d/7d` (15) | complaints reported nationwide in the last 1/3/7 days, per category (UPI, investment, card, loan_app, digital_arrest) | how much stolen money is "in the pipeline" that must cash out within 2-48h; the mix matters because digital-arrest frauds are 40x larger than UPI ones. Same value for every district in a window | ~1.0 |
| `cmp_local_1d`, `cmp_local_7d` | complaints whose victim lives here | weak on purpose: victims and cash-outs are in different places. Kept so the model can check, because some real fraud is local | 1.3 |
| `cmp_nb_7d` | same for the 5 nearest districts | same | 1.0 |

PLAN.md asked for complaint counts in "linked" districts. A complaint becomes
linked to a district the moment its money lands in an account there, which
is exactly what the live-chain features below measure, so that is where the
linkage lives.

### Live chains - the differentiator (6)

A chain is *active* at T if the complaint is reported, it is younger than 72 h,
and it has no visible withdrawal yet. Its money sits in whichever accounts have
received a transfer but not forwarded it on.

| feature | meaning | why | lift |
|---|---|---|---|
| `n_active_chains_here` | active chains whose money currently sits in an account in this district | the mule who will walk to the ATM already holds the money here | 16.5 |
| `n_active_accounts_here` | number of such accounts | fan-out: several mules with cash to pull | 19.8 |
| `money_in_flight_here` | rupees sitting in those accounts | more money = more withdrawals needed to structure it under 50k | 20.0 |
| `avg_chain_age_hours` | mean hours since the fraud for those chains (0 if none) | cash-out happens 2-48 h after the fraud, median ~14 h; chains near that age are ripe | 2.0 |
| `min_chain_age_hours` | age of the youngest such chain (72 if none) | a fresh chain that just parked money here is about to move | 0.32 |
| `avg_active_hop_here` | mean hop number of the holding accounts (0 if none) | money at hop 5-7 has finished layering and is about to be withdrawn | 2.3 |

## Key decisions

- **Visibility times instead of event times.** The single most important
  design choice. It costs nothing in code (one `max()`), and it is what makes
  the metrics in Phase 3 honest.
- **Matrices, not loops.** Rolling counts are computed for all 724 districts x
  1,460 windows at once as cumulative-sum differences. The whole table builds in
  seconds, so re-running with new features is cheap.
- **Holding intervals for live chains.** Each transfer creates a "holding":
  money is in account A from when the transfer becomes visible until A forwards
  it, the chain cashes out, or the chain goes stale at 72 h. Holdings are
  expanded to the windows they overlap (2.2 M rows) and aggregated with
  groupbys. No graph library is needed for these aggregates; networkx will be
  used in Phase 4 for the drill-down view of a single chain.
- **"Active hotspots" come from the past 30 days**, never from
  `hotspot_history` (which would be future knowledge).
- **The brute-force test is the definition of every feature.** If the fast
  pipeline and the slow one disagree, the slow one is right.

## How to run

```bash
source venv/bin/activate
python -m features.build          # ~10 s -> data/train_table.parquet + docs/feature_summary.md
python -m features.test_leakage   # ~20 s, must print LEAKAGE TEST PASSED
```

## Known simplifications

- Chain hops become visible the instant the complaint is reported. Real banks
  take hours to respond to CFCFRMS; a "bank response delay" would be one more
  `max()` term.
- Neighbours are the 5 nearest centroids, not true shared borders.
- The nationwide complaint features are identical for every district in a
  window, so they can only shift the overall level, not the ranking.
- 30% of chains never cash out and sit as "money in flight" for up to 72 h.
  That is realistic noise: the LEA cannot know in advance which chains will
  cash out, so the model has to learn the base rate.

## Likely judge questions

**Q: How do you know the model is not peeking at the future?**
A: Two layers. First, every feature is computed from events with a visibility
time strictly before the window, and complaints are only visible once
reported. Second, `features/test_leakage.py` re-computes all 42 features for
sampled rows with a brute-force filter and asserts equality; it also proves
that moving the cut-off 6 h ahead changes the values, so it would catch a leak.
The test found a real bug on its first run.

**Q: What are the "live chain" features and would they exist with real data?**
A: When a victim reports, CFCFRMS pulls the transaction trail and freezes what
it can. We use that trail: which account holds the money right now, in which
district, how much, how old the chain is. With real feeds these come straight
from the CFCFRMS trail table; the visibility rule mirrors how the trail
actually arrives (only after the complaint).

**Q: Only 5% of windows are positive. Doesn't that make prediction trivial or
impossible?**
A: Neither - it makes *accuracy* useless (95% by predicting "no"). Phase 3
reports hit-rate@top-K: of the K district-windows we flag, how many actually
had a withdrawal. That matches how a control room works: limited teams, pick
the top K places to watch.
