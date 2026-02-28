#!/usr/bin/env python3
"""
Fetch BTC/USD historical data and save to CSV.

Every run creates a new timestamped file in data/ so you can
collect datasets for different periods and compare them.

Usage
-----
    python fetch_data.py                          # default: 3M ending today
    python fetch_data.py --period 6M
    python fetch_data.py --start 2024-01-01       # 3M starting Jan 2024
    python fetch_data.py --start 2023-06-15 --period 1Y --timeframe 1d
    python fetch_data.py --list                   # show saved files
"""

import argparse
import os
import sys
from datetime import datetime

from data_manager import DataManager

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def list_datasets() -> None:
    """Print all CSV files in data/ with size and row count."""
    os.makedirs(DATA_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))

    if not files:
        print("No datasets found in data/. Run this script to fetch some.")
        return

    print(f"\n  Saved datasets in data/")
    print(f"  {'-'*60}")

    for f in files:
        path = os.path.join(DATA_DIR, f)
        size_kb = os.path.getsize(path) / 1024
        # quick row count without loading full df
        with open(path) as fh:
            rows = sum(1 for _ in fh) - 1  # minus header
        print(f"  {f:<45} {rows:>6} rows  {size_kb:>7.0f} KB")
    print()


def fetch_and_save(period: str, timeframe: str, start_date: str = None):
    """Fetch data and save to data/ with a descriptive filename."""
    dm = DataManager(timeframe=timeframe)

    print()
    df = dm.fetch(period, start_date=start_date)

    if df.empty:
        return None

    # Validate
    report = dm.validate(df)
    if not report["valid"]:
        print(f"⚠  Quality warnings: {report['issues']}")
    else:
        print(f"Data quality: OK (score {report['score']}/100)")

    # Build filename
    # With start date:  BTC-USD_1h_3M_20240101.csv  (date = start)
    # Without:          BTC-USD_1h_3M_20260228.csv  (date = today)
    if start_date:
        date_tag = start_date.replace("-", "")
    else:
        date_tag = datetime.now().strftime("%Y%m%d")
    filename = f"BTC-USD_{timeframe}_{period.upper()}_{date_tag}.csv"
    filepath = os.path.join(DATA_DIR, filename)

    dm.save(filepath)

    # Print summary
    s = dm.summary(df)
    print(f"\n  Summary")
    print(f"  {'-'*40}")
    print(f"  {'Candles':<20} {s['candles']:,}")
    print(f"  {'Date range':<20} {s['start'][:10]} → {s['end'][:10]}")
    print(f"  {'Days':<20} {s['days']}")
    print(f"  {'Price range':<20} ${s['price_low']:,.0f} – ${s['price_high']:,.0f}")
    print(f"  {'Last close':<20} ${s['last_close']:,.0f}")
    print(f"  {'Volatility':<20} {s['volatility_pct']:.2f} % per candle")
    print()

    return filepath


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch BTC/USD historical data from Yahoo Finance",
    )
    p.add_argument(
        "--period", default="3M",
        help="How far back to fetch: 1W, 2W, 1M, 2M, 3M, 6M, 1Y, 2Y "
             "(default: 3M)",
    )
    p.add_argument(
        "--start", default=None, metavar="YYYY-MM-DD",
        help="Start date (e.g. 2024-01-15). End date = start + period. "
             "If omitted, fetches the most recent data ending today.",
    )
    p.add_argument(
        "--timeframe", default="1h",
        help="Candle size: 15m, 1h, 1d (default: 1h). "
             "Note: 15m max 60 days, 1h max 730 days.",
    )
    p.add_argument(
        "--list", action="store_true", dest="list_files",
        help="List all saved datasets and exit",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    print("BTC/USD Data Fetcher")
    print("=" * 35)

    if args.list_files:
        list_datasets()
        return

    result = fetch_and_save(args.period, args.timeframe, args.start)
    if result is None:
        print("Fetch failed. Check your internet connection or try again.")
        sys.exit(1)

    print(f"Use this file for backtesting:")
    print(f"  python backtest.py --file {result}")


if __name__ == "__main__":
    main()