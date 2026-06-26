#!/usr/bin/env python3

"""
derivative_analyse.py

Derivative analysis using NSE option chain via pnsea.

Usage:

    python derivative_analyse.py PAYTM

or

    python derivative_analyse.py

Reads watchlist from config.json:

{
    "watchlist": [
        "PAYTM",
        "HDFCBANK",
        "INFY",
        "TCS",
        "RELIANCE"
    ]
}
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import traceback
from paths import DERIVATIVE_DIR

import pandas as pd
from pnsea import NSE


REPORT_DIR = Path("reports")
STOCK_DIR = REPORT_DIR / "stocks"


# ==========================================================
# CONFIG
# ==========================================================

def load_watchlist():

    config_file = Path("config.json")

    if not config_file.exists():
        raise FileNotFoundError(
            "config.json not found"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    return [
        s.strip().upper()
        for s in config.get("watchlist", [])
    ]


# ==========================================================
# FILE HELPERS
# ==========================================================

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
            f"WARNING: recreating CSV "
            f"{path} ({ex})"
        )

    row_df.to_csv(path, index=False)


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
            f"WARNING: recreating Excel "
            f"{path} ({ex})"
        )

    row_df.to_excel(path, index=False)


# ==========================================================
# ANALYSIS
# ==========================================================

def analyse_stock(stock):

    nse = NSE()

    result = nse.equityOptions.option_chain(
        stock
    )

    if result is None:
        raise ValueError(
            f"No data returned for {stock}"
        )

    # pnsea returns:
    # (
    #   dataframe,
    #   expiry_dates,
    #   spot_price
    # )

    df = result[0]
    expiry_dates = result[1]
    spot = float(result[2])


    raw_file = (
    DERIVATIVE_DIR /
    f"{stock.upper()}_option_chain.csv"
)

    df.to_csv(raw_file, index=False)

    if df is None or len(df) == 0:

        raise ValueError(
            f"No option chain rows for {stock}"
        )

    df = df.fillna(0)

    required_cols = [
        "strikePrice",
        "CE_openInterest",
        "CE_changeinOpenInterest",
        "CE_totalTradedVolume",
        "PE_openInterest",
        "PE_changeinOpenInterest",
        "PE_totalTradedVolume"
    ]

    for col in required_cols:

        if col not in df.columns:

            raise ValueError(
                f"Missing column: {col}"
            )

    # --------------------------------------
    # Ignore deep OTM strikes
    # --------------------------------------

    lower = spot * 0.85
    upper = spot * 1.15

    df = df[
        (df["strikePrice"] >= lower)
        &
        (df["strikePrice"] <= upper)
    ].copy()

    # --------------------------------------
    # Weighted Scores
    # --------------------------------------

    df["PutScore"] = (
        (df["PE_openInterest"] * 0.60)
        +
        (df["PE_changeinOpenInterest"] * 0.30)
        +
        (df["PE_totalTradedVolume"] * 0.10)
    )

    df["CallScore"] = (
        (df["CE_openInterest"] * 0.60)
        +
        (df["CE_changeinOpenInterest"] * 0.30)
        +
        (df["CE_totalTradedVolume"] * 0.10)
    )

    # --------------------------------------
    # Support / Resistance
    # --------------------------------------

    supports = df[
        df["strikePrice"] < spot
    ].copy()

    resistances = df[
        df["strikePrice"] > spot
    ].copy()

    if supports.empty:

        raise ValueError(
            "No support strikes found"
        )

    if resistances.empty:

        raise ValueError(
            "No resistance strikes found"
        )

    strongest_support = (
        supports
        .sort_values(
            "PutScore",
            ascending=False
        )
        .iloc[0]
    )

    strongest_resistance = (
        resistances
        .sort_values(
            "CallScore",
            ascending=False
        )
        .iloc[0]
    )

    # --------------------------------------
    # PCR
    # --------------------------------------

    total_put_oi = (
        df["PE_openInterest"]
        .sum()
    )

    total_call_oi = (
        df["CE_openInterest"]
        .sum()
    )

    pcr = (
        total_put_oi / total_call_oi
        if total_call_oi > 0
        else 0
    )

    # --------------------------------------
    # Build-up
    # --------------------------------------

    put_buildup = (
        df["PE_changeinOpenInterest"]
        .sum()
    )

    call_buildup = (
        df["CE_changeinOpenInterest"]
        .sum()
    )

    # --------------------------------------
    # Bias
    # --------------------------------------

    if pcr > 1.20:

        bias = "BULLISH"

    elif pcr < 0.80:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL"

    # --------------------------------------
    # Top OI Walls
    # --------------------------------------

    top_puts = (
        supports
        .sort_values(
            "PutScore",
            ascending=False
        )
        .head(10)
    )

    top_calls = (
        resistances
        .sort_values(
            "CallScore",
            ascending=False
        )
        .head(10)
    )

    # --------------------------------------
    # Console Report
    # --------------------------------------

    print()
    print("=" * 70)
    print(f"{stock} DERIVATIVE REPORT")
    print("=" * 70)

    print(
        f"Spot Price           : {spot:.2f}"
    )

    print(
        f"Nearest Expiry       : "
        f"{expiry_dates[0] if expiry_dates else 'N/A'}"
    )

    print(
        f"Strong Support       : "
        f"{strongest_support['strikePrice']}"
    )

    print(
        f"Strong Resistance    : "
        f"{strongest_resistance['strikePrice']}"
    )

    print(
        f"PCR                  : {pcr:.2f}"
    )

    print(
        f"Put Build-up         : "
        f"{put_buildup:,.0f}"
    )

    print(
        f"Call Build-up        : "
        f"{call_buildup:,.0f}"
    )

    print(
        f"Bias                 : {bias}"
    )

    print("=" * 70)

    print("\nTop Put Walls")

    print(
        top_puts[
            [
                "strikePrice",
                "PE_openInterest",
                "PutScore"
            ]
        ]
    )

    print("\nTop Call Walls")

    print(
        top_calls[
            [
                "strikePrice",
                "CE_openInterest",
                "CallScore"
            ]
        ]
    )

    return {
        "Run Date":
            datetime.now().strftime(
                "%Y-%m-%d"
            ),

        "Stock":
            stock,

        "Spot":
            round(spot, 2),

        "Support":
            float(
                strongest_support[
                    "strikePrice"
                ]
            ),

        "Support Score":
            round(
                float(
                    strongest_support[
                        "PutScore"
                    ]
                ),
                0
            ),

        "Resistance":
            float(
                strongest_resistance[
                    "strikePrice"
                ]
            ),

        "Resistance Score":
            round(
                float(
                    strongest_resistance[
                        "CallScore"
                    ]
                ),
                0
            ),

        "PCR":
            round(pcr, 2),

        "Put Build-up":
            round(
                float(put_buildup),
                0
            ),

        "Call Build-up":
            round(
                float(call_buildup),
                0
            ),

        "Bias":
            bias
    }


# ==========================================================
# SAVE
# ==========================================================

def save_record(record):

    REPORT_DIR.mkdir(
        exist_ok=True
    )

    STOCK_DIR.mkdir(
        exist_ok=True
    )

    row = pd.DataFrame([record])

    append_csv(
        REPORT_DIR /
        "derivative_history.csv",
        row
    )

    append_excel(
        REPORT_DIR /
        "derivative_history.xlsx",
        row
    )

    append_excel(
        STOCK_DIR /
        f"{record['Stock']}_derivative_history.xlsx",
        row
    )


# ==========================================================
# MAIN
# ==========================================================

def main():

    if len(sys.argv) > 1:

        stocks = [
            sys.argv[1].upper()
        ]

    else:

        stocks = load_watchlist()

    if not stocks:

        print(
            "No stocks configured"
        )

        return

    for stock in stocks:

        try:

            record = analyse_stock(
                stock
            )

            save_record(
                record
            )

        # except Exception as ex:

        #     print(
        #         f"Failed {stock}: {ex}"
        #     )


        #     import traceback

        except Exception:

            print(
                f"\nFAILED: {stock}"
            )

            traceback.print_exc()


if __name__ == "__main__":
    main()