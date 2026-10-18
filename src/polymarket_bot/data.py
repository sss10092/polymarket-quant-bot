from __future__ import annotations

import json
import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class PolymarketDataClient:
    def __init__(self, gamma_url: str, clob_url: str, timeout: float = 10.0):
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-quant-bot/1.0"})

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def markets(self, limit: int = 25) -> list[dict]:
        payload = self._get(
            f"{self.gamma_url}/markets",
            {"active": "true", "closed": "false", "limit": limit},
        )
        markets = payload if isinstance(payload, list) else payload.get("data", [])
        for market in markets:
            market["_token_id"] = self.extract_yes_token_id(market)
        return markets

    @staticmethod
    def extract_yes_token_id(market: dict) -> str | None:
        direct = market.get("token_id")
        if direct:
            return str(direct)
        raw = market.get("clobTokenIds") or market.get("clob_token_ids")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = [raw]
        if isinstance(raw, list) and raw:
            return str(raw[0])
        tokens = market.get("tokens")
        if isinstance(tokens, list):
            for token in tokens:
                outcome = str(token.get("outcome", "")).lower()
                if outcome in {"yes", "true", "1"} and token.get("token_id"):
                    return str(token["token_id"])
        return None

    def orderbook(self, token_id: str) -> dict:
        try:
            payload = self._get(f"{self.clob_url}/book", {"token_id": token_id})
            return payload if isinstance(payload, dict) else {"bids": [], "asks": []}
        except requests.RequestException as exc:
            log.warning("orderbook request failed for %s: %s", token_id, exc)
            return {"bids": [], "asks": []}
