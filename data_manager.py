"""
Data Manager — Fetches and validates BTC historical data via yfinance.

yfinance pulls data directly from Yahoo Finance, which aggregates exchange
data and is widely used as a reliable free reference source. No API key needed.

Timeframe limits (Yahoo Finance):
    - 1m  : max  7 days
    - 5m  : max 60 days
    - 15m : max 60 days
    - 1h  : max 730 days
    - 1d  : unlimited
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    yf = None  # fetch() will raise a clear error if called without it


# ── Symbol mapping ──────────────────────────────────────────────────────────
# yfinance uses '-' notation (BTC-USD), not '/' (BTC/USDT).
# BTC-USD from Yahoo tracks the same Coinbase/Binance composite price
# and is the most common free data source for crypto backtesting.
SYMBOL = "BTC-USD"

# Maximum history that Yahoo Finance allows per timeframe
_MAX_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "1h": 730,
    "1d": 9999,
}

# Human-friendly period codes → days
_PERIOD_DAYS = {
    "1W": 7,
    "2W": 14,
    "1M": 30,
    "2M": 60,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "2Y": 730,
}


class DataManager:
    """Fetch, validate, save, and load BTC OHLCV data."""

    def __init__(self, symbol: str = SYMBOL, timeframe: str = "1h"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data: Optional[pd.DataFrame] = None

    # ── Fetch ────────────────────────────────────────────────────────────
    def fetch(self, period: str = "3M", start_date: str = None) -> pd.DataFrame:
        """
        Download OHLCV data from Yahoo Finance.

        Args:
            period:     Duration of data — e.g. '1M', '3M', '6M', '1Y'.
            start_date: Optional start date as 'YYYY-MM-DD'.
                        If given, end date = start_date + period.
                        If omitted, end date = today (fetch most recent data).

        Returns:
            DataFrame indexed by datetime with columns
            [Open, High, Low, Close, Volume].
        """
        days = _PERIOD_DAYS.get(period.upper())
        if days is None:
            raise ValueError(
                f"Unknown period '{period}'. Choose from: {list(_PERIOD_DAYS)}"
            )

        if yf is None:
            raise RuntimeError(
                "yfinance is not installed.  Run:  pip install yfinance"
            )

        max_days = _MAX_DAYS.get(self.timeframe, 9999)
        if days > max_days:
            print(
                f"⚠  {self.timeframe} data is limited to {max_days} days on Yahoo Finance. "
                f"Clamping request from {days}d → {max_days}d."
            )
            days = max_days

        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = start + timedelta(days=days)
            # clamp to today if end is in the future
            if end > datetime.now():
                end = datetime.now()
        else:
            end = datetime.now()
            start = end - timedelta(days=days)

        print(f"Fetching {self.symbol} ({self.timeframe}) from {start:%Y-%m-%d} to {end:%Y-%m-%d} ...")

        df = yf.download(
            self.symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=self.timeframe,
            auto_adjust=True,
            progress=False,
        )

        if df.empty:
            print("✗ No data returned from Yahoo Finance.")
            return pd.DataFrame()

        # Flatten MultiIndex columns if present (yfinance >= 0.2.31)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Keep only OHLCV and ensure column order
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        df.sort_index(inplace=True)

        # Remove duplicate timestamps
        df = df[~df.index.duplicated(keep="first")]

        self.data = df
        actual_days = (df.index[-1] - df.index[0]).days

        print(f"✓ {len(df):,} candles | {actual_days} days | "
              f"${df['Close'].iloc[-1]:,.0f} last close")

        return df

    # ── Validation ───────────────────────────────────────────────────────
    def validate(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Run quality checks on OHLCV data.

        Returns a dict with 'valid' (bool), 'issues' (list[str]),
        and 'score' (0-100).
        """
        if df is None:
            df = self.data
        if df is None or df.empty:
            return {"valid": False, "issues": ["No data loaded"], "score": 0}

        issues = []

        # 1. Missing values
        n_missing = int(df.isnull().sum().sum())
        if n_missing:
            issues.append(f"{n_missing} missing values")

        # 2. Duplicate timestamps
        n_dup = int(df.index.duplicated().sum())
        if n_dup:
            issues.append(f"{n_dup} duplicate timestamps")

        # 3. Non-positive prices
        price_cols = ["Open", "High", "Low", "Close"]
        n_bad = int((df[price_cols] <= 0).sum().sum())
        if n_bad:
            issues.append(f"{n_bad} non-positive price entries")

        # 4. OHLC logic (High should be highest, Low should be lowest)
        ohlc_errors = int(
            (df["High"] < df["Low"]).sum()
            + (df["High"] < df["Open"]).sum()
            + (df["High"] < df["Close"]).sum()
            + (df["Low"] > df["Open"]).sum()
            + (df["Low"] > df["Close"]).sum()
        )
        if ohlc_errors:
            issues.append(f"{ohlc_errors} OHLC logic violations")

        # 5. Extreme single-candle moves (>30 %)
        pct = df["Close"].pct_change().abs()
        n_extreme = int((pct > 0.30).sum())
        if n_extreme:
            issues.append(f"{n_extreme} candles with >30 % move")

        score = max(0, 100 - len(issues) * 15)
        return {"valid": len(issues) == 0, "issues": issues, "score": score}

    # ── Save / Load ──────────────────────────────────────────────────────
    def save(self, filepath: str) -> str:
        """Save current data to CSV."""
        if self.data is None or self.data.empty:
            print("✗ No data to save.")
            return ""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        self.data.to_csv(filepath)
        print(f"✓ Saved {len(self.data):,} candles → {filepath}")
        return filepath

    def load(self, filepath: str) -> pd.DataFrame:
        """Load OHLCV data from a CSV file."""
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        df.sort_index(inplace=True)
        self.data = df
        actual_days = (df.index[-1] - df.index[0]).days
        print(f"✓ Loaded {len(df):,} candles ({actual_days} days) from {filepath}")
        return df

    # ── Summary ──────────────────────────────────────────────────────────
    def summary(self, df: Optional[pd.DataFrame] = None) -> dict:
        """Return a human-readable summary dict of the loaded data."""
        if df is None:
            df = self.data
        if df is None or df.empty:
            return {"error": "No data loaded"}

        returns = df["Close"].pct_change().dropna()
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "candles": len(df),
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
            "days": (df.index[-1] - df.index[0]).days,
            "price_low": float(df["Low"].min()),
            "price_high": float(df["High"].max()),
            "last_close": float(df["Close"].iloc[-1]),
            "volatility_pct": float(returns.std() * 100),
        }