#!/usr/bin/env python3
"""
BTC/USD RSI-Volume-Wick Strategy Backtester
============================================
Fetches historical Bitcoin data via yfinance, generates trading signals
based on RSI + volume spikes + candlestick wick patterns, and runs a
simulated backtest with configurable risk parameters.

Usage
-----
    # Quick run with bundled sample data:
    python main.py

    # Fetch fresh data and run:
    python main.py --fetch 3M

    # Choose a preset:
    python main.py --preset aggressive

    # Compare all presets:
    python main.py --compare

    # Optimise parameters:
    python main.py --optimise
"""

import argparse
import itertools
import os
import random
import sys

import pandas as pd

from config import PRESETS, SIGNAL_KEYS, BACKTEST_KEYS, DEFAULTS, OPTIMISATION_GRID
from data_manager import DataManager
from strategy_backtester import (
    generate_signals, backtest, performance_metrics, print_metrics,
)


SAMPLE_DATA = os.path.join(os.path.dirname(__file__), "data", "btc_sample_1h.csv")


# ═══════════════════════════════════════════════════════════════════════════
#  Core helpers
# ═══════════════════════════════════════════════════════════════════════════

def load_data(period: str = None, timeframe: str = "1h") -> pd.DataFrame:
    """Return OHLCV data — fetch live if *period* given, else use sample."""
    dm = DataManager(timeframe=timeframe)

    if period:
        try:
            df = dm.fetch(period)
        except RuntimeError as e:
            print(f"✗ {e}")
            df = pd.DataFrame()
        if df.empty:
            print("Falling back to sample data.")
            df = dm.load(SAMPLE_DATA)
    else:
        if os.path.exists(SAMPLE_DATA):
            df = dm.load(SAMPLE_DATA)
        else:
            print(f"Sample file not found at {SAMPLE_DATA}.")
            print("Run with --fetch to download data first.")
            sys.exit(1)

    # validate
    report = dm.validate(df)
    if not report["valid"]:
        print(f"Data quality warnings: {report['issues']}")
    else:
        print(f"Data quality: OK (score {report['score']}/100)")

    return df


def run_single(df: pd.DataFrame, preset_name: str = "moderate",
               show_metrics: bool = True) -> dict:
    """Run one backtest and optionally print results."""
    params = PRESETS.get(preset_name)
    if params is None:
        print(f"Unknown preset '{preset_name}'. Options: {list(PRESETS)}")
        sys.exit(1)

    sig_params = {k: v for k, v in params.items() if k in SIGNAL_KEYS}
    bt_params = {k: v for k, v in params.items() if k in BACKTEST_KEYS}

    signals = generate_signals(df, **sig_params)
    result = backtest(signals, **bt_params)
    metrics = performance_metrics(result)

    if show_metrics:
        print_metrics(metrics)

    return {"signals": signals, "result": result, "metrics": metrics,
            "preset": preset_name}


# ═══════════════════════════════════════════════════════════════════════════
#  Preset comparison
# ═══════════════════════════════════════════════════════════════════════════

def compare_presets(df: pd.DataFrame) -> None:
    """Run every preset on the same data and print a comparison table."""
    print(f"\n{'='*65}")
    print("  PRESET COMPARISON")
    print(f"{'='*65}")

    rows = []
    for name in PRESETS:
        res = run_single(df, name, show_metrics=False)
        m = res["metrics"]
        if "error" in m:
            rows.append((name, "—", "—", "—", "—"))
        else:
            rows.append((
                name,
                f"{m['Total Return (%)']:+.2f} %",
                f"{m['Win Rate (%)']:.1f} %",
                f"{m['Total Trades']}",
                f"{m['Sharpe Ratio']:.2f}",
            ))

    print(f"\n  {'Preset':<16} {'Return':>10} {'Win Rate':>10} "
          f"{'Trades':>8} {'Sharpe':>8}")
    print(f"  {'-'*56}")
    for row in rows:
        print(f"  {row[0]:<16} {row[1]:>10} {row[2]:>10} "
              f"{row[3]:>8} {row[4]:>8}")
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  Parameter optimisation
# ═══════════════════════════════════════════════════════════════════════════

def optimise(df: pd.DataFrame, max_combos: int = 50) -> pd.DataFrame:
    """Grid-search over parameter combinations, ranked by return."""
    keys = list(OPTIMISATION_GRID.keys())
    all_combos = list(itertools.product(*OPTIMISATION_GRID.values()))

    if len(all_combos) > max_combos:
        random.seed(42)
        all_combos = random.sample(all_combos, max_combos)

    print(f"\nOptimising: testing {len(all_combos)} combinations …")

    results = []
    for i, vals in enumerate(all_combos, 1):
        params = dict(zip(keys, vals))
        sig_p = {k: v for k, v in params.items() if k in SIGNAL_KEYS}
        bt_p = {k: v for k, v in params.items() if k in BACKTEST_KEYS}

        signals = generate_signals(df, **sig_p)
        res = backtest(signals, **bt_p)
        m = performance_metrics(res)

        if "error" not in m:
            results.append({**params, **m})

        if i % 10 == 0:
            print(f"  … {i}/{len(all_combos)}")

    if not results:
        print("No valid results found.")
        return pd.DataFrame()

    rdf = pd.DataFrame(results).sort_values("Total Return (%)", ascending=False)

    print(f"\n{'='*65}")
    print(f"  TOP 5 PARAMETER SETS (by return)")
    print(f"{'='*65}\n")
    for i, (_, row) in enumerate(rdf.head().iterrows(), 1):
        print(f"  #{i}  Return {row['Total Return (%)']:+.2f} %  |  "
              f"Win {row['Win Rate (%)']:.0f} %  |  "
              f"Sharpe {row['Sharpe Ratio']:.2f}  |  "
              f"Trades {int(row['Total Trades'])}")
        print(f"      RSI {int(row['rsi_oversold'])}/{int(row['rsi_overbought'])}  "
              f"Vol ×{row['volume_multiplier']:.1f}  "
              f"Wick {row['wick_threshold']:.2f}  "
              f"SL {row['stop_loss']:.3f}  TP {row['take_profit']:.3f}")
    print()

    return rdf


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BTC RSI-Volume-Wick Strategy Backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--fetch", metavar="PERIOD", default=None,
        help="Fetch fresh data from Yahoo Finance. "
             "Periods: 1W, 2W, 1M, 2M, 3M, 6M, 1Y, 2Y",
    )
    p.add_argument(
        "--timeframe", default="1h",
        help="Candle timeframe (default: 1h). "
             "Tip: 1h supports up to 2Y; 15m is limited to 60 days.",
    )
    p.add_argument(
        "--preset", default="moderate", choices=list(PRESETS),
        help="Strategy preset (default: moderate)",
    )
    p.add_argument(
        "--compare", action="store_true",
        help="Compare all presets on the same data",
    )
    p.add_argument(
        "--optimise", action="store_true",
        help="Run parameter optimisation grid search",
    )
    p.add_argument(
        "--save", metavar="PATH", default=None,
        help="Save fetched data to a CSV file",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    print("BTC/USD RSI-Volume-Wick Strategy Backtester")
    print("=" * 45)

    # ── load data ────────────────────────────────────────────────────
    df = load_data(args.fetch, args.timeframe)

    # ── optionally save ──────────────────────────────────────────────
    if args.save:
        dm = DataManager()
        dm.data = df
        dm.save(args.save)

    # ── run mode ─────────────────────────────────────────────────────
    if args.compare:
        compare_presets(df)
    elif args.optimise:
        optimise(df)
    else:
        run_single(df, args.preset)


if __name__ == "__main__":
    main()
