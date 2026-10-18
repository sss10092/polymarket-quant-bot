import pytest

from polymarket_bot.config import Settings
from polymarket_bot.strategy import MarketAnalyzer, ValueBettingStrategy


def settings(**kwargs):
    base = Settings()
    return Settings(**{**base.__dict__, **kwargs})


def test_mean_reversion_uses_history():
    a = MarketAnalyzer(window=10, strength=.3)
    for _ in range(10):
        a.record_price("m", .30)
    assert a.fair_value("m", .50) < .50


def test_kelly_never_bets_when_no_edge():
    assert MarketAnalyzer.fractional_kelly(.50, .50, 100, .25) == 0


def test_orderbook_sorts_best_levels():
    stats = MarketAnalyzer.orderbook_stats({"bids":[{"price":.4,"size":5},{"price":.45,"size":5}], "asks":[{"price":.6,"size":5},{"price":.55,"size":5}]})
    assert stats["bid"] == .45
    assert stats["ask"] == .55


def test_probability_guard():
    s = ValueBettingStrategy(settings(min_edge=.01))
    book = {"bids":[{"price":.01,"size":100}],"asks":[{"price":.02,"size":100}]}
    assert s.signal({"id":"m","question":"x"}, book) is None


def test_settings_fail_closed_for_live():
    with pytest.raises(ValueError):
        s = settings(mode="live", live_trading=True, live_confirmation="bad", private_key="x")
        s.validate()
