"""
Phase 3 - training.

Run:  python -m model.train

1. Temporal split: months 1-10 train (last 3 weeks = validation), 11-12 test.
2. LightGBM binary classifier with scale_pos_weight for the ~5% positive rate.
   Early stopping on validation PR-AUC. Test rows are never touched here.
3. Isotonic calibration fitted on the validation slice only, so the scores
   the API shows are real probabilities (scale_pos_weight inflates raw ones).
4. Ablation model: same recipe WITHOUT the six live-chain features.

Outputs: model/model.txt, model/model_no_chains.txt, model/calibrator.pkl,
         model/features.json
"""
import json
import pickle
import time

import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

from model import common
from model import config as MC


def fit(train, valid, features, label="model"):
    """Train one LightGBM model with early stopping. Returns the booster."""
    n_pos = int(train["y"].sum())
    n_neg = len(train) - n_pos
    params = dict(MC.LGB_PARAMS, scale_pos_weight=n_neg / n_pos)
    dtrain = lgb.Dataset(train[features], label=train["y"], free_raw_data=True)
    dvalid = lgb.Dataset(valid[features], label=valid["y"], reference=dtrain)
    t0 = time.time()
    booster = lgb.train(
        params, dtrain, num_boost_round=MC.NUM_ROUNDS, valid_sets=[dvalid],
        valid_names=["valid"],
        callbacks=[lgb.early_stopping(MC.EARLY_STOPPING_ROUNDS, verbose=False),
                   lgb.log_evaluation(200)],
    )
    print(f"  [{label}] {len(features)} features, scale_pos_weight={n_neg / n_pos:.1f}, "
          f"best iteration {booster.best_iteration}, "
          f"valid PR-AUC {booster.best_score['valid']['average_precision']:.4f}, "
          f"{time.time() - t0:.0f}s")
    return booster


def main():
    t0 = time.time()
    df = common.load_table()
    train, valid, test = common.split(df)
    features = common.feature_columns(df)
    print(f"rows: train {len(train):,} ({train['y'].mean():.2%} pos)  "
          f"valid {len(valid):,} ({valid['y'].mean():.2%} pos)  "
          f"test {len(test):,} (untouched)")
    del df, test

    print("training main model ...")
    booster = fit(train, valid, features, "main")
    booster.save_model(MC.MODEL_PATH, num_iteration=booster.best_iteration)

    print("calibrating on the validation slice ...")
    raw_valid = booster.predict(valid[features], num_iteration=booster.best_iteration)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(raw_valid, valid["y"])
    cal_valid = calibrator.predict(raw_valid)
    print(f"  valid Brier score raw {brier_score_loss(valid['y'], raw_valid):.4f} "
          f"-> calibrated {brier_score_loss(valid['y'], cal_valid):.4f}; "
          f"PR-AUC unchanged {average_precision_score(valid['y'], cal_valid):.4f}")
    with open(MC.CALIBRATOR_PATH, "wb") as f:
        pickle.dump(calibrator, f)

    print("training ablation model (no live-chain features) ...")
    ablation_features = [c for c in features if c not in MC.LIVE_CHAIN_FEATURES]
    ablation = fit(train, valid, ablation_features, "no-chains")
    ablation.save_model(MC.ABLATION_MODEL_PATH, num_iteration=ablation.best_iteration)

    with open(MC.FEATURES_PATH, "w") as f:
        json.dump({"features": features, "ablation_features": ablation_features,
                   "best_iteration": booster.best_iteration,
                   "ablation_best_iteration": ablation.best_iteration}, f, indent=2)
    print(f"saved {MC.MODEL_PATH}, {MC.ABLATION_MODEL_PATH}, {MC.CALIBRATOR_PATH}, "
          f"{MC.FEATURES_PATH}  ({time.time() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
