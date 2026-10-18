from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .strategy import Signal

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fill:
    order_id: str
    status: str
    side: str
    price: float
    size: float
    timestamp: str


class Broker(Protocol):
    def submit(self, signal: Signal) -> Fill: ...


class PaperBroker:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS fills(
                order_id TEXT PRIMARY KEY, timestamp TEXT, market TEXT, token_id TEXT,
                side TEXT, price REAL, size REAL, status TEXT, edge REAL, fair_value REAL
            )""")

    def submit(self, signal: Signal) -> Fill:
        now = datetime.now(timezone.utc).isoformat()
        oid = f"paper-{int(datetime.now(timezone.utc).timestamp()*1_000_000)}"
        fill = Fill(oid, "filled", signal.side, signal.price, signal.size, now)
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?)", (
                oid, now, signal.market_name, signal.token_id, signal.side,
                signal.price, signal.size, "filled", signal.edge, signal.fair_value,
            ))
        return fill


class LiveBroker:
    def __init__(self, private_key: str, chain_id: int, confirmation: str):
        if confirmation != "I_UNDERSTAND_LIVE_RISK":
            raise RuntimeError("Live broker requires explicit risk confirmation")
        self.private_key = private_key
        self.chain_id = chain_id
        self._client = None

    def _client_sync(self):
        if self._client is None:
            from polymarket import SecureClient
            self._client = SecureClient.create(private_key=self.private_key)
        return self._client

    def submit(self, signal: Signal) -> Fill:
        client = self._client_sync()
        side = signal.side
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported side: {side}")
        response = client.place_limit_order(
            token_id=signal.token_id,
            price=signal.price,
            size=signal.size,
            side=side,
        )
        order_id = getattr(response, "order_id", None) or getattr(response, "id", None) or str(response)
        return Fill(
            str(order_id), "submitted", side, signal.price, signal.size,
            datetime.now(timezone.utc).isoformat(),
        )
