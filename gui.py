#!/usr/bin/env python3
"""
GUI for the BTC/USD Strategy Backtester.

Two-tab interface:
    Tab 1 — Fetch Data   : pick period + timeframe, download, view saved files
    Tab 2 — Backtest      : pick CSV, adjust parameters, run, view results
"""

import os
import sys
import threading
import tkinter as tk
import pandas as pd
from tkinter import ttk, filedialog

# ── project imports ─────────────────────────────────────────────────────
from data_manager import DataManager
from config import PRESETS, SIGNAL_KEYS, BACKTEST_KEYS
from strategy_backtester import (
    generate_signals, backtest, performance_metrics,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
#  Main application
# ═══════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BTC/USD Strategy Backtester")
        self.geometry("780x720")
        self.minsize(700, 600)

        # ── notebook (tabs) ─────────────────────────────────────────
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.fetch_tab = FetchTab(self.notebook, self)
        self.backtest_tab = BacktestTab(self.notebook, self)

        self.notebook.add(self.fetch_tab, text="  Fetch Data  ")
        self.notebook.add(self.backtest_tab, text="  Backtest  ")

        # when switching to backtest tab, refresh the file list
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, _event):
        selected = self.notebook.index(self.notebook.select())
        if selected == 1:  # Backtest tab
            self.backtest_tab.refresh_files()


# ═══════════════════════════════════════════════════════════════════════════
#  Tab 1 — Fetch Data
# ═══════════════════════════════════════════════════════════════════════════

