# Phase 1 notes - synthetic data engine

## What was built

`python -m datagen.generate` builds `data/fraudlens.db` (SQLite, ~170 MB) with
12 months of synthetic cyber-fraud history on REAL India district geography.

| table                | rows      | what it is |
|----------------------|-----------|------------|
| `districts`          | 724       | real districts from a public GeoJSON: id, name, state, centroid lat/lon, `is_hotspot` (the initial 25), synthetic `population_weight` |
| `district_neighbors` | 3,620     | 5 nearest districts by centroid distance (stand-in for shared borders) |
| `atms`               | 4,438     | ATMs scattered around each centroid, count ~ population, bank name |
| `accounts`           | 71,896    | victim / clean / mule accounts; mules concentrate in hotspots and mostly have rented/forged KYC |
| `holidays`           | 15        | random bank-holiday-style days |
| `hotspot_history`    | 51        | which districts were ACTIVE hotspots, and when (25 initial + 26 that drifted in) |
| `complaints`         | 102,563   | fraud events: time, `reported_at`, victim district, category, amount, first mule account |
| `transactions`       | 1,441,625 | the mule chain for every complaint (hop_number 1..7) |
| `withdrawals`        | 285,890   | **ground truth**: ATM cash-outs with atm, district, mule account, amount, time |

Extra columns/tables beyond PLAN.md, all cheap and useful later:
`complaints.reported_at` (so Phase 2 can avoid using complaints before they
were reported), `withdrawals.account_id`, `district_neighbors`, `hotspot_history`,
`holidays`, `districts.census_code`.

Files:
- `datagen/config.py`  - every physics knob, with a comment on what it models
- `datagen/geo.py`     - download + clean the GeoJSON, centroids, neighbours
- `datagen/generate.py`- the simulator (static world, hotspot drift, day-by-day events, write DB)
- `datagen/validate.py`- row counts, physics checks, four plots into `docs/`
- `data/india_districts.geojson` - cleaned map (committed, <1 MB) with `district_id` stamped on every polygon so the dashboard can join risk scores directly

## How the physics rules were implemented

1. **~300 complaints/day, log-normal amounts.** Poisson per day with a weekday
   factor (weekends lower, so the year averages ~281/day). Amount is log-normal
   with a category-specific median (UPI 15k ... digital arrest 6 lakh).
2. **Mule chain 3-7 hops with fan-out.** Money moves through a "frontier" of
   accounts. Each account forwards to 1 account, or with 30% chance fans out to
   2-4. A hop never holds more than 6 accounts; extra branches consolidate into
   an existing one (layering, then merging). Hop delays are log-normal (median
   25 min, tail to hours).
3. **Cash-out.** 70% of chains end in ATM withdrawals. The cash-out district is
   chosen FIRST, and every last-hop mule sits there. Delay is log-normal
   (median 10h, clipped 2-48h). The amount is split into withdrawals of
   10k-50k (never above 50k), one mule visiting several ATMs 5-40 minutes apart.
4. **Geography + drift.** 65% of cash-out chains go to an ACTIVE hotspot, the
   rest anywhere by population. Every 30 days each hotspot has a 12% chance of
   being "burned" and replaced, 60% of the time by a neighbour of an existing
   hotspot (corridor spreading), otherwise by a random populous district.
5. **Self-excitation.** A cash-out in district D adds +1.5 to D's weight
   multiplier (and +0.75 to its neighbours) for the next 3-7 days, capped at 6,
   then it cools. Implemented as a `boost[day, district]` matrix.
6. **Weekly / diurnal.** Withdrawal hour is sampled from a curve with early
   morning and late evening peaks. Cash-outs landing on a Sunday or holiday
   slip to the next day half the time.

## Key decisions (and why)

- **One seed, one `numpy` Generator passed everywhere.** Same config = same DB,
  byte for byte. Judges can re-run and get identical metrics.
- **Real districts, synthetic population.** The GeoJSON has no population, so
  `population_weight` is a log-normal proxy with a boost for known metros. Swapping
  in Census population is a one-column change.
- **Neighbours = 5 nearest centroids** instead of true shared borders. Avoids a
  geometry library and is easy to explain; good enough for spillover effects.
- **Time is "minutes since day 0" (a float)** inside the simulator and converted
  to timestamps only when writing. Simple arithmetic, no timezone headaches.
- **`hotspot_history` is stored but `districts.is_hotspot` stays the initial
  flag.** Later phases must NOT peek at the future hotspot set; the model has to
  infer drift from recent events.

## Validation results (`python -m datagen.validate`)

```
complaints/day                  281.0   (target ~300)
chains that cash out            70.2%   (target 70%)
max single withdrawal          50,000   (limit 50,000)
withdrawals in active hotspot   64.7%   (target ~65%)
hotspot episodes (drift)           51   (25 initial)
chain depth min/mean/max     3/5.0/7   (target 3-7)
fraud->first cash-out hours  p10=3.4 median=14.1 p90=35.1
withdrawals in peak hours       41.8%   (uniform would be 33%)
withdrawals on Sundays           7.2%   (uniform would be 14.3%)
positive (district,6h) rate     5.05%   of 1,057,040 windows
```

That last line matters for Phase 2/3: only ~5% of (district, 6-hour window)
cells contain a withdrawal, so accuracy is meaningless and hit-rate@top-K is
the right headline metric.

Plots: `plot_events_over_time.png`, `plot_geography.png`,
`plot_hop_histogram.png`, `plot_time_to_cashout.png` (all in `docs/`).

## How to run

```bash
source venv/bin/activate
python -m datagen.generate    # ~45 s, writes data/fraudlens.db
python -m datagen.validate    # prints checks, writes docs/plot_*.png
```

To change the world, edit `datagen/config.py` and re-run both.

## Known simplifications

- Population is a random proxy, so an occasional remote district gets a larger
  weight than it deserves (visible as a green "drifted-in" bubble in Ladakh).
- Chain depth is uniform 3-7 by construction; real depth distributions are skewed.
- Every complaint is a separate chain; real gangs reuse mule accounts across
  many victims (a Phase 2+ graph-feature enhancement if time allows).
- Events scheduled after day 365 (from the last day's frauds) are kept in the
  DB; the plots clip to the 365-day horizon.

## Likely judge questions

**Q: This is fake data. Why should we believe any metric?**
A: We don't claim real-world accuracy. The generator encodes publicly documented
fraud behaviour (Jamtara-style corridors, mule chains, structuring under 50k,
2-48h cash-out windows, corridor drift). Metrics prove the pipeline can learn
those patterns end to end. With real CFCFRMS/1930 feeds the generator is
replaced and nothing downstream changes - the tables have the same shape as
the real data.

**Q: How did you pick the hotspots and the parameters?**
A: The initial 25 are districts repeatedly named in public reporting on mule
corridors (Jamtara belt, Mewat/NCR, Bharatpur-Alwar, Kolkata metro, lower Assam).
Every numeric parameter is in one file with a comment explaining what it models,
so a domain expert can tune it in minutes without touching code.

**Q: Isn't a model trained on this just going to memorise the hotspot list?**
A: That is exactly why hotspots DRIFT every month and why there is self-excitation
and background noise everywhere. A naive "yesterday's hotspots" baseline is our
Phase 3 comparison; the model has to beat it by picking up drift and bursts from
recent events, not from the static flag.
