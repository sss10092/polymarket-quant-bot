from __future__ import annotations

import logging
import time

from .broker import Broker
from .config import Settings
from .data import PolymarketDataClient
from .strategy import Signal, ValueBettingStrategy

log = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self, settings: Settings, broker: Broker):
        self.settings = settings
        self.data = PolymarketDataClient(settings.gamma_url, settings.clob_url)
        self.strategy = ValueBettingStrategy(settings)
        self.broker = broker
        self.cash = settings.starting_cash

    def scan(self) -> list[Signal]:
        markets = self.data.markets(self.settings.max_markets)
        signals: list[Signal] = []
        for market in markets:
            token_id = market.get("_token_id") or self.data.extract_yes_token_id(market)
            if not token_id:
                continue
            market = {**market, "token_id": token_id}
            self._warm_up(market, str(token_id))
            book = self.data.orderbook(str(token_id))
            signal = self.strategy.signal(market, book)
            if signal and signal.notional <= self.cash and signal.notional <= self.settings.max_portfolio_risk:
                signals.append(signal)
        return signals

    def _warm_up(self, market: dict, token_id: str) -> None:
        market_id = str(market.get("id") or market.get("condition_id") or market.get("conditionId") or "")
        analyzer = self.strategy.analyzer
        if not market_id or len(analyzer.history[market_id]) >= 3:
            return
        try:
            from .history import fetch_price_history
            h = fetch_price_history(token_id, fidelity=60, clob_url=self.settings.clob_url)
        except Exception as exc:
            log.warning("price history warm-up failed for %s: %s", market_id, exc)
            return
        for p in h["price"].tail(self.settings.reversion_window).to_numpy()[:-1]:
            analyzer.record_price(market_id, float(p))

    def execute(self, signals: list[Signal]) -> int:
        count = 0
        for signal in signals:
            if signal.notional > self.cash:
                continue
            fill = self.broker.submit(signal)
            self.cash -= signal.notional
            count += 1
            log.info("%s %s %.4f x %.2f (%s)", signal.side, signal.token_id, signal.price, signal.size, fill.order_id)
        return count

    def run_forever(self) -> None:
        while True:
            try:
                signals = self.scan()
                log.info("scan complete: %d signals", len(signals))
                if self.settings.mode in {"paper", "live"}:
                    self.execute(signals)
            except Exception:
                log.exception("scan cycle failed")
            time.sleep(self.settings.scan_interval)
