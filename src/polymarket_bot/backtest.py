from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd

from .config import Settings
from .strategy import MarketAnalyzer


@dataclass
class BacktestResult:
    starting_cash: float
    ending_cash: float
    total_return: float
    trades: int
    win_rate: float
    max_drawdown: float
    sharpe: float
    t_stat: float

    def as_dict(self):
        return asdict(self)


class BacktestEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, frame: pd.DataFrame) -> BacktestResult:
        required = {"timestamp", "market_id", "price"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        df = frame.copy().sort_values(["market_id", "timestamp"]).reset_index(drop=True)
        df["next_price"] = df.groupby("market_id")["price"].shift(-1)
        analyzer = MarketAnalyzer(self.settings.reversion_window, self.settings.reversion_strength)
        cash = self.settings.starting_cash
        equity = [cash]
        trade_returns = []
        trades = wins = 0

        for _, row in df.iterrows():
            price = float(row.price)
            next_price = row.next_price
            if not 0 < price < 1 or pd.isna(next_price):
                continue
            market_id = str(row.market_id)
            fair = analyzer.fair_value(market_id, price)
            analyzer.record_price(market_id, price)
            edge = fair - price
            if edge < self.settings.min_edge or not self.settings.min_probability <= fair <= self.settings.max_probability:
                equity.append(cash)
                continue
            dollars = analyzer.fractional_kelly(
                fair, price, min(cash, self.settings.max_position_size), self.settings.kelly_fraction
            )
            if dollars < 1 or dollars > cash:
                equity.append(cash)
                continue
            shares = dollars / price
            liquidation = shares * float(next_price)
            pnl = liquidation - dollars
            cash += pnl
            trades += 1
            wins += int(pnl > 0)
            trade_returns.append(pnl / dollars)
            equity.append(cash)

        curve = pd.Series(equity, dtype=float)
        peaks = curve.cummax()
        drawdown = ((curve - peaks) / peaks).min() if len(curve) else 0.0
        returns = pd.Series(trade_returns, dtype=float)
        valid = len(returns) >= 2 and returns.std(ddof=1) > 0
        sharpe = float(returns.mean() / returns.std(ddof=1)) if valid else 0.0
        t_stat = sharpe * math.sqrt(len(returns)) if valid else 0.0
        return BacktestResult(
            starting_cash=self.settings.starting_cash,
            ending_cash=float(cash),
            total_return=float((cash / self.settings.starting_cash) - 1),
            trades=trades,
            win_rate=(wins / trades if trades else 0.0),
            max_drawdown=float(drawdown),
            sharpe=sharpe,
            t_stat=t_stat,
        )


def load_price_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df
