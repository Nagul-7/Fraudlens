"""
Knobs for Phase 3 (training + evaluation).
"""
from datagen import config as DC

TRAIN_TABLE_PATH = "data/train_table.parquet"

# Temporal split. NEVER a random split: the model must predict the future.
TEST_START = "2025-11-01"   # months 11-12 are the untouched test set
VALID_DAYS = 21             # last 3 weeks of the train months are held out for
                            # early stopping + probability calibration only

# The six "live chain" features - our differentiator, removed in the ablation.
LIVE_CHAIN_FEATURES = [
    "n_active_chains_here", "n_active_accounts_here", "money_in_flight_here",
    "avg_chain_age_hours", "min_chain_age_hours", "avg_active_hop_here",
]
NATIONWIDE_COMPLAINT_PREFIX = "cmp_nat_"

LGB_PARAMS = {
    "objective": "binary",
    "metric": "average_precision",  # PR-AUC on the validation slice
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 200,        # leaves must cover many district-windows
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": DC.SEED,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}
NUM_ROUNDS = 2000
EARLY_STOPPING_ROUNDS = 100

TOP_KS = [10, 25, 50]       # "police watch the K riskiest districts each window"

MODEL_PATH = "model/model.txt"
ABLATION_MODEL_PATH = "model/model_no_chains.txt"
CALIBRATOR_PATH = "model/calibrator.pkl"
FEATURES_PATH = "model/features.json"
METRICS_PATH = "docs/metrics.md"
IMPORTANCE_PLOT = "docs/feature_importance.png"
DRIFT_PLOT = "docs/drift_hitrate.png"
