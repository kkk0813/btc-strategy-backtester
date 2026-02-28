"""
Strategy Backtester — RSI + Volume Spike + Wick reversal strategy.

Entry logic
-----------
LONG  : RSI < oversold  AND  volume spike  AND  long lower wick
SHORT : RSI > overbought  AND  volume spike  AND  long upper wick

Exit logic
----------
Each trade closes when it hits the stop-loss %, take-profit %, or the
data ends (EOD).  Transaction costs are deducted on every round-trip.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


# ═══════════════════════════════════════════════════════════════════════════
#  Indicators
# ═══════════════════════════════════════════════════════════════════════════

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.inf)
    return 100 - (100 / (1 + rs))


def volume_spike(volume: pd.Series, multiplier: float = 1.5,
                 period: int = 20) -> pd.Series:
    """True where volume exceeds `multiplier` × rolling average."""
    avg = volume.rolling(period).mean()
    return (volume > avg * multiplier).fillna(False)


def wick_ratios(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Return (upper_wick_ratio, lower_wick_ratio).

    Ratio = wick length / max(body, 0.1 % of price).
    The 0.1 % floor avoids division-by-zero on doji candles.
    """
    body = (df["Close"] - df["Open"]).abs()
    min_body = df["Close"] * 0.001
    body = body.where(body > 0, min_body)

    upper = df["High"] - df[["Open", "Close"]].max(axis=1)
    lower = df[["Open", "Close"]].min(axis=1) - df["Low"]

    return (upper / body).fillna(0), (lower / body).fillna(0)


# ═══════════════════════════════════════════════════════════════════════════
#  Signal generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_signals(
    df: pd.DataFrame,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    rsi_period: int = 14,
    volume_multiplier: float = 1.5,
    volume_period: int = 20,
    wick_threshold: float = 0.3,
) -> pd.DataFrame:
    """
    Attach indicator columns and a Signal column to a copy of *df*.

    Signal values: +1 (long), -1 (short), 0 (no signal).
    """
    out = df.copy()

    out["RSI"] = rsi(out["Close"], rsi_period)
    out["Volume_Spike"] = volume_spike(out["Volume"], volume_multiplier, volume_period)
    out["Upper_Wick_Ratio"], out["Lower_Wick_Ratio"] = wick_ratios(out)

    long_cond = (
        (out["RSI"] < rsi_oversold)
        & out["Volume_Spike"]
        & (out["Lower_Wick_Ratio"] > wick_threshold)
    )
    short_cond = (
        (out["RSI"] > rsi_overbought)
        & out["Volume_Spike"]
        & (out["Upper_Wick_Ratio"] > wick_threshold)
    )

    out["Signal"] = 0
    out.loc[long_cond, "Signal"] = 1
    out.loc[short_cond, "Signal"] = -1

    n_long = int(long_cond.sum())
    n_short = int(short_cond.sum())
    print(f"Signals → {n_long} long, {n_short} short  "
          f"(RSI {rsi_oversold}/{rsi_overbought}, vol ×{volume_multiplier}, "
          f"wick {wick_threshold})")

    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Backtester
# ═══════════════════════════════════════════════════════════════════════════

