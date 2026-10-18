from __future__ import annotations

import json
import time
from typing import Callable

import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def _get(url: str, params: dict, retries: int = 4, session=None):
    s = session or requests
    for attempt in range(retries):
        r = s.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"{url} kept failing after {retries} attempts")


def _as_list(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, list) else []
        except json.JSONDecodeError:
            return []
    return []


def parse_resolved_market(m: dict) -> dict | None:
    outcomes = [str(x).strip().lower() for x in _as_list(m.get("outcomes"))]
    prices = _as_list(m.get("outcomePrices"))
    tokens = _as_list(m.get("clobTokenIds"))
    if outcomes != ["yes", "no"] or len(prices) != 2 or len(tokens) != 2:
        return None
    try:
        p_yes = float(prices[0])
    except (TypeError, ValueError):
        return None
    if p_yes not in (0.0, 1.0):
        return None
    end = m.get("closedTime") or m.get("endDate")
    if not end:
        return None
    return {
        "market_id": str(m.get("id")),
        "question": str(m.get("question") or ""),
        "yes_token": str(tokens[0]),
        "outcome": int(p_yes == 1.0),
        "end_ts": pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tzinfo else pd.Timestamp(end, tz="UTC"),
        "start_ts": pd.Timestamp(m["startDate"]).tz_convert("UTC") if m.get("startDate") else None,
        "volume": float(m.get("volumeNum") or 0.0),
    }


def fetch_resolved_markets(n: int = 300, min_volume: float = 50_000, end_after: str = "2024-01-01",
                           gamma_url: str = GAMMA, progress: Callable | None = print, session=None) -> pd.DataFrame:
    rows, offset, page = [], 0, 100
    while len(rows) < n:
        batch = _get(f"{gamma_url}/markets", {"closed": "true", "limit": page, "offset": offset, "order": "volumeNum",
                                               "ascending": "false", "volume_num_min": min_volume,
                                               "end_date_min": f"{end_after}T00:00:00Z"}, session=session)
        batch = batch if isinstance(batch, list) else batch.get("data", [])
        if not batch:
            break
        for m in batch:
            r = parse_resolved_market(m)
            if r:
                rows.append(r)
        offset += page
        if progress:
            progress(f"  scanned {offset} closed markets, {len(rows)} resolved yes/no kept")
        time.sleep(0.2)
    return pd.DataFrame(rows[:n])


def fetch_price_history(token_id: str, start_ts=None, end_ts=None, fidelity: int = 60,
                        clob_url: str = CLOB, session=None) -> pd.DataFrame:
    data = _get(f"{clob_url}/prices-history", {"market": token_id, "interval": "max", "fidelity": fidelity},
                session=session).get("history", [])
    if not data and end_ts is not None:
        end = pd.Timestamp(end_ts)
        start = pd.Timestamp(start_ts) if start_ts is not None else end - pd.Timedelta(days=120)
        t = start
        while t < end:
            t2 = min(t + pd.Timedelta(days=14), end)
            chunk = _get(f"{clob_url}/prices-history", {"market": token_id, "startTs": int(t.timestamp()),
                                                         "endTs": int(t2.timestamp()), "fidelity": fidelity},
                         session=session).get("history", [])
            data.extend(chunk)
            t = t2
            time.sleep(0.1)
    if not data:
        return pd.DataFrame(columns=["timestamp", "price"])
    df = pd.DataFrame(data).rename(columns={"t": "timestamp", "p": "price"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp")[["timestamp", "price"]]


def fetch_dataset(n_markets: int = 300, min_volume: float = 50_000, end_after: str = "2024-01-01",
                  progress: Callable | None = print, session=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    markets = fetch_resolved_markets(n_markets, min_volume, end_after, progress=progress, session=session)
    frames, kept = [], []
    for i, m in enumerate(markets.itertuples()):
        h = fetch_price_history(m.yes_token, m.start_ts, m.end_ts, session=session)
        h = h[h["timestamp"] <= m.end_ts]
        if len(h) >= 48:
            frames.append(h.assign(market_id=m.market_id))
            kept.append(m.market_id)
        if progress and (i + 1) % 25 == 0:
            progress(f"  price histories {i + 1}/{len(markets)}, {len(kept)} with 48+ hourly points")
        time.sleep(0.15)
    prices = pd.concat(frames, ignore_index=True)[["timestamp", "market_id", "price"]] if frames else \
        pd.DataFrame(columns=["timestamp", "market_id", "price"])
    return prices, markets[markets["market_id"].isin(kept)].reset_index(drop=True)
