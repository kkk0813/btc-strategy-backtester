#!/usr/bin/env python3
"""
Run backtests on previously fetched BTC/USD CSV data.

The workflow is: fetch data once with fetch_data.py, then run as many
backtests as you want against the saved CSV — no re-downloading needed.

Usage
-----
    python backtest.py                        # pick from available CSVs
    python backtest.py --file data/xyz.csv    # use a specific file
    python backtest.py --preset aggressive
    python backtest.py --compare              # compare all presets
    python backtest.py --optimise             # parameter grid search
"""

import argparse
import itertools
import os
import random
import sys

import pandas as pd

from config import PRESETS, SIGNAL_KEYS, BACKTEST_KEYS, OPTIMISATION_GRID
from data_manager import DataManager
from strategy_backtester import (
    generate_signals, backtest, performance_metrics, print_metrics,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ═══════════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════════

def discover_csvs() -> list:
    """Return sorted list of CSV paths in data/."""
    os.makedirs(DATA_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
    return [os.path.join(DATA_DIR, f) for f in files]


def pick_file(explicit_path: str = None) -> str:
    """
    Resolve which CSV to use.
    - If explicit_path is given, use it.
    - Otherwise list available files and prompt user to choose.
    """
    if explicit_path:
        if not os.path.exists(explicit_path):
            print(f"✗ File not found: {explicit_path}")
            sys.exit(1)
        return explicit_path

    csvs = discover_csvs()
    if not csvs:
        print("No CSV files found in data/.")
        print("Run  python fetch_data.py  first to download data.")
        sys.exit(1)

    if len(csvs) == 1:
        print(f"Using: {csvs[0]}")
        return csvs[0]

    # Multiple files — let user choose
    print(f"\n  Available datasets:")
    print(f"  {'-'*55}")
    for i, path in enumerate(csvs, 1):
        name = os.path.basename(path)
        size_kb = os.path.getsize(path) / 1024
        print(f"  [{i}] {name:<45} {size_kb:>6.0f} KB")
    print()

    while True:
        try:
            choice = input(f"Select file (1-{len(csvs)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(csvs):
                return csvs[idx]
        except (ValueError, EOFError):
            pass
        print(f"Enter a number between 1 and {len(csvs)}.")


def load_csv(filepath: str) -> pd.DataFrame:
    """Load and validate a CSV file."""
    dm = DataManager()
    df = dm.load(filepath)

    if df.empty:
        print("✗ File is empty or could not be parsed.")
        sys.exit(1)

    report = dm.validate(df)
    if not report["valid"]:
        print(f"⚠  Quality warnings: {report['issues']}")
    else:
        print(f"Data quality: OK (score {report['score']}/100)")

    return df


# ═══════════════════════════════════════════════════════════════════════════
#  Backtest modes
# ═══════════════════════════════════════════════════════════════════════════

def run_single(df: pd.DataFrame, preset_name: str = "moderate",
               show: bool = True) -> dict:
    """Run one backtest with a named preset."""
    params = PRESETS.get(preset_name)
    if params is None:
        print(f"Unknown preset '{preset_name}'. Options: {list(PRESETS)}")
        sys.exit(1)

    sig_p = {k: v for k, v in params.items() if k in SIGNAL_KEYS}
    bt_p = {k: v for k, v in params.items() if k in BACKTEST_KEYS}

    signals = generate_signals(df, **sig_p)
    result = backtest(signals, **bt_p)
    metrics = performance_metrics(result)

    if show:
        print_metrics(metrics)

    return {"signals": signals, "result": result, "metrics": metrics,
            "preset": preset_name}


def compare_presets(df: pd.DataFrame) -> None:
    """Run every preset and print a comparison table."""
    print(f"\n{'='*65}")
    print("  PRESET COMPARISON")
    print(f"{'='*65}")

    rows = []
    for name in PRESETS:
        res = run_single(df, name, show=False)
        m = res["metrics"]
        if "error" in m:
            rows.append((name, "—", "—", "—", "—"))
        else:
            rows.append((
                name,
                f"{m['Total Return (%)']:+.2f} %",
                f"{m['Win Rate (%)']:.1f} %",
                str(m["Total Trades"]),
                f"{m['Sharpe Ratio']:.2f}",
            ))

    print(f"\n  {'Preset':<16} {'Return':>10} {'Win Rate':>10} "
          f"{'Trades':>8} {'Sharpe':>8}")
    print(f"  {'-'*56}")
    for row in rows:
        print(f"  {row[0]:<16} {row[1]:>10} {row[2]:>10} "
              f"{row[3]:>8} {row[4]:>8}")
    print()


def optimise(df: pd.DataFrame, max_combos: int = 50) -> pd.DataFrame:
    """Grid-search parameter combinations, ranked by return."""
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
        print("No valid results. Try relaxing parameter ranges or using more data.")
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
        description="Backtest BTC RSI-Volume-Wick strategy on saved CSV data",
    )
    p.add_argument(
        "--file", default=None,
        help="Path to CSV file. If omitted, picks from data/ folder.",
    )
    p.add_argument(
        "--preset", default="moderate", choices=list(PRESETS),
        help="Strategy preset (default: moderate)",
    )
    p.add_argument(
        "--compare", action="store_true",
        help="Compare all presets",
    )
    p.add_argument(
        "--optimise", action="store_true",
        help="Run parameter optimisation",
    )
    p.add_argument(
        "--max-combos", type=int, default=50,
        help="Max parameter combinations for --optimise (default: 50)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    print("BTC/USD Strategy Backtester")
    print("=" * 35)

    # ── load data ────────────────────────────────────────────────────
    filepath = pick_file(args.file)
    df = load_csv(filepath)

    # ── run ──────────────────────────────────────────────────────────
    if args.compare:
        compare_presets(df)
    elif args.optimise:
        optimise(df, args.max_combos)
    else:
        run_single(df, args.preset)


if __name__ == "__main__":
    main()
