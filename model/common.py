"""
Shared pieces for train.py and evaluate.py: loading, the temporal split, and
the per-window top-K metric. Kept in one place so every method (model,
baselines, ablation) is scored by exactly the same code.
"""
import numpy as np
import pandas as pd

from datagen import config as DC
from model import config as MC

KEY_COLS = ["district_id", "window_idx", "window_start"]
LABEL_COLS = ["y", "y_count"]


def load_table():
    df = pd.read_parquet(MC.TRAIN_TABLE_PATH)
    return df.sort_values(["window_idx", "district_id"]).reset_index(drop=True)


def feature_columns(df):
    return [c for c in df.columns if c not in KEY_COLS + LABEL_COLS]


def split(df):
    """train (months 1-10 minus last 3 weeks), valid (those 3 weeks), test (months 11-12)."""
    test_start = pd.Timestamp(MC.TEST_START)
    valid_start = test_start - pd.Timedelta(days=MC.VALID_DAYS)
    train = df[df["window_start"] < valid_start]
    valid = df[(df["window_start"] >= valid_start) & (df["window_start"] < test_start)]
    test = df[df["window_start"] >= test_start]
    return train, valid, test


def as_window_matrix(part, col):
    """Values of `col` as a [n_windows, n_districts] matrix (rows sorted by window, district)."""
    n_d = part["district_id"].nunique()
    return part[col].to_numpy().reshape(-1, n_d)


def hit_rate_at_k(score, y, k, y_count=None, subset=None):
    """Per-window top-K metrics.

    score, y: [n_windows, n_districts]. For each window, flag the K districts
    with the highest score (ties broken by district order).
      hit_rate   = caught positive districts / all positive districts (recall@K)
      precision  = caught positive districts / K
      coverage   = withdrawals inside flagged districts / all withdrawals
    `subset` (bool [n_districts]) restricts the positives we care about, e.g.
    "districts that only became hotspots during the test period".
    Windows with no positives (in the subset) are skipped in the average.
    """
    order = np.argsort(-score, axis=1, kind="stable")[:, :k]
    flagged = np.zeros_like(y, dtype=bool)
    np.put_along_axis(flagged, order, True, axis=1)
    pos = y > 0
    if subset is not None:
        pos = pos & subset[None, :]
    n_pos = pos.sum(axis=1)
    has_pos = n_pos > 0
    caught = (flagged & pos).sum(axis=1)
    out = {
        "hit_rate": float(np.mean(caught[has_pos] / n_pos[has_pos])),
        "precision": float(np.mean(caught[has_pos] / k)),
        "per_window": np.where(has_pos, caught / np.maximum(n_pos, 1), np.nan),
        "n_windows": int(has_pos.sum()),
    }
    if y_count is not None:
        yc = np.where(pos, y_count, 0)
        total = yc.sum(axis=1)
        out["coverage"] = float(np.mean((yc * flagged).sum(axis=1)[has_pos] / total[has_pos]))
    return out
