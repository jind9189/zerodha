import json
import os
import sys
import pandas as pd
import yfinance as yf
from google import genai
from google.genai import types
from dotenv import load_dotenv
from paths import CASH_DIR

# Load environment variables (.env configuration)
load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    print("❌ ERROR: GEMINI_API_KEY not found in environment variables or .env file.")
    exit(1)

client = genai.Client()


DATA_DIR = CASH_DIR
CONFIG_FILE = "config.json"
# Detect whether a config file existed before this run; used to decide scanning behavior
config_provided = os.path.exists(CONFIG_FILE)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def load_configuration():
    """Loads default configurations without bias overhead strings"""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            "watchlist": ["PAYTM", "HDFCBANK", "INFY", "TCS", "RELIANCE"],
            "ichimoku_settings": {"tenkan_period": 9, "kijun_period": 26, "senkou_span_b_period": 52}
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config

def calculate_ichimoku(df, settings):
    """Computes technical parameters locally on your system CPU"""
    high_t = df['High'].rolling(window=settings['tenkan_period']).max()
    low_t = df['Low'].rolling(window=settings['tenkan_period']).min()
    df['Tenkan'] = (high_t + low_t) / 2

    high_k = df['High'].rolling(window=settings['kijun_period']).max()
    low_k = df['Low'].rolling(window=settings['kijun_period']).min()
    df['Kijun'] = (high_k + low_k) / 2
    return df

def fetch_real_historical_data(symbol):
    """Pulls genuine historical metrics; utilizes local CSV storage if available"""
    clean_symbol = str(symbol).strip().upper()
    csv_path = DATA_DIR / f"{clean_symbol}.csv"
    
    if csv_path.exists():
        return pd.read_csv(csv_path, index_col=0, parse_dates=True)
        
    print(f"🌐 [Cache Miss] Downloading data from Yahoo Finance for {clean_symbol}...")
    ticker_map = {
        "PAYTM": "PAYTM.NS", "HDFCBANK": "HDFCBANK.NS", 
        "INFY": "INFY.NS", "TCS": "TCS.NS", "RELIANCE": "RELIANCE.NS"
    }
    ticker_symbol = ticker_map.get(clean_symbol, f"{clean_symbol}.NS")
    
    df = yf.download(ticker_symbol, period="3mo", progress=False)
    if df.empty:
        raise ValueError(f"No records found for token: {ticker_symbol}")
        
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    df.to_csv(csv_path)
    return df

def perform_llm_research(symbol, current_price, tenkan, kijun):
    """
    Sends the localized numbers to Gemini.
    The AI automatically deduces if the trend layout is BULLISH or BEARISH.
    """
    prompt = f"""
    Analyze this Indian stock market snapshot for ticker: {symbol}.
    
    Current Metrics:
    - Last Traded Price (LTP): ₹{current_price:.2f}
    - Ichimoku Tenkan-sen: ₹{tenkan:.2f}
    - Ichimoku Kijun-sen: ₹{kijun:.2f}
    
    Task:
    1. Determine the directional trend bias (Return "POSITIVE" if price is safely above Kijun-sen, or "NEGATIVE" if trailing below).
    2. Based on that automated bias assessment, calculate a logical 7-day Stop Loss and Target price respecting a 1:2 risk-to-reward ratio.
    3. Provide a brief technical reason under 20 words to save tokens.
    
    Return strictly in JSON format matching these exact four keys:
    "rationale", "bias", "stop_loss", "target".
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        )
        return json.loads(response.text)
    except Exception as e:
        return {"rationale": "Fallback triggered.", "bias": "NEUTRAL", "stop_loss": round(current_price * 0.96, 2), "target": round(current_price * 1.08, 2)}

def main():
    config = load_configuration()
    
    # -------------------------------------------------------------
    # SIMPLIFIED ARGUMENT ROUTER
    # -------------------------------------------------------------
    # If any word is passed after scanner.py, target that specific stock instantly
    if len(sys.argv) >= 2:
        input_stock = str(sys.argv[1]).strip().upper()
        watchlist = [input_stock]
        print(f"🎯 [On-The-Fly Single Mode] Scanning: {input_stock}")
    else:
        # If a config file was provided (exists before this run), honor its watchlist only
        if config_provided:
            watchlist = config.get('watchlist', [])
            print(f"📋 [Standard Mode] Using watchlist from {CONFIG_FILE} ({len(watchlist)} symbols).")
        else:
            # No config present before run - fall back to scanning all CSVs in local_stock_data
            watchlist = [
                    f.stem.upper()
                    for f in DATA_DIR.glob("*.csv")
]
            print(f"📁 [Fallback Mode] No config provided; scanning all local_stock_data ({len(watchlist)} symbols).")
    # -------------------------------------------------------------

    results = []
    for stock in watchlist:
        try:
            df = fetch_real_historical_data(stock)
            df = calculate_ichimoku(df, config['ichimoku_settings'])
            
            df_one_month = df.tail(22)
            latest = df_one_month.iloc[-1]
            current_price = float(latest['Close'])
            t_val = float(latest['Tenkan'])
            k_val = float(latest['Kijun'])
            
            # The AI takes the values and finds the bias automatically
            analysis = perform_llm_research(stock, current_price, t_val, k_val)
            
            results.append({
                "Stock": stock.upper(), 
                "LTP": round(current_price, 2),
                "Bias": str(analysis.get("bias")).upper(),
                "Stop Loss": analysis.get("stop_loss"), 
                "Target": analysis.get("target"),
                "AI Rationale": analysis.get("rationale")
            })
        except Exception as err:
            print(f"❌ Skipped {stock}: {err}")

    if results:
        output_df = pd.DataFrame(results)
        # Save compact JSON summary (xlsx not required)
        output_df.to_json("trading_setup_output.json", orient="records", indent=2)
        print("\n", output_df[["Stock", "LTP", "Bias", "Stop Loss", "Target"]].to_string(index=False))

if __name__ == "__main__":
    main()