class FetchTab(ttk.Frame):
    PERIODS = ["1W", "2W", "1M", "2M", "3M", "6M", "1Y", "2Y"]
    TIMEFRAMES = [
        ("15m  (max 60 days)", "15m"),
        ("1h   (max 730 days)", "1h"),
        ("1d   (unlimited)", "1d"),
    ]

    def __init__(self, parent, app: App):
        super().__init__(parent, padding=15)
        self.app = app
        self._build()

    def _build(self):
        # ── settings frame ──────────────────────────────────────────
        settings = ttk.LabelFrame(self, text="Download Settings", padding=12)
        settings.pack(fill=tk.X, pady=(0, 10))

        # period
        ttk.Label(settings, text="Period:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.period_var = tk.StringVar(value="3M")
        period_cb = ttk.Combobox(settings, textvariable=self.period_var,
                                 values=self.PERIODS, state="readonly", width=10)
        period_cb.grid(row=0, column=1, sticky="w")

        # timeframe
        ttk.Label(settings, text="Candle interval:").grid(
            row=0, column=2, sticky="w", padx=(24, 8))
        self.tf_var = tk.StringVar(value="1h")
        tf_cb = ttk.Combobox(settings, textvariable=self.tf_var,
                             values=[t[1] for t in self.TIMEFRAMES],
                             state="readonly", width=10)
        tf_cb.grid(row=0, column=3, sticky="w")

        # fetch button
        self.fetch_btn = ttk.Button(settings, text="Fetch Data",
                                    command=self._on_fetch)
        self.fetch_btn.grid(row=0, column=4, padx=(24, 0))

        # start date (row 1)
        self.use_start_var = tk.BooleanVar(value=False)
        start_check = ttk.Checkbutton(settings, text="Start date:",
                                       variable=self.use_start_var,
                                       command=self._toggle_start)
        start_check.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.start_var = tk.StringVar(value="2024-01-01")
        self.start_entry = ttk.Entry(settings, textvariable=self.start_var,
                                     width=12, state=tk.DISABLED)
        self.start_entry.grid(row=1, column=1, sticky="w", pady=(8, 0))

        self.start_hint = tk.StringVar(value="(disabled — fetches most recent data)")
        ttk.Label(settings, textvariable=self.start_hint,
                  foreground="grey").grid(row=1, column=2, columnspan=3,
                                          sticky="w", padx=(12, 0),
                                          pady=(8, 0))

        # hint label (row 2)
        self.hint_var = tk.StringVar(value="")
        ttk.Label(settings, textvariable=self.hint_var,
                  foreground="grey").grid(row=2, column=0, columnspan=5,
                                          sticky="w", pady=(6, 0))
        tf_cb.bind("<<ComboboxSelected>>", self._update_hint)
        period_cb.bind("<<ComboboxSelected>>", self._update_hint)
        self._update_hint()

        settings.columnconfigure(4, weight=1)

        # ── saved files ─────────────────────────────────────────────
        files_frame = ttk.LabelFrame(self, text="Saved Datasets (data/)",
                                     padding=12)
        files_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("filename", "rows", "size")
        self.tree = ttk.Treeview(files_frame, columns=cols, show="headings",
                                 height=6)
        self.tree.heading("filename", text="File")
        self.tree.heading("rows", text="Rows")
        self.tree.heading("size", text="Size")
        self.tree.column("filename", width=340)
        self.tree.column("rows", width=80, anchor="e")
        self.tree.column("size", width=80, anchor="e")

        scroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL,
                                command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_btn = ttk.Button(self, text="Refresh List",
                                      command=self._refresh_files)
        self.refresh_btn.pack(anchor="w")

        # ── console ─────────────────────────────────────────────────
        console_frame = ttk.LabelFrame(self, text="Console", padding=8)
        console_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.console = tk.Text(console_frame, height=8, wrap=tk.WORD,
                               bg="#f7f7f7", font=("Consolas", 9))
        self.console.pack(fill=tk.BOTH, expand=True)

        self._refresh_files()

    # ── helpers ──────────────────────────────────────────────────────

    def _update_hint(self, _event=None):
        tf = self.tf_var.get()
        limits = {"15m": 60, "1h": 730, "1d": 99999}
        period_days = {"1W": 7, "2W": 14, "1M": 30, "2M": 60,
                       "3M": 90, "6M": 180, "1Y": 365, "2Y": 730}
        max_d = limits.get(tf, 9999)
        req_d = period_days.get(self.period_var.get(), 0)
        if req_d > max_d:
            self.hint_var.set(f"⚠  {tf} interval only supports up to "
                              f"{max_d} days — will be clamped.")
        else:
            self.hint_var.set("")

    def _toggle_start(self):
        if self.use_start_var.get():
            self.start_entry.config(state=tk.NORMAL)
            self.start_hint.set("End = start + period")
        else:
            self.start_entry.config(state=tk.DISABLED)
            self.start_hint.set("(disabled — fetches most recent data)")

    def _refresh_files(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        if not os.path.isdir(DATA_DIR):
            return
        for f in sorted(os.listdir(DATA_DIR)):
            if not f.endswith(".csv"):
                continue
            path = os.path.join(DATA_DIR, f)
            size_kb = os.path.getsize(path) / 1024
            with open(path) as fh:
                rows = sum(1 for _ in fh) - 1
            self.tree.insert("", tk.END,
                             values=(f, f"{rows:,}", f"{size_kb:.0f} KB"))

    def _log(self, msg: str):
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)

    def _on_fetch(self):
        self.fetch_btn.config(state=tk.DISABLED)
        self.console.delete("1.0", tk.END)
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        period = self.period_var.get()
        tf = self.tf_var.get()

        start_date = None
        if self.use_start_var.get():
            start_date = self.start_var.get().strip()
            self._log(f"Fetching BTC-USD  period={period}  interval={tf}  start={start_date} …")
        else:
            self._log(f"Fetching BTC-USD  period={period}  interval={tf} …")

        try:
            dm = DataManager(timeframe=tf)
            df = dm.fetch(period, start_date=start_date)

            if df.empty:
                self._log("✗ No data returned.")
                return

            report = dm.validate(df)
            if not report["valid"]:
                self._log(f"⚠  Warnings: {report['issues']}")
            else:
                self._log(f"Data quality: OK (score {report['score']}/100)")

            from datetime import datetime
            if start_date:
                date_tag = start_date.replace("-", "")
            else:
                date_tag = datetime.now().strftime("%Y%m%d")
            fname = f"BTC-USD_{tf}_{period.upper()}_{date_tag}.csv"
            fpath = os.path.join(DATA_DIR, fname)
            dm.save(fpath)

            s = dm.summary(df)
            self._log(f"\n  Candles : {s['candles']:,}")
            self._log(f"  Range   : {s['start'][:10]} → {s['end'][:10]}")
            self._log(f"  Price   : ${s['price_low']:,.0f} – ${s['price_high']:,.0f}")
            self._log(f"  Saved   : {fname}")

        except Exception as e:
            self._log(f"✗ Error: {e}")
        finally:
            self.after(0, lambda: self.fetch_btn.config(state=tk.NORMAL))
            self.after(0, self._refresh_files)


# ═══════════════════════════════════════════════════════════════════════════
#  Tab 2 — Backtest
# ═══════════════════════════════════════════════════════════════════════════

class BacktestTab(ttk.Frame):

    def __init__(self, parent, app: App):
        super().__init__(parent, padding=15)
        self.app = app
        self._param_entries = {}
        self._build()

    def _build(self):
        # ── top row: file selection ─────────────────────────────────
        file_frame = ttk.LabelFrame(self, text="Data File", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_frame, text="CSV:").grid(row=0, column=0, sticky="w",
                                                  padx=(0, 8))
        self.file_var = tk.StringVar()
        self.file_cb = ttk.Combobox(file_frame, textvariable=self.file_var,
                                    state="readonly", width=48)
        self.file_cb.grid(row=0, column=1, sticky="ew")

        browse_btn = ttk.Button(file_frame, text="Browse …",
                                command=self._browse)
        browse_btn.grid(row=0, column=2, padx=(8, 0))

        file_frame.columnconfigure(1, weight=1)

        # ── preset selector ─────────────────────────────────────────
        preset_frame = ttk.LabelFrame(self, text="Preset", padding=10)
        preset_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(preset_frame, text="Load preset:").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self.preset_var = tk.StringVar(value="moderate")
        preset_cb = ttk.Combobox(preset_frame, textvariable=self.preset_var,
                                 values=list(PRESETS), state="readonly",
                                 width=16)
        preset_cb.grid(row=0, column=1, sticky="w")
        preset_cb.bind("<<ComboboxSelected>>", self._load_preset)

        # ── parameters ──────────────────────────────────────────────
        params_frame = ttk.LabelFrame(self, text="Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=(0, 10))

        fields = [
            # (label,            key,                default, col, row)
            ("RSI Oversold",     "rsi_oversold",     30,      0, 0),
            ("RSI Overbought",   "rsi_overbought",   70,      0, 1),
            ("RSI Period",       "rsi_period",        14,      0, 2),
            ("Volume Multiplier","volume_multiplier", 1.5,     2, 0),
            ("Volume Period",    "volume_period",     20,      2, 1),
            ("Wick Threshold",   "wick_threshold",    0.3,     2, 2),
            ("Initial Capital",  "initial_capital",   10000,   4, 0),
            ("Position Size",    "position_size",     0.10,    4, 1),
            ("Stop Loss",        "stop_loss",         0.02,    4, 2),
            ("Take Profit",      "take_profit",       0.04,    4, 3),
        ]

        for label, key, default, col, row in fields:
            ttk.Label(params_frame, text=label + ":").grid(
                row=row, column=col, sticky="w", padx=(12 if col else 0, 4))
            var = tk.StringVar(value=str(default))
            entry = ttk.Entry(params_frame, textvariable=var, width=10)
            entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 12))
            self._param_entries[key] = var

        # save-to-preset button (right side of params box)
        save_btn = ttk.Button(params_frame, text="Save to Preset",
                              command=self._save_preset)
        save_btn.grid(row=0, column=6, padx=(8, 0), sticky="ne")

        # ── action buttons ──────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.run_btn = ttk.Button(btn_frame, text="Run Backtest",
                                  command=self._on_run)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.compare_btn = ttk.Button(btn_frame, text="Compare All Presets",
                                      command=self._on_compare)
        self.compare_btn.pack(side=tk.LEFT, padx=(0, 6))

        # ── results ─────────────────────────────────────────────────
        results_frame = ttk.LabelFrame(self, text="Results", padding=8)
        results_frame.pack(fill=tk.BOTH, expand=True)

        self.results_text = tk.Text(results_frame, wrap=tk.WORD,
                                    bg="#f7f7f7", font=("Consolas", 9))
        scroll = ttk.Scrollbar(results_frame, orient=tk.VERTICAL,
                                command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scroll.set)
        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_files()
        self._load_preset()

    # ── helpers ──────────────────────────────────────────────────────

    def refresh_files(self):
        csvs = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
        self.file_cb["values"] = csvs
        if csvs and not self.file_var.get():
            self.file_cb.current(len(csvs) - 1)  # pick newest

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select CSV", initialdir=DATA_DIR,
            filetypes=[("CSV files", "*.csv")])
        if path:
            self.file_var.set(os.path.basename(path))

    def _load_preset(self, _event=None):
        name = self.preset_var.get()
        preset = PRESETS.get(name, {})
        for key, var in self._param_entries.items():
            if key in preset:
                var.set(str(preset[key]))

    def _save_preset(self):
        """Write current parameter values back to config.py for the selected preset."""
        from tkinter import messagebox

        name = self.preset_var.get()
        params = self._read_params()
        if not params:
            return

        # only save strategy + risk params, not initial_capital
        saveable = {k: v for k, v in params.items() if k != "initial_capital"}

        confirm = messagebox.askyesno(
            "Save Preset",
            f"Overwrite '{name}' preset in config.py with current parameters?"
        )
        if not confirm:
            return

        # update in-memory presets
        PRESETS[name] = saveable

        # rewrite config.py
        try:
            self._write_config_file()
            messagebox.showinfo("Saved", f"Preset '{name}' saved to config.py")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write config.py:\n{e}")

    def _write_config_file(self):
        """Regenerate config.py from the current PRESETS dict."""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "config.py")

        # read existing file to preserve OPTIMISATION_GRID and other content
        # strategy: rewrite only the PRESETS block, keep everything else
        lines = [
            '"""\n',
            'Strategy presets and default parameters.\n',
            '\n',
            'Each preset is a dict that can be unpacked directly into\n',
            'generate_signals() and backtest() calls.\n',
            '"""\n',
            '\n',
            'PRESETS = {\n',
        ]

        for preset_name, params in PRESETS.items():
            lines.append(f'    "{preset_name}": {{\n')
            for k, v in params.items():
                lines.append(f'        "{k}": {v},\n')
            lines.append(f'    }},\n')
        lines.append('}\n')

        lines.append('\n')
        lines.append('# Keys understood by generate_signals vs backtest\n')
        lines.append('SIGNAL_KEYS = {"rsi_oversold", "rsi_overbought", "rsi_period",\n')
        lines.append('               "volume_multiplier", "volume_period", "wick_threshold"}\n')
        lines.append('BACKTEST_KEYS = {"initial_capital", "position_size", "stop_loss",\n')
        lines.append('                 "take_profit", "transaction_cost"}\n')
        lines.append('\n')
        lines.append('DEFAULTS = PRESETS["moderate"]\n')
        lines.append('\n')
        lines.append('# Parameter grid for optimisation sweeps\n')
        lines.append('OPTIMISATION_GRID = {\n')
        lines.append('    "rsi_oversold":      [25, 30, 35, 40],\n')
        lines.append('    "rsi_overbought":    [60, 65, 70, 75],\n')
        lines.append('    "volume_multiplier": [1.2, 1.5, 1.7],\n')
        lines.append('    "wick_threshold":    [0.2, 0.3, 0.4],\n')
        lines.append('    "stop_loss":         [0.015, 0.02, 0.025],\n')
        lines.append('    "take_profit":       [0.03, 0.04, 0.05],\n')
        lines.append('}\n')

        with open(config_path, "w") as f:
            f.writelines(lines)

    def _read_params(self) -> dict:
        """Parse entries into a params dict, return empty on error."""
        params = {}
        for key, var in self._param_entries.items():
            raw = var.get().strip()
            try:
                params[key] = int(raw) if "." not in raw else float(raw)
            except ValueError:
                self._log(f"✗ Invalid value for {key}: '{raw}'")
                return {}
        return params

    def _log(self, msg: str):
        self.results_text.insert(tk.END, msg + "\n")
        self.results_text.see(tk.END)

    def _clear_results(self):
        self.results_text.delete("1.0", tk.END)

    def _load_data(self) -> "pd.DataFrame | None":
        import pandas as pd
        fname = self.file_var.get()
        if not fname:
            self._log("✗ No file selected.")
            return None
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            self._log(f"✗ File not found: {path}")
            return None
        dm = DataManager()
        df = dm.load(path)
        if df.empty:
            self._log("✗ File is empty or could not be parsed.")
            return None
        report = dm.validate(df)
        self._log(f"Loaded {len(df):,} candles from {fname}")
        if not report["valid"]:
            self._log(f"⚠  Warnings: {report['issues']}")
        return df

    # ── run backtest ─────────────────────────────────────────────────

    def _on_run(self):
        self.run_btn.config(state=tk.DISABLED)
        self.compare_btn.config(state=tk.DISABLED)
        self._clear_results()
        threading.Thread(target=self._do_run, daemon=True).start()

    def _do_run(self):
        try:
            df = self._load_data()
            if df is None:
                return

            params = self._read_params()
            if not params:
                return

            sig_p = {k: v for k, v in params.items() if k in SIGNAL_KEYS}
            bt_p = {k: v for k, v in params.items() if k in BACKTEST_KEYS}

            signals = generate_signals(df, **sig_p)
            result = backtest(signals, **bt_p)
            m = performance_metrics(result)

            self._print_metrics(m)

        except Exception as e:
            self._log(f"✗ Error: {e}")
        finally:
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            self.after(0, lambda: self.compare_btn.config(state=tk.NORMAL))

    # ── compare all presets ──────────────────────────────────────────

    def _on_compare(self):
        self.run_btn.config(state=tk.DISABLED)
        self.compare_btn.config(state=tk.DISABLED)
        self._clear_results()
        threading.Thread(target=self._do_compare, daemon=True).start()

    def _do_compare(self):
        try:
            df = self._load_data()
            if df is None:
                return

            header = (f"  {'Preset':<16} {'Return':>10} {'Win Rate':>10} "
                      f"{'Trades':>8} {'Sharpe':>8}")
            self._log("\n  PRESET COMPARISON")
            self._log("  " + "=" * 56)
            self._log(header)
            self._log("  " + "-" * 56)

            for name, preset in PRESETS.items():
                sig_p = {k: v for k, v in preset.items() if k in SIGNAL_KEYS}
                bt_p = {k: v for k, v in preset.items() if k in BACKTEST_KEYS}

                signals = generate_signals(df, **sig_p)
                result = backtest(signals, **bt_p)
                m = performance_metrics(result)

                if "error" in m:
                    self._log(f"  {name:<16} {'—':>10} {'—':>10} "
                              f"{'—':>8} {'—':>8}")
                else:
                    self._log(
                        f"  {name:<16} "
                        f"{m['Total Return (%)']:>+9.2f}% "
                        f"{m['Win Rate (%)']:>9.1f}% "
                        f"{m['Total Trades']:>8} "
                        f"{m['Sharpe Ratio']:>8.2f}"
                    )
            self._log("")

        except Exception as e:
            self._log(f"✗ Error: {e}")
        finally:
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            self.after(0, lambda: self.compare_btn.config(state=tk.NORMAL))

    # ── formatted metrics output ─────────────────────────────────────

    def _print_metrics(self, m: dict):
        if "error" in m:
            self._log(f"\n  {m['error']}")
            self._log(f"  Signals generated: {m.get('signals_generated', 0)}")
            self._log("  Try relaxing parameters or using more data.\n")
            return

        self._log(f"\n  {'='*50}")
        self._log(f"  BACKTEST RESULTS")
        self._log(f"  {'='*50}")

        sections = [
            ("Signals", [
                ("Generated", m["Signals Generated"]),
                ("Attempted", m["Trades Attempted"]),
                ("Conversion", f"{m['Signal Conversion (%)']:.1f} %"),
            ]),
            ("Trades", [
                ("Total", m["Total Trades"]),
                ("Wins / Losses", f"{m['Winning Trades']} / {m['Losing Trades']}"),
                ("Win Rate", f"{m['Win Rate (%)']:.1f} %"),
            ]),
            ("Returns", [
                ("Total Return", f"{m['Total Return (%)']:.2f} %"),
                ("Net Profit", f"${m['Net Profit']:,.2f}"),
                ("Avg Trade", f"${m['Avg Trade P&L']:,.2f}"),
                ("Best / Worst",
                 f"{m['Best Trade (%)']:.2f}% / {m['Worst Trade (%)']:.2f}%"),
            ]),
            ("Risk", [
                ("Profit Factor", f"{m['Profit Factor']:.2f}"),
                ("Max Drawdown", f"{m['Max Drawdown (%)']:.2f} %"),
                ("Sharpe", f"{m['Sharpe Ratio']:.2f}"),
                ("Sortino", f"{m['Sortino Ratio']:.2f}"),
            ]),
            ("Exits", [
                ("Stop-Loss", m["SL Exits"]),
                ("Take-Profit", m["TP Exits"]),
                ("End-of-Data", m["EOD Exits"]),
            ]),
            ("Capital", [
                ("Initial", f"${m['Initial Capital']:,.2f}"),
                ("Final", f"${m['Final Capital']:,.2f}"),
                ("Net Profit", f"${m['Net Profit']:,.2f}"),
                ("Costs Paid", f"${m['Total Costs']:,.2f}"),
            ]),
        ]

        for title, rows in sections:
            self._log(f"\n  {title}")
            self._log(f"  {'-'*40}")
            for label, val in rows:
                self._log(f"    {label:<22} {val}")

        ret = m["Total Return (%)"]
        tag = "STRONG" if ret > 10 else "POSITIVE" if ret > 0 else "NEGATIVE"
        self._log(f"\n  Assessment: {tag} ({ret:+.2f} %)")
        self._log(f"  ${m['Initial Capital']:,.0f} → ${m['Final Capital']:,.0f}")
        self._log(f"  {'='*50}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()