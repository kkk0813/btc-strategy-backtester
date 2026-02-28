"""
Strategy presets and default parameters.

Each preset is a dict that can be unpacked directly into
generate_signals() and backtest() calls.
"""

PRESETS = {
    "conservative": {
        "rsi_oversold": 25,
        "rsi_overbought": 75,
        "rsi_period": 14,
        "volume_multiplier": 1.7,
        "volume_period": 20,
        "wick_threshold": 0.4,
        "stop_loss": 0.025,
        "take_profit": 0.05,
        "position_size": 0.08,
    },
    "moderate": {
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "rsi_period": 14,
        "volume_multiplier": 1.5,
        "volume_period": 20,
        "wick_threshold": 0.3,
        "stop_loss": 0.02,
        "take_profit": 0.04,
        "position_size": 0.1,
    },
    "aggressive": {
        "rsi_oversold": 35,
        "rsi_overbought": 65,
        "rsi_period": 14,
        "volume_multiplier": 1.3,
        "volume_period": 20,
        "wick_threshold": 0.2,
        "stop_loss": 0.015,
        "take_profit": 0.03,
        "position_size": 0.15,
    },
    "scalping": {
        "rsi_oversold": 40,
        "rsi_overbought": 60,
        "rsi_period": 10,
        "volume_multiplier": 2,
        "volume_period": 20,
        "wick_threshold": 0.15,
        "position_size": 0.2,
        "stop_loss": 0.01,
        "take_profit": 0.03,
    },
}

# Keys understood by generate_signals vs backtest
SIGNAL_KEYS = {"rsi_oversold", "rsi_overbought", "rsi_period",
               "volume_multiplier", "volume_period", "wick_threshold"}
BACKTEST_KEYS = {"initial_capital", "position_size", "stop_loss",
                 "take_profit", "transaction_cost"}

DEFAULTS = PRESETS["moderate"]

# Parameter grid for optimisation sweeps
OPTIMISATION_GRID = {
    "rsi_oversold":      [25, 30, 35, 40],
    "rsi_overbought":    [60, 65, 70, 75],
    "volume_multiplier": [1.2, 1.5, 1.7],
    "wick_threshold":    [0.2, 0.3, 0.4],
    "stop_loss":         [0.015, 0.02, 0.025],
    "take_profit":       [0.03, 0.04, 0.05],
}
