# BTC/USD Trading Strategy Backtester

A Python backtesting framework for a **RSI + Volume Spike + Candlestick Wick** reversal strategy on Bitcoin historical data. Includes both a CLI and a GUI interface.

## Strategy Logic

The strategy generates entry signals by combining three independent technical indicators that must all agree simultaneously:

| Signal | RSI | Volume | Candlestick |
|--------|-----|--------|-------------|
| **Long** (buy) | RSI < oversold threshold | Volume > N× rolling average | Lower wick > threshold ratio |
| **Short** (sell) | RSI > overbought threshold | Volume > N× rolling average | Upper wick > threshold ratio |

Each trade exits on a **stop-loss**, **take-profit**, or at the end of data. Transaction costs are deducted per round-trip.

## Quick Start

```bash
git clone https://github.com/kkk0813/btc-strategy-backtester.git
cd btc-strategy-backtester
pip install -r requirements.txt
```

### GUI (recommended)
```bash
python gui.py
```
Two-tab interface: **Fetch Data** to download and manage datasets, **Backtest** to run strategies with adjustable parameters and view results.

### CLI
```bash
# Step 1: Fetch data (saved to data/ as CSV)
python fetch_data.py                              # 3M ending today
python fetch_data.py --period 6M                  # 6 months
python fetch_data.py --start 2024-01-01           # 3M from a specific date
python fetch_data.py --start 2023-06-15 --period 1Y --timeframe 1d
python fetch_data.py --list                       # list saved datasets

# Step 2: Backtest (reads from saved CSVs — no re-downloading)
python backtest.py                                # auto-picks CSV
python backtest.py --file data/BTC-USD_1h_3M_20260228.csv
python backtest.py --preset aggressive
python backtest.py --compare                      # all presets side by side
python backtest.py --optimise                     # parameter grid search
```

## Project Structure

```
├── gui.py                  # GUI (tkinter) — fetch data + backtest in one window
├── fetch_data.py           # CLI — download data from Yahoo Finance → CSV
├── backtest.py             # CLI — run backtests on saved CSV files
├── data_manager.py         # Library — data fetching, validation, CSV I/O
├── strategy_backtester.py  # Library — indicators, signals, backtester, metrics
├── config.py               # Strategy presets and parameter grid
├── data/                   # Saved datasets (CSV)
│   └── btc_sample_1h.csv   # Bundled sample data (90 days, 1h candles)
├── requirements.txt
└── README.md
```

## Data Source

Historical OHLCV data is fetched from **Yahoo Finance** via [yfinance](https://github.com/ranaroussi/yfinance). No API key required.

| Timeframe | Max History |
|-----------|-------------|
| 15m | 60 days |
| 1h | 730 days (2 years) |
| 1d | Unlimited |

You can specify a **start date** to fetch data from any historical period (e.g. a crash or rally), not just the most recent. The end date is calculated as start + period.

## Features

- **Separated fetch and backtest** — download once, backtest as many times as you want
- **GUI and CLI** — both interfaces use the same underlying engine
- **4 built-in presets** — conservative, moderate, aggressive, scalping
- **Saveable presets** — tune parameters in the GUI and save them back to config.py
- **Parameter optimisation** — grid search across RSI, volume, wick, and risk parameters
- **Preset comparison** — run all presets on the same data in one command
- **Data validation** — checks for missing values, OHLC logic errors, extreme moves
- **Comprehensive metrics** — win rate, Sharpe ratio, Sortino ratio, max drawdown, profit factor, capital tracking, transaction costs

## Configuration

Four built-in presets in `config.py` (editable via GUI "Save to Preset" button):

| Preset | RSI | Volume | Wick | SL / TP |
|--------|-----|--------|------|---------|
| Conservative | 25 / 75 | 1.7× | 0.4 | 2.5% / 5.0% |
| Moderate | 30 / 70 | 1.5× | 0.3 | 2.0% / 4.0% |
| Aggressive | 35 / 65 | 1.3× | 0.2 | 1.5% / 3.0% |
| Scalping | 40 / 60 | 1.2× | 0.15 | 1.0% / 2.0% |

## Built With

- **Python 3.9+**
- **pandas** — data manipulation
- **NumPy** — numerical computation
- **yfinance** — market data retrieval
- **tkinter** — GUI (included with Python)

## Disclaimer

This project is for **educational and research purposes only**. It is not financial advice. Past backtested performance does not guarantee future results.