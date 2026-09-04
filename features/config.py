"""
Knobs for the Phase 2 feature pipeline. Kept separate from datagen/config.py
because these describe how we LOOK at the data, not how the world behaves.
"""

WINDOW_HOURS = 6                 # unit of prediction: (district, 6-hour window)
LOOKBACK_DAYS = [1, 3, 7, 30]    # rolling-count horizons
DECAY_TAU_HOURS = 72.0           # exponential-decay memory: a withdrawal 3 days
                                 # ago counts ~1/e as much as one just now
ACTIVE_CHAIN_MAX_AGE_HOURS = 72  # a chain older than this without a cash-out is
                                 # treated as dead (max cash-out delay is 48h)
N_ACTIVE_HOTSPOTS = 25           # "active hotspots" = top-25 districts by
                                 # withdrawals in the last 30 days (from the past only)
HOURS_SINCE_CAP = 24 * 30        # "never seen a withdrawal" is capped at 30 days
DIST_CAP_KM = 3000.0             # distance when there is no active hotspot yet

TRAIN_TABLE_PATH = "data/train_table.parquet"
SUMMARY_PATH = "docs/feature_summary.md"