def backtest(
    signals_df: pd.DataFrame,
    initial_capital: float = 10_000,
    position_size: float = 0.10,
    stop_loss: float = 0.02,
    take_profit: float = 0.04,
    transaction_cost: float = 0.001,
) -> Dict:
    """
    Simulate the strategy on *signals_df* (which must contain a Signal column).

    Returns a dict with keys: trades, equity_curve, final_capital,
    initial_capital, signals_generated, trades_attempted.
    """
    capital = initial_capital
    position = 0          # +1 long, -1 short, 0 flat
    entry_price = 0.0
    entry_time = None
    trades = []
    equity = [initial_capital]

    signals_generated = int(signals_df["Signal"].abs().sum())
    trades_attempted = 0

    for i in range(1, len(signals_df)):
        price = signals_df["Close"].iloc[i]
        sig = signals_df["Signal"].iloc[i]
        ts = signals_df.index[i]

        if sig != 0:
            trades_attempted += 1

        # ── check exit ──────────────────────────────────────────────
        if position != 0:
            pnl_pct = (
                (price - entry_price) / entry_price
                if position == 1
                else (entry_price - price) / entry_price
            )

            reason = None
            if pnl_pct <= -stop_loss:
                reason = "SL"
            elif pnl_pct >= take_profit:
                reason = "TP"

            if reason:
                amt = capital * position_size
                costs = amt * transaction_cost * 2  # entry + exit
                net = amt * pnl_pct - costs
                capital += net
                trades.append(_trade_record(
                    entry_time, ts, position, entry_price, price,
                    pnl_pct, amt, net, costs, reason,
                ))
                position, entry_price, entry_time = 0, 0.0, None

        # ── check entry ─────────────────────────────────────────────
        if position == 0 and sig != 0:
            position = sig
            entry_price = price
            entry_time = ts

        # ── equity update ───────────────────────────────────────────
        eq = capital
        if position != 0:
            unreal = (
                (price - entry_price) / entry_price
                if position == 1
                else (entry_price - price) / entry_price
            )
            eq += capital * position_size * unreal
        equity.append(eq)

    # ── close any open position at end of data ──────────────────────
    if position != 0:
        price = signals_df["Close"].iloc[-1]
        ts = signals_df.index[-1]
        pnl_pct = (
            (price - entry_price) / entry_price
            if position == 1
            else (entry_price - price) / entry_price
        )
        amt = capital * position_size
        costs = amt * transaction_cost * 2
        net = amt * pnl_pct - costs
        capital += net
        trades.append(_trade_record(
            entry_time, ts, position, entry_price, price,
            pnl_pct, amt, net, costs, "EOD",
        ))

    print(f"Backtest → {signals_generated} signals, "
          f"{trades_attempted} attempted, {len(trades)} executed")

    return {
        "trades": trades,
        "equity_curve": equity,
        "final_capital": capital,
        "initial_capital": initial_capital,
        "signals_generated": signals_generated,
        "trades_attempted": trades_attempted,
    }


