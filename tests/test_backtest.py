import pandas as pd

from polymarket_bot.backtest import BacktestEngine
from polymarket_bot.config import Settings


def test_backtest_runs():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=20, freq="h"),
        "market_id": ["m"] * 20,
        "price": [0.40] * 10 + [0.60] * 10,
    })
    result = BacktestEngine(Settings(min_edge=.01)).run(df)
    assert result.trades >= 0
    assert result.starting_cash == 1000
