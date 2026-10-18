from __future__ import annotations

import argparse
import logging

from .backtest import BacktestEngine, load_price_csv
from .broker import LiveBroker, PaperBroker
from .config import Settings, load_env
from .engine import TradingEngine


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Polymarket quantitative trading framework")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--mode", choices=["demo", "paper", "live"], default=None)
    run.add_argument("--once", action="store_true")
    bt = sub.add_parser("backtest")
    bt.add_argument("csv")
    fh = sub.add_parser("fetch-history")
    fh.add_argument("--markets", type=int, default=300)
    fh.add_argument("--min-volume", type=float, default=50_000)
    fh.add_argument("--since", default="2024-01-01")
    fh.add_argument("--out-dir", default="data/polymarket")
    rs = sub.add_parser("research")
    rs.add_argument("--synthetic", action="store_true")
    rs.add_argument("--data-dir", default="data/polymarket")
    rs.add_argument("--min-edge", type=float, default=0.02)
    rs.add_argument("--horizon", type=int, default=24)
    rs.add_argument("--cost", type=float, default=0.01)
    args = parser.parse_args(argv)
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    if args.command == "fetch-history":
        _fetch(args)
        return
    if args.command == "research":
        _research(args, settings)
        return
    if args.command == "backtest":
        result = BacktestEngine(settings).run(load_price_csv(args.csv))
        for k, v in result.as_dict().items():
            print(f"{k}: {v}")
        return
    mode = args.mode or settings.mode
    if mode == "demo":
        from .demo import demo
        demo(settings)
        return
    broker = (LiveBroker(settings.private_key, settings.chain_id, settings.live_confirmation)
              if mode == "live" else PaperBroker(settings.db_path))
    engine = TradingEngine(settings, broker)
    if args.once:
        signals = engine.scan()
        print(f"signals={len(signals)}")
        if mode in {"paper", "live"}:
            print(f"executed={engine.execute(signals)}")
    else:
        engine.run_forever()

def _fetch(args) -> None:
    from pathlib import Path

    from .history import fetch_dataset
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Fetching up to {args.markets} resolved yes/no markets (volume >= {args.min_volume:,.0f}, ended after {args.since})...")
    prices, markets = fetch_dataset(args.markets, args.min_volume, args.since)
    prices.to_csv(out / "prices.csv", index=False)
    markets.to_csv(out / "markets.csv", index=False)
    print(f"{len(markets)} markets, {len(prices):,} hourly prices -> {out}/prices.csv, {out}/markets.csv")


def _research(args, settings: Settings) -> None:
    from pathlib import Path

    import pandas as pd

    from .research import ResearchConfig, evaluate, format_report, synthetic_markets
    cfg = ResearchConfig(window=settings.reversion_window, strength=settings.reversion_strength,
                         min_edge=args.min_edge, horizon=args.horizon, cost=args.cost)
    if args.synthetic:
        print("SYNTHETIC markets: true probability is a martingale; the traded price adds a transient error that decays.")
        print(f"Rule: trade when mean-reversion fair value differs from price by {cfg.min_edge:.2f}, "
              f"exit after {cfg.horizon}h, cost {cfg.cost:.2f} per side.\n")
        for noise in (0.0, 0.02, 0.04):
            prices, markets = synthetic_markets(noise=noise, seed=1)
            r = evaluate(prices, markets, cfg)
            print(f"planted overreaction sd={noise:.2f}: trades={r['trades']:5d}  mean net return/trade={r.get('mean_ret_per_trade', 0):+.3f}  "
                  f"hit rate={r.get('hit_rate', 0):.2f}  t (clustered by market)={r.get('t_stat_clustered', 0):+.2f}")
        return
    d = Path(args.data_dir)
    if not (d / "prices.csv").exists() or not (d / "markets.csv").exists():
        raise SystemExit(f"No data in {d}/. Run: polymarket-bot fetch-history   (or use --synthetic)")
    r = evaluate(pd.read_csv(d / "prices.csv"), pd.read_csv(d / "markets.csv"), cfg)
    print(f"Mean-reversion rule on {r['markets']} resolved Polymarket markets, min edge {cfg.min_edge:.2f}, "
          f"exit after {cfg.horizon}h or at resolution, cost {cfg.cost:.2f} per side\n")
    print(format_report(r))
    r["_trades"].to_csv(d / "trades.csv", index=False)
    print(f"\ntrades: {d}/trades.csv")


if __name__ == "__main__":
    main()
