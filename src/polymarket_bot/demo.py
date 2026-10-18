from __future__ import annotations

import numpy as np

from .config import Settings
from .strategy import MarketAnalyzer


def demo(settings: Settings) -> None:
    analyzer = MarketAnalyzer(settings.reversion_window, settings.reversion_strength)
    rng = np.random.default_rng(7)
    for market_id, baseline, current in [("demo-1", .42, .68), ("demo-2", .62, .45), ("demo-3", .35, .51)]:
        for p in np.clip(baseline + rng.normal(0, .01, settings.reversion_window), .02, .98):
            analyzer.record_price(market_id, float(p))
        fair = analyzer.fair_value(market_id, current)
        edge = fair - current
        print(f"{market_id}: market={current:.3f} fair={fair:.3f} edge={edge:+.3f}")
    print("\nThis only shows the fair-value calculation. For a test with trades run: polymarket-bot research --synthetic")
