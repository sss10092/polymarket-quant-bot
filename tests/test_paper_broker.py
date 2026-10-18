from polymarket_bot.broker import PaperBroker
from polymarket_bot.strategy import Signal


def test_paper_fill(tmp_path):
    broker = PaperBroker(str(tmp_path / "fills.db"))
    fill = broker.submit(Signal("t", "market", "BUY", .5, 10, .1, .6, .5))
    assert fill.status == "filled"
