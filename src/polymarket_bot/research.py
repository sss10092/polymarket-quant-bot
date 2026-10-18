from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ResearchConfig:
    window: int = 20
    strength: float = 0.30
    min_edge: float = 0.02
    horizon: int = 24
    cost: float = 0.01
    min_price: float = 0.05
    max_price: float = 0.95


def fair_values(p: np.ndarray, window: int, strength: float) -> np.ndarray:
    s = pd.Series(p)
    past_mean = s.rolling(window).mean().shift(1).to_numpy()
    return (1 - strength) * p + strength * past_mean


def market_trades(p: np.ndarray, outcome: int, cfg: ResearchConfig) -> list[dict]:
    fair = fair_values(p, cfg.window, cfg.strength)
    last = len(p) - 1
    trades, t = [], cfg.window
    while t < last:
        edge = fair[t] - p[t]
        if not (cfg.min_price <= p[t] <= cfg.max_price) or abs(edge) < cfg.min_edge:
            t += 1
            continue
        exit_t = t + cfg.horizon
        resolved = exit_t >= last
        long_yes = edge > 0
        entry = (p[t] if long_yes else 1 - p[t]) + cfg.cost
        if resolved:
            value = outcome if long_yes else 1 - outcome
        else:
            value = (p[exit_t] if long_yes else 1 - p[exit_t]) - cfg.cost
        trades.append({"t": t, "side": "YES" if long_yes else "NO", "entry": entry, "ret": (value - entry) / entry,
                       "held_to_resolution": resolved, "edge": edge})
        t = min(exit_t, last)
    return trades


def snapshot_brier(p: np.ndarray, ts: pd.Series, end_ts, outcome: int, cfg: ResearchConfig, hours_before: int):
    cutoff = pd.Timestamp(end_ts) - pd.Timedelta(hours=hours_before)
    idx = int(ts.searchsorted(cutoff, side="right")) - 1
    if idx < cfg.window:
        return None
    fair = fair_values(p[: idx + 1], cfg.window, cfg.strength)[idx]
    return (p[idx] - outcome) ** 2, (np.clip(fair, 0, 1) - outcome) ** 2


def evaluate(prices: pd.DataFrame, markets: pd.DataFrame, cfg: ResearchConfig | None = None) -> dict:
    cfg = cfg or ResearchConfig()
    prices = prices.assign(timestamp=pd.to_datetime(prices["timestamp"], utc=True), market_id=prices["market_id"].astype(str))
    markets = markets.assign(market_id=markets["market_id"].astype(str), end_ts=pd.to_datetime(markets["end_ts"], utc=True))
    meta = markets.set_index("market_id")
    rows, brier = [], {24: [], 168: []}
    for mid, g in prices.sort_values("timestamp").groupby("market_id"):
        if mid not in meta.index:
            continue
        p = g["price"].to_numpy(float)
        outcome = int(meta.at[mid, "outcome"])
        for tr in market_trades(p, outcome, cfg):
            rows.append({"market_id": mid, **tr})
        for h in brier:
            b = snapshot_brier(p, g["timestamp"].reset_index(drop=True), meta.at[mid, "end_ts"], outcome, cfg, h)
            if b:
                brier[h].append(b)
    trades = pd.DataFrame(rows, columns=["market_id", "t", "side", "entry", "ret", "held_to_resolution", "edge"])
    out = {"markets": int(prices["market_id"].nunique()), "trades": len(trades)}
    if len(trades):
        per_market = trades.groupby("market_id")["ret"].mean()
        m = len(per_market)
        se = per_market.std(ddof=1) / np.sqrt(m) if m > 1 else np.nan
        out.update({
            "markets_traded": m,
            "mean_ret_per_trade": float(trades["ret"].mean()),
            "hit_rate": float((trades["ret"] > 0).mean()),
            "share_held_to_resolution": float(trades["held_to_resolution"].mean()),
            "mean_ret_per_market": float(per_market.mean()),
            "t_stat_clustered": float(per_market.mean() / se) if se and np.isfinite(se) and se > 0 else 0.0,
        })
    for h, vals in brier.items():
        if vals:
            a = np.array(vals)
            out[f"brier_market_{h}h"] = float(a[:, 0].mean())
            out[f"brier_model_{h}h"] = float(a[:, 1].mean())
    out["_trades"] = trades
    return out


def synthetic_markets(n_markets: int = 200, hours: int = 720, noise: float = 0.03, phi: float = 0.9,
                      vol: float = 0.04, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    frames, meta = [], []
    for i in range(n_markets):
        q = np.empty(hours)
        q[0] = rng.uniform(0.15, 0.85)
        for t in range(1, hours):
            q[t] = np.clip(q[t - 1] + vol * q[t - 1] * (1 - q[t - 1]) * rng.standard_normal(), 0.001, 0.999)
        e = np.zeros(hours)
        sd = noise * np.sqrt(1 - phi**2)
        for t in range(1, hours):
            e[t] = phi * e[t - 1] + sd * rng.standard_normal()
        p = np.clip(q + e, 0.01, 0.99)
        outcome = int(rng.random() < q[-1])
        ts = t0 + pd.to_timedelta(np.arange(hours) + i * 24, unit="h")
        frames.append(pd.DataFrame({"timestamp": ts, "market_id": f"syn{i}", "price": p}))
        meta.append({"market_id": f"syn{i}", "question": "synthetic", "outcome": outcome, "end_ts": ts[-1]})
    return pd.concat(frames, ignore_index=True), pd.DataFrame(meta)


def format_report(res: dict) -> str:
    keys = ["markets", "markets_traded", "trades", "mean_ret_per_trade", "hit_rate", "share_held_to_resolution",
            "mean_ret_per_market", "t_stat_clustered", "brier_market_24h", "brier_model_24h", "brier_market_168h", "brier_model_168h"]
    lines = []
    for k in keys:
        if k in res:
            v = res[k]
            lines.append(f"{k:26s} {v:.4f}" if isinstance(v, float) else f"{k:26s} {v}")
    return "\n".join(lines)
