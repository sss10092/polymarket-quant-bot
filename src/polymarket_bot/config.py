from __future__ import annotations

import os
from dataclasses import dataclass


def load_env(path: str = ".env") -> None:
    try:
        lines = open(path).read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip("'").strip('"')
            if v and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mode: str = "paper"
    scan_interval: int = 30
    max_markets: int = 25
    starting_cash: float = 1000.0
    max_position_size: float = 100.0
    max_portfolio_risk: float = 1000.0
    min_edge: float = 0.05
    kelly_fraction: float = 0.25
    min_probability: float = 0.05
    max_probability: float = 0.95
    reversion_window: int = 20
    reversion_strength: float = 0.30
    max_spread: float = 0.05
    min_depth: float = 25.0
    gamma_url: str = "https://gamma-api.polymarket.com"
    clob_url: str = "https://clob.polymarket.com"
    db_path: str = "data/trades.sqlite3"
    live_trading: bool = False
    live_confirmation: str = ""
    private_key: str = ""
    funder: str = ""
    chain_id: int = 137

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls(
            mode=os.getenv("POLYMARKET_MODE", "paper").lower(),
            scan_interval=int(os.getenv("POLYMARKET_SCAN_INTERVAL", "30")),
            max_markets=int(os.getenv("POLYMARKET_MAX_MARKETS", "25")),
            starting_cash=float(os.getenv("POLYMARKET_STARTING_CASH", "1000")),
            max_position_size=float(os.getenv("POLYMARKET_MAX_POSITION", "100")),
            max_portfolio_risk=float(os.getenv("POLYMARKET_MAX_PORTFOLIO_RISK", "1000")),
            min_edge=float(os.getenv("POLYMARKET_MIN_EDGE", "0.05")),
            kelly_fraction=float(os.getenv("POLYMARKET_KELLY_FRACTION", "0.25")),
            min_probability=float(os.getenv("POLYMARKET_MIN_PROBABILITY", "0.05")),
            max_probability=float(os.getenv("POLYMARKET_MAX_PROBABILITY", "0.95")),
            reversion_window=int(os.getenv("POLYMARKET_REVERSION_WINDOW", "20")),
            reversion_strength=float(os.getenv("POLYMARKET_REVERSION_STRENGTH", "0.30")),
            max_spread=float(os.getenv("POLYMARKET_MAX_SPREAD", "0.05")),
            min_depth=float(os.getenv("POLYMARKET_MIN_DEPTH", "25")),
            gamma_url=os.getenv("POLYMARKET_GAMMA_URL", cls.gamma_url),
            clob_url=os.getenv("POLYMARKET_CLOB_URL", cls.clob_url),
            db_path=os.getenv("POLYMARKET_DB_PATH", cls.db_path),
            live_trading=_bool("POLYMARKET_LIVE_TRADING"),
            live_confirmation=os.getenv("POLYMARKET_LIVE_CONFIRMATION", ""),
            private_key=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
            funder=os.getenv("POLYMARKET_FUNDER", ""),
            chain_id=int(os.getenv("POLYMARKET_CHAIN_ID", "137")),
        )
        s.validate()
        return s

    def validate(self) -> None:
        if self.mode not in {"demo", "paper", "live"}:
            raise ValueError("mode must be demo, paper, or live")
        if not 0 < self.kelly_fraction <= 1:
            raise ValueError("kelly_fraction must be in (0, 1]")
        if not 0 < self.min_probability < self.max_probability < 1:
            raise ValueError("probability bounds must satisfy 0 < min < max < 1")
        if self.max_position_size <= 0 or self.max_portfolio_risk <= 0:
            raise ValueError("risk limits must be positive")
        if self.live_trading and self.live_confirmation != "I_UNDERSTAND_LIVE_RISK":
            raise ValueError("live trading requires POLYMARKET_LIVE_CONFIRMATION=I_UNDERSTAND_LIVE_RISK")
        if self.mode == "live" and not self.live_trading:
            raise ValueError("mode=live requires POLYMARKET_LIVE_TRADING=true")
        if self.mode == "live" and not self.private_key:
            raise ValueError("live mode requires POLYMARKET_PRIVATE_KEY")
