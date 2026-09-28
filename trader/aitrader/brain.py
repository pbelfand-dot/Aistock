"""
brain.py: the local AI.

A machine-learning model (gradient-boosted decision trees, from scikit-learn)
that runs 100% on your own computer. No internet or paid API is needed to think.

The one question it answers, for every stock, every day:
    "Given how this stock and the market have been acting,
     what's the chance the price is HIGHER in N trading days?"

It learns "walk-forward", like a person living through history. On each
retrain day it studies only the past (answers it could actually know by then),
then makes predictions for the next few weeks. So its backtest score is
honest: it never saw the future it's being graded on.

Why not have a chatbot (LLM) pick the trades? An LLM has read the news about
the very years we'd test it on, so a backtest of it is secretly cheating. Its
answers also change from run to run, so you can't measure it reliably. The
LLM (llm.py) writes explanations; this model makes the calls.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import FEATURE_COLUMNS, make_features, make_label


class Brain:
    def __init__(self, horizon_days=5, retrain_every_days=21, min_train_days=500):
        self.horizon_days = horizon_days
        self.retrain_every_days = retrain_every_days
        self.min_train_days = min_train_days

    def _new_model(self):
        # Small and heavily "regularized" on purpose: stock data is mostly noise,
        # and a big model would just memorize the noise.
        return HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
            min_samples_leaf=50, l2_regularization=1.0, random_state=42)

    def build_dataset(self, bars: dict, market: pd.DataFrame) -> pd.DataFrame:
        """One long table: a row per (day, ticker) with features + the answer."""
        frames = []
        for ticker, df in bars.items():
            f = make_features(df, market)
            f["label"] = make_label(df, self.horizon_days)
            f["ticker"] = ticker
            frames.append(f)
        data = pd.concat(frames)
        data.index.name = "date"
        return data.reset_index().dropna(subset=FEATURE_COLUMNS)

    def walk_forward_scores(self, bars: dict, market: pd.DataFrame) -> pd.DataFrame:
        """Probability (0-1) of 'price higher in N days' for every day and ticker.
        Days before the AI has enough history stay blank (= no trades)."""
        data = self.build_dataset(bars, market)
        dates = sorted(data["date"].unique())
        scores = pd.DataFrame(np.nan, index=pd.DatetimeIndex(dates), columns=list(bars))

        for start in range(self.min_train_days, len(dates), self.retrain_every_days):
            # On dates[start] we only know answers for days at least N trading days old.
            last_known = dates[start - self.horizon_days]
            train = data[(data["date"] <= last_known) & data["label"].notna()]
            if len(train) < 200 or train["label"].nunique() < 2:
                continue
            model = self._new_model().fit(train[FEATURE_COLUMNS], train["label"].astype(int))

            end = dates[min(start + self.retrain_every_days, len(dates)) - 1]
            block = data[(data["date"] >= dates[start]) & (data["date"] <= end)]
            if block.empty:
                continue
            prob_up = model.predict_proba(block[FEATURE_COLUMNS])[:, 1]
            for (date, ticker), p in zip(zip(block["date"], block["ticker"]), prob_up):
                scores.at[date, ticker] = p
        return scores
