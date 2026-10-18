from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

from .config import Settings


@dataclass(frozen=True)
class Signal:
    token_id: str
    market_name: str
    side: str
    price: float
    size: float
    edge: float
    fair_value: float
    market_price: float

    @property
    def notional(self) -> float:
        return self.price * self.size


class MarketAnalyzer:
    def __init__(self, window: int = 20, strength: float = 0.30):
        self.window = window
        self.strength = strength
        self.history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))

    def record_price(self, market_id: str, price: float) -> None:
        if 0 < price < 1:
            self.history[market_id].append(float(price))

    @staticmethod
    def orderbook_stats(orderbook: dict) -> dict[str, float]:
        bids = sorted(orderbook.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
        asks = sorted(orderbook.get("asks", []), key=lambda x: float(x["price"]))
        if not bids or not asks:
            return {"bid": 0.0, "ask": 1.0, "mid": 0.5, "spread": 1.0, "depth": 0.0, "imbalance": 0.0}
        bid, ask = float(bids[0]["price"]), float(asks[0]["price"])
        bid_depth = sum(float(x.get("size", 0)) for x in bids[:10])
        ask_depth = sum(float(x.get("size", 0)) for x in asks[:10])
        total = bid_depth + ask_depth
        return {
            "bid": bid, "ask": ask, "mid": (bid + ask) / 2,
            "spread": ask - bid, "depth": total,
            "imbalance": (bid_depth - ask_depth) / total if total else 0.0,
        }

    def fair_value(self, market_id: str, current_price: float) -> float:
        history = self.history[market_id]
        if len(history) < 3:
            return current_price
        mean = sum(history) / len(history)
        value = (1 - self.strength) * current_price + self.strength * mean
        return min(0.999, max(0.001, value))

    @staticmethod
    def fractional_kelly(prob: float, price: float, bankroll: float, fraction: float) -> float:
        if not (0 < prob < 1 and 0 < price < 1):
            return 0.0
        b = (1 / price) - 1
        if b <= 0:
            return 0.0
        k = max(0.0, (prob * b - (1 - prob)) / b)
        return bankroll * k * fraction


class ValueBettingStrategy:
    name = "value"

    def __init__(self, settings: Settings, analyzer: MarketAnalyzer | None = None):
        self.settings = settings
        self.analyzer = analyzer or MarketAnalyzer(settings.reversion_window, settings.reversion_strength)

    def signal(self, market: dict, orderbook: dict) -> Optional[Signal]:
        stats = self.analyzer.orderbook_stats(orderbook)
        if stats["spread"] > self.settings.max_spread or stats["depth"] < self.settings.min_depth:
            return None
        market_id = str(market.get("id") or market.get("condition_id") or market.get("conditionId") or "")
        if not market_id:
            return None
        current = stats["mid"]
        self.analyzer.record_price(market_id, current)
        fair = self.analyzer.fair_value(market_id, current)
        if not self.settings.min_probability <= fair <= self.settings.max_probability:
            return None
        edge = abs(fair - current)
        if edge < self.settings.min_edge:
            return None
        if fair <= current:
            return None
        side, price, probability = "BUY", stats["ask"], fair
        dollars = self.analyzer.fractional_kelly(
            probability, price, self.settings.max_position_size, self.settings.kelly_fraction
        )
        dollars = min(dollars, self.settings.max_position_size)
        if dollars < 1 or price <= 0:
            return None
        return Signal(
            token_id=str(market.get("token_id") or market.get("_token_id") or market.get("id")),
            market_name=str(market.get("question") or market.get("title") or "unknown"),
            side=side, price=price, size=dollars / price,
            edge=edge, fair_value=fair, market_price=current,
        )
