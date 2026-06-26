#!/usr/bin/env python3
# atr_report.py
# Production-ready ATR/ADX/Ichimoku reporting utility

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import json
from paths import CASH_DIR



REPORTS_DIR = Path("reports")
STOCK_REPORTS_DIR = REPORTS_DIR / "stocks"

def wilder_atr(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def wilder_adx(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    plus_dm = np.where((high.diff() > -low.diff()) & (high.diff() > 0), high.diff(), 0.0)
    minus_dm = np.where((-low.diff() > high.diff()) & (-low.diff() > 0), -low.diff(), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100
    return dx.ewm(alpha=1/period, adjust=False).mean()

def ichimoku(df):
    high, low = df["High"], df["Low"]
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    return tenkan, kijun

def resample_ohlc(df, rule):
    return df.resample(rule).agg({
        "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
    }).dropna()

def append_excel(path, row_df):

    try:
        if path.exists() and path.stat().st_size > 0:
            existing = pd.read_excel(path)
            row_df = pd.concat(
                [existing, row_df],
                ignore_index=True
            )

    except Exception as ex:
        print(
            f"WARNING: recreating Excel {path}: {ex}"
        )

    row_df.to_excel(path, index=False)

def append_csv(path, row_df):

    try:
        if path.exists() and path.stat().st_size > 0:
            existing = pd.read_csv(path)
            row_df = pd.concat(
                [existing, row_df],
                ignore_index=True
            )

    except Exception as ex:
        print(
            f"WARNING: recreating CSV {path}: {ex}"
        )

    row_df.to_csv(path, index=False)

def load_stock(stock):

    csv_file = CASH_DIR / f"{stock.upper()}.csv"

    print(f"Loading stock file: {csv_file}")

    df = pd.read_csv(csv_file)

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").set_index("Date")
    return df

def process_stock(stock):
    df = load_stock(stock)

    daily_atr = float(wilder_atr(df).iloc[-1])
    weekly = resample_ohlc(df, "W")
    monthly = resample_ohlc(df, "ME")

    weekly_atr = float(wilder_atr(weekly).iloc[-1]) if len(weekly) > 14 else np.nan
    monthly_atr = float(wilder_atr(monthly).iloc[-1]) if len(monthly) > 14 else np.nan

    adx = float(wilder_adx(df).iloc[-1])

    tenkan, kijun = ichimoku(df)

    close = float(df["Close"].iloc[-1])
    tenkan_val = float(tenkan.iloc[-1])
    kijun_val = float(kijun.iloc[-1])

    vol_ratio = float(df["Volume"].iloc[-1] / df["Volume"].tail(20).mean())
    volume_confirmed = vol_ratio > 1

    score = 0
    if adx > 25: score += 2
    if volume_confirmed: score += 2
    if close > kijun_val: score += 2
    if tenkan_val > kijun_val: score += 2
    if close > tenkan_val: score += 2

    record = {
        "Run Date": datetime.now().strftime("%Y-%m-%d"),
        "Stock": stock.upper(),
        "Close": round(close,2),
        "Daily ATR": round(daily_atr,2),
        "Weekly ATR": None if np.isnan(weekly_atr) else round(weekly_atr,2),
        "Monthly ATR": None if np.isnan(monthly_atr) else round(monthly_atr,2),
        "ATR %": round((daily_atr/close)*100,2),
        "ADX": round(adx,2),
        "Tenkan": round(tenkan_val,2),
        "Kijun": round(kijun_val,2),
        "Volume Ratio": round(vol_ratio,2),
        "Trend Score": score,
        "Setup Status": "YES" if score >= 8 else "NO"
    }
    return record

def save_record(record):
    REPORTS_DIR.mkdir(exist_ok=True)
    STOCK_REPORTS_DIR.mkdir(exist_ok=True)

    row = pd.DataFrame([record])

    append_csv(REPORTS_DIR / "atr_history.csv", row)
    append_excel(REPORTS_DIR / "atr_history.xlsx", row)
    append_excel(STOCK_REPORTS_DIR / f"{record['Stock']}_history.xlsx", row)



def load_config_stocks():

    config_file = Path("config.json")

    if not config_file.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_file}"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    stocks = config.get("watchlist", [])

    if not stocks:
        raise ValueError(
            "No stocks defined in watchlist"
        )

    return [
        str(stock).strip().upper()
        for stock in stocks
    ]


def main():

    try:

        # ----------------------------------
        # Command line stock takes priority
        # ----------------------------------

        if len(sys.argv) > 1:

            stocks = [
                sys.argv[1].upper()
            ]

        # ----------------------------------
        # Otherwise use config.json
        # ----------------------------------

        else:

            stocks = load_config_stocks()

        print(
            f"Processing {len(stocks)} stock(s)"
        )

        for stock in stocks:

            try:

                record = process_stock(
                    stock
                )

                save_record(
                    record
                )

            except Exception as ex:

                print(
                    f"Failed {stock}: {ex}"
                )

    except Exception as ex:

        print(f"ERROR: {ex}")
        sys.exit(1)

if __name__ == "__main__":
    main()
