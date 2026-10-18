# Polymarket Quant Bot

A research, backtesting and paper-trading framework for Polymarket, with a live-execution adapter that is off by default.

## What it does

1. Pulls markets and order books from the public Gamma and CLOB APIs.
2. Estimates fair value with a simple mean-reversion model.
3. Filters signals on spread and order-book depth.
4. Sizes positions with fractional Kelly and hard position limits.
5. Paper trades and stores fills in SQLite.
6. Backtests from a price CSV.
7. Live trading needs both `POLYMARKET_LIVE_TRADING=true` and `POLYMARKET_LIVE_CONFIRMATION=I_UNDERSTAND_LIVE_RISK`.

## Does the signal work?

The fair value is a blend of the current price and its recent average, so the strategy bets that moves reverse. `research` tests that on hourly price histories of resolved markets. Each trade buys YES or NO, exits after 24 hours (or takes the resolution payoff if the market closes first), and pays 1 cent per side for the spread. Returns are averaged per market before the t-stat, since trades in the same market are not independent.

Synthetic check (`research --synthetic`), 200 markets where the true probability is a martingale and the traded price adds a decaying error of known size:

| Planted overreaction | Trades | Net return per trade | Hit rate | t (by market) |
|---|---|---|---|---|
| none | 192 | -4.3% | 33% | -3.1 |
| 2 cents | 731 | +1.0% | 48% | +0.4 |
| 4 cents | 2794 | +7.1% | 62% | +9.2 |

With no overreaction the rule loses roughly its trading costs, and it only makes money once the overreaction is larger than the spread. Run `fetch-history` then `research` to see which case real Polymarket markets look like.

`run --mode paper` pulls each market's recent hourly prices before the first scan, so `--once` can produce signals.

## Run

```bash
pip install -e '.[dev]'
pytest -q
polymarket-bot research --synthetic
polymarket-bot fetch-history --markets 300
polymarket-bot research
cp .env.example .env
polymarket-bot run --mode paper --once
```

`fetch-history` uses the public Gamma and CLOB APIs, needs no key, and takes about 5 to 10 minutes for 300 markets. It writes data/polymarket/prices.csv and markets.csv.

Docker: `docker compose up --build`. For live trading, install `.[live]` and set the private key through the environment, never in git.
