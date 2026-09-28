"""
brain.py: the local AI.

A machine-learning model (gradient-boosted decision trees, from scikit-learn)
that runs 100% on your own computer. No internet or paid API is needed to think.

The question it answers, for every stock, at every bar:
    swing desk: "What's the chance the price is HIGHER in 5 trading days?"
    day desk:   "What's the chance it's HIGHER in 1 hour (before today's close)?"

It learns "walk-forward", like a person living through history. On each
retrain point it studies only the past (answers it could actually know by
then), then makes predictions until the next retrain. So its backtest score
is honest: it never saw the future it's being graded on.

Why not have a chatbot (LLM) pick the trades? An LLM has read the news about
the very years we'd test it on, so a backtest of it is secretly cheating. Its
answers also change from run to run, so you can't measure it reliably. The
LLM (llm.py) writes explanations; this model makes the calls.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import FEATURE_COLUMNS, INTRADAY_COLUMNS, label_known_at, make_features, make_label


class Brain:
    def __init__(self, horizon=5, retrain_every=21, min_train=500, intraday=False):
        self.horizon = horizon                  # all counted in bars (days, or 5-minute bars)
        self.retrain_every = retrain_every
        self.min_train = min_train
        self.intraday = intraday
        self.columns = INTRADAY_COLUMNS if intraday else FEATURE_COLUMNS

    def _new_model(self):
        # Small and heavily "regularized" on purpose: stock data is mostly noise,
        # and a big model would just memorize the noise.
        return HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
            min_samples_leaf=50, l2_regularization=1.0, random_state=42)

    def build_dataset(self, bars: dict, market: pd.DataFrame) -> pd.DataFrame:
        """One long table: a row per (time, ticker) with features + the answer."""
        frames = []
        for ticker, df in bars.items():
            f = make_features(df, market, self.intraday)
            f["label"] = make_label(df, self.horizon, same_day=self.intraday)
            f["known_at"] = label_known_at(df, self.horizon, same_day=self.intraday)
            f["ticker"] = ticker
            frames.append(f)
        data = pd.concat(frames)
        data.index.name = "date"
        return data.reset_index().dropna(subset=self.columns)

    def walk_forward_scores(self, bars: dict, market: pd.DataFrame, since=None) -> pd.DataFrame:
        """Probability (0-1) of 'price higher later' for every bar and ticker.
        Bars before the AI has enough history stay blank (= no trades).
        since: only fill in scores from this time on (much faster for live use)."""
        data = self.build_dataset(bars, market)
        dates = sorted(data["date"].unique())
        scores = pd.DataFrame(np.nan, index=pd.DatetimeIndex(dates), columns=list(bars))
        since = pd.Timestamp(since) if since is not None else None

        for start in range(self.min_train, len(dates), self.retrain_every):
            end = dates[min(start + self.retrain_every, len(dates)) - 1]
            if since is not None and end < since:
                continue
            # Train only on answers that were already known at dates[start].
            train = data[(data["known_at"] <= dates[start]) & data["label"].notna()]
            if len(train) < 200 or train["label"].nunique() < 2:
                continue
            model = self._new_model().fit(train[self.columns], train["label"].astype(int))

            block = data[(data["date"] >= dates[start]) & (data["date"] <= end)]
            if block.empty:
                continue
            prob_up = model.predict_proba(block[self.columns])[:, 1]
            for (date, ticker), p in zip(zip(block["date"], block["ticker"]), prob_up):
                scores.at[date, ticker] = p
        return scores
