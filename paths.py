from pathlib import Path

BASE_DIR = Path(__file__).parent

HISTORY_DIR = BASE_DIR / "historyData"

CASH_DIR = HISTORY_DIR / "cash"
DERIVATIVE_DIR = HISTORY_DIR / "derivative"

REPORT_DIR = BASE_DIR / "reports"
STOCK_REPORT_DIR = REPORT_DIR / "stocks"

for folder in [
    CASH_DIR,
    DERIVATIVE_DIR,
    REPORT_DIR,
    STOCK_REPORT_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)
    