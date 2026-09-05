"""
Everything the API needs, loaded once at startup.

Design notes
------------
- We serve the CALIBRATED model: the raw LightGBM score is turned into a real
  probability by the isotonic calibrator fitted on the validation slice.
  Ranking still uses the raw score (isotonic is monotone, but it creates ties
  that would scramble a top-K ordering).
- The demo clock starts at the FIRST WINDOW OF THE TEST PERIOD, so every
  score the dashboard shows is genuine out-of-sample prediction.
- Scores are precomputed for the whole served range at startup (~0.3 M rows,
  a couple of seconds) so endpoints are sub-millisecond lookups.
- Per-feature contributions (`pred_contrib`) are computed ON DEMAND for the
  724 rows of one window. That is milliseconds, and it avoids holding a
  90 MB contribution matrix in memory.
"""
import json
import pickle
import sqlite3

import lightgbm as lgb
import numpy as np
import pandas as pd

from datagen import config as DC
from features import config as FC
from features import build as FB
from model import common
from model import config as MC

HISTORY_DAYS = 30          # how far back the drill-down sparkline reaches
WINDOWS_PER_DAY = 24 // FC.WINDOW_HOURS


class AppState:
    def __init__(self):
        self.loaded = False

    # -- startup ----------------------------------------------------------
    def load(self):
        print("[api] loading model + table ...")
        self.booster = lgb.Booster(model_file=MC.MODEL_PATH)
        with open(MC.CALIBRATOR_PATH, "rb") as f:
            self.calibrator = pickle.load(f)
        with open(MC.FEATURES_PATH) as f:
            self.features = json.load(f)["features"]

        df = common.load_table()
        self.test_start = pd.Timestamp(MC.TEST_START)
        self.test_start_window = int(df.loc[df["window_start"] == self.test_start, "window_idx"].iloc[0])
        # serve the test period, plus 30 days before it so the sparkline is full
        first = self.test_start_window - HISTORY_DAYS * WINDOWS_PER_DAY
        self.df = df[df["window_idx"] >= first].reset_index(drop=True)
        self.last_window = int(self.df["window_idx"].max())
        del df

        print(f"[api] scoring {len(self.df):,} district-windows ...")
        raw = self.booster.predict(self.df[self.features])
        self.df["risk_raw"] = raw.astype(np.float32)
        self.df["risk"] = self.calibrator.predict(raw).astype(np.float32)
        # rank within each window: 1 = riskiest district in that window
        self.df["rank"] = (self.df.groupby("window_idx")["risk_raw"]
                             .rank(ascending=False, method="first").astype(np.int16))

        self.districts = pd.read_sql(
            "SELECT district_id, name, state, lat, lon, is_hotspot FROM districts ORDER BY district_id",
            sqlite3.connect(DC.DB_PATH))
        self.n_districts = len(self.districts)
        self.district_name = self.districts.set_index("district_id")["name"].to_dict()
        self.district_state = self.districts.set_index("district_id")["state"].to_dict()
        self._load_atms()
        self._load_accounts_bank()
        self._load_holdings()

        # index for O(1) slicing by window
        self.df = self.df.sort_values(["window_idx", "district_id"]).reset_index(drop=True)
        self.window_offset = {w: i * self.n_districts
                              for i, w in enumerate(sorted(self.df["window_idx"].unique()))}
        self.clock = self.test_start_window          # the demo clock
        self._contrib_cache = {}
        self.warm(self.clock)                        # so the first alert call is instant
        self.loaded = True
        print(f"[api] ready. clock at window {self.clock} ({self.window_start(self.clock)}), "
              f"serving up to {self.window_start(self.last_window)}")

    def _load_accounts_bank(self):
        """account_id -> bank, for the Phase 6 bank-facing view."""
        conn = sqlite3.connect(DC.DB_PATH)
        acc = pd.read_sql("SELECT account_id, bank FROM accounts", conn)
        conn.close()
        self.account_bank = acc.set_index("account_id")["bank"]
        self.banks = sorted(acc["bank"].unique().tolist())

    def _load_atms(self):
        conn = sqlite3.connect(DC.DB_PATH)
        atms = pd.read_sql("SELECT atm_id, district_id, bank, lat, lon FROM atms", conn)
        conn.close()
        self.atms_by_district = {d: g for d, g in atms.groupby("district_id")}
        self.n_atms = atms.groupby("district_id").size().to_dict()

    def _load_holdings(self):
        """Money currently parked in mule accounts, per (district, window).

        Reuses the Phase 2 holdings logic so the API's 'active chains' panel is
        exactly what the model's live-chain features saw - no second definition.
        """
        print("[api] building live-chain holdings ...")
        ev = FB.load_events()
        h = FB.build_holdings(ev)
        first_served = (self.test_start_window - HISTORY_DAYS * WINDOWS_PER_DAY) * FC.WINDOW_HOURS
        h = h[h["t_out"] >= first_served]            # only what can still be shown
        self.holdings = h.reset_index(drop=True)
        self.complaints = ev["complaints"].set_index("complaint_id")
        self.withdrawals = ev["withdrawals"]
        print(f"[api] {len(self.holdings):,} holdings in the served range")

    # -- helpers ----------------------------------------------------------
    def window_start(self, window_idx):
        return pd.Timestamp(DC.START_DATE) + pd.Timedelta(hours=int(window_idx) * FC.WINDOW_HOURS)

    def window_of(self, ts):
        hours = (pd.Timestamp(ts) - pd.Timestamp(DC.START_DATE)).total_seconds() / 3600
        return int(hours // FC.WINDOW_HOURS)

    def resolve_window(self, window):
        """'current' | ISO timestamp | window index -> a validated window index."""
        if window is None or window == "current":
            return self.clock
        try:
            w = int(window)
        except (TypeError, ValueError):
            w = self.window_of(window)
        if w < self.test_start_window:
            raise ValueError(
                f"window {self.window_start(w)} is before the test period starts "
                f"({self.test_start.isoformat()}). The API only serves out-of-sample windows.")
        if w > self.last_window:
            raise ValueError(f"window {self.window_start(w)} is past the end of the simulated data "
                             f"({self.window_start(self.last_window)}).")
        return w

    def window_rows(self, window_idx):
        """All 724 district rows for one window, in district_id order."""
        off = self.window_offset[window_idx]
        return self.df.iloc[off:off + self.n_districts]

    def contributions(self, window_idx):
        """LightGBM pred_contrib for one window: [n_districts, n_features + 1].

        Values are in raw log-odds space; the last column is the base value.
        Used only to RANK which features pushed a score up, so the space is fine.

        pred_contrib costs ~760 ms for 724 rows (SHAP is far more expensive than
        a plain predict, which is 4 ms), so results are cached per window and the
        cache is warmed on startup and whenever the clock advances. Endpoints
        therefore never pay that cost themselves.
        """
        cached = self._contrib_cache.get(window_idx)
        if cached is None:
            rows = self.window_rows(window_idx)
            cached = self.booster.predict(rows[self.features], pred_contrib=True)
            if len(self._contrib_cache) >= 8:        # keep memory bounded
                self._contrib_cache.pop(next(iter(self._contrib_cache)))
            self._contrib_cache[window_idx] = cached
        return cached

    def warm(self, window_idx):
        """Precompute the expensive contributions for a window."""
        self.contributions(window_idx)

    def districts_with_category(self, window_idx, category):
        """District ids currently holding money from a chain of this fraud type.

        The model itself is not per-category (risk is one number), so the
        category filter narrows WHICH districts are shown rather than changing
        any score. That keeps the filter honest.
        """
        held = self.active_holdings(window_idx)
        if held.empty:
            return set()
        cats = self.complaints["fraud_category"]
        return set(held.loc[held["complaint_id"].map(cats) == category, "district_id"].unique())

    def active_holdings(self, window_idx, district_id=None):
        """Chains whose money sits in a district at this window's start."""
        t = window_idx * FC.WINDOW_HOURS
        h = self.holdings
        m = (h["t_in"] < t) & (h["t_out"] >= t)
        if district_id is not None:
            m &= h["district_id"] == district_id
        out = h[m].copy()
        out["age_hours"] = t - out["t_incident"]
        return out


STATE = AppState()
