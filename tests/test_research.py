import json

import numpy as np
import pandas as pd

from polymarket_bot import history
from polymarket_bot.research import ResearchConfig, evaluate, market_trades, synthetic_markets


def test_no_planted_effect_loses_costs_and_planted_effect_is_found():
    cfg = ResearchConfig()
    null = evaluate(*synthetic_markets(noise=0.0, seed=1), cfg)
    strong = evaluate(*synthetic_markets(noise=0.04, seed=1), cfg)
    assert null["mean_ret_per_trade"] < 0
    assert strong["mean_ret_per_trade"] > 0.03 and strong["t_stat_clustered"] > 4


def test_fair_value_uses_only_past_prices():
    p = np.r_[np.full(30, 0.5), 0.6, np.full(30, 0.5)]
    trades = market_trades(p, 0, ResearchConfig(min_edge=0.02, horizon=5, cost=0.0))
    assert trades[0]["t"] == 30 and trades[0]["side"] == "NO"
    assert abs(trades[0]["ret"] - (0.5 - 0.4) / 0.4) < 1e-12


def test_trade_held_into_resolution_pays_outcome():
    p = np.r_[np.full(25, 0.5), 0.40, 0.40, 0.40]
    tr = market_trades(p, 1, ResearchConfig(min_edge=0.02, horizon=24, cost=0.01))
    assert tr[0]["held_to_resolution"] and tr[0]["side"] == "YES"
    assert abs(tr[0]["ret"] - (1 - 0.41) / 0.41) < 1e-12


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        if url.endswith("/markets"):
            if params["offset"] > 0:
                return Resp([])
            return Resp([
                {"id": "1", "question": "A?", "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps(["1", "0"]),
                 "clobTokenIds": json.dumps(["tokA", "tokA2"]), "closedTime": "2025-03-01 12:00:00+00", "volumeNum": 1e6},
                {"id": "2", "question": "B?", "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps(["0.5", "0.5"]),
                 "clobTokenIds": json.dumps(["tokB", "tokB2"]), "closedTime": "2025-03-01T00:00:00Z"},
                {"id": "3", "question": "C?", "outcomes": json.dumps(["Trump", "Harris"]), "outcomePrices": json.dumps(["1", "0"]),
                 "clobTokenIds": json.dumps(["tokC", "tokC2"]), "closedTime": "2025-03-01T00:00:00Z"},
            ])
        t0 = int(pd.Timestamp("2025-02-20", tz="UTC").timestamp())
        if "interval" in params:
            return Resp({"history": []})
        if params["startTs"] > t0 + 10 * 86400:
            return Resp({"history": []})
        return Resp({"history": [{"t": t0 + 3600 * i, "p": 0.5} for i in range(60)]})


class Resp:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


def test_fetch_dataset_keeps_resolved_binary_markets_and_falls_back_to_windows(monkeypatch):
    monkeypatch.setattr(history.time, "sleep", lambda s: None)
    s = FakeSession()
    prices, markets = history.fetch_dataset(n_markets=10, progress=None, session=s)
    assert list(markets["market_id"]) == ["1"]
    assert markets["outcome"].iloc[0] == 1
    assert len(prices) == 60 and set(prices["market_id"]) == {"1"}
    assert any("startTs" in p for _, p in s.calls)


def test_paper_scan_warms_up_from_history(monkeypatch):
    from polymarket_bot.config import Settings
    from polymarket_bot.engine import TradingEngine

    class B:
        def submit(self, s):
            pass

    eng = TradingEngine(Settings(min_edge=0.03), B())
    monkeypatch.setattr(eng.data, "markets", lambda n: [{"id": "m1", "question": "Q?", "_token_id": "tok"}])
    book = {"bids": [{"price": "0.40", "size": "500"}], "asks": [{"price": "0.42", "size": "500"}]}
    monkeypatch.setattr(eng.data, "orderbook", lambda t: book)
    hist = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=30, freq="h", tz="UTC"), "price": 0.60})
    monkeypatch.setattr(history, "fetch_price_history", lambda *a, **k: hist)
    signals = eng.scan()
    assert len(signals) == 1 and signals[0].side == "BUY" and signals[0].fair_value > 0.44