def _trade_record(entry_time, exit_time, direction, entry_px, exit_px,
                   pnl_pct, amount, net_pnl, costs, reason) -> Dict:
    duration_hrs = (exit_time - entry_time).total_seconds() / 3600
    return {
        "entry_time": entry_time,
        "exit_time": exit_time,
        "type": "LONG" if direction == 1 else "SHORT",
        "entry_price": entry_px,
        "exit_price": exit_px,
        "pnl_pct": pnl_pct,
        "net_pnl": net_pnl,
        "costs": costs,
        "amount": amount,
        "duration_hrs": duration_hrs,
        "reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Performance metrics
# ═══════════════════════════════════════════════════════════════════════════

def performance_metrics(result: Dict) -> Dict:
    """
    Compute a full set of performance metrics from a backtest result dict.

    If no trades were executed, returns a dict with an 'error' key and
    diagnostic info.
    """
    trades = result["trades"]
    equity = result["equity_curve"]
    cap0 = result["initial_capital"]
    capN = result["final_capital"]
    sig_gen = result.get("signals_generated", 0)
    sig_att = result.get("trades_attempted", 0)

    if not trades:
        return {
            "error": "No trades executed",
            "signals_generated": sig_gen,
            "trades_attempted": sig_att,
        }

    tdf = pd.DataFrame(trades)

    n = len(tdf)
    wins = tdf[tdf["net_pnl"] > 0]
    losses = tdf[tdf["net_pnl"] <= 0]
    n_win = len(wins)
    n_loss = len(losses)
    win_rate = n_win / n * 100

    gross_profit = wins["net_pnl"].sum() if n_win else 0.0
    gross_loss = abs(losses["net_pnl"].sum()) if n_loss else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    eq_s = pd.Series(equity)
    peak = eq_s.expanding().max()
    dd = (eq_s - peak) / peak * 100
    max_dd = abs(dd.min())

    rets = eq_s.pct_change().dropna()
    if len(rets) > 1 and rets.std() > 0:
        # annualise assuming 1 h candles → 8760 candles/year
        ann_factor = np.sqrt(8760)
        sharpe = (rets.mean() / rets.std()) * ann_factor
        neg = rets[rets < 0]
        sortino = (rets.mean() / neg.std()) * ann_factor if len(neg) > 0 else float("inf")
    else:
        sharpe = sortino = 0.0

    exit_counts = tdf["reason"].value_counts()

    return {
        # signals
        "Signals Generated": sig_gen,
        "Trades Attempted": sig_att,
        "Signal Conversion (%)": (n / sig_gen * 100) if sig_gen else 0,
        # trades
        "Total Trades": n,
        "Winning Trades": n_win,
        "Losing Trades": n_loss,
        "Win Rate (%)": win_rate,
        # returns
        "Total Return (%)": (capN - cap0) / cap0 * 100,
        "Net Profit": capN - cap0,
        "Avg Trade P&L": float(tdf["net_pnl"].mean()),
        "Best Trade (%)": float(tdf["pnl_pct"].max() * 100),
        "Worst Trade (%)": float(tdf["pnl_pct"].min() * 100),
        "Avg Win (%)": float(wins["pnl_pct"].mean() * 100) if n_win else 0,
        "Avg Loss (%)": float(losses["pnl_pct"].mean() * 100) if n_loss else 0,
        # risk
        "Profit Factor": profit_factor,
        "Max Drawdown (%)": max_dd,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        # duration
        "Avg Duration (hrs)": float(tdf["duration_hrs"].mean()),
        "Max Duration (hrs)": float(tdf["duration_hrs"].max()),
        # costs
        "Total Costs": float(tdf["costs"].sum()),
        # exits
        "SL Exits": int(exit_counts.get("SL", 0)),
        "TP Exits": int(exit_counts.get("TP", 0)),
        "EOD Exits": int(exit_counts.get("EOD", 0)),
        # capital
        "Initial Capital": cap0,
        "Final Capital": capN,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Display helpers
# ═══════════════════════════════════════════════════════════════════════════

def print_metrics(m: Dict) -> None:
    """Pretty-print a metrics dict to the console."""
    if "error" in m:
        print(f"\n{'='*55}")
        print(f"  Strategy produced {m.get('signals_generated',0)} signals "
              f"but {m['error'].lower()}.")
        print(f"  Try relaxing parameters or using more data.")
        print(f"{'='*55}\n")
        return

    print(f"\n{'='*55}")
    print(f"  BACKTEST RESULTS")
    print(f"{'='*55}")

    _section("Signals",
             ("Generated", m["Signals Generated"]),
             ("Attempted", m["Trades Attempted"]),
             ("Conversion", f"{m['Signal Conversion (%)']:.1f} %"))

    _section("Trades",
             ("Total", m["Total Trades"]),
             ("Wins / Losses", f"{m['Winning Trades']} / {m['Losing Trades']}"),
             ("Win Rate", f"{m['Win Rate (%)']:.1f} %"))

    _section("Returns",
             ("Total Return", f"{m['Total Return (%)']:.2f} %"),
             ("Net Profit", f"${m['Net Profit']:,.2f}"),
             ("Avg Trade", f"${m['Avg Trade P&L']:,.2f}"),
             ("Best / Worst", f"{m['Best Trade (%)']:.2f} % / {m['Worst Trade (%)']:.2f} %"))

    _section("Risk",
             ("Profit Factor", f"{m['Profit Factor']:.2f}"),
             ("Max Drawdown", f"{m['Max Drawdown (%)']:.2f} %"),
             ("Sharpe", f"{m['Sharpe Ratio']:.2f}"),
             ("Sortino", f"{m['Sortino Ratio']:.2f}"))

    _section("Exits",
             ("Stop-Loss", m["SL Exits"]),
             ("Take-Profit", m["TP Exits"]),
             ("End-of-Data", m["EOD Exits"]))

    _section("Capital",
             ("Initial", f"${m['Initial Capital']:,.2f}"),
             ("Final", f"${m['Final Capital']:,.2f}"),
             ("Net Profit", f"${m['Net Profit']:,.2f}"),
             ("Costs Paid", f"${m['Total Costs']:,.2f}"))

    # overall assessment
    ret = m["Total Return (%)"]
    tag = ("STRONG" if ret > 10 else "POSITIVE" if ret > 0
           else "NEGATIVE")
    print(f"\n  Assessment: {tag} ({ret:+.2f} %)")
    print(f"  ${m['Initial Capital']:,.0f} → ${m['Final Capital']:,.0f}")
    print(f"{'='*55}\n")


def _section(title: str, *rows):
    print(f"\n  {title}")
    print(f"  {'-'*40}")
    for label, val in rows:
        print(f"    {label:<22} {val}")