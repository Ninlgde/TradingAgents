"""Quick AAPL technical-indicator sanity check (no LLM / API key needed).

Usage:
    conda activate tradingagents
    cd ~/Desktop/source/TradingAgents
    python scripts/quick_ta.py [YYYY-MM-DD]

The date defaults to 2026-08-03 (most recent completed trading day when
written). Pass a different date as argv[1] if needed.
"""
import sys

from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-08-03"

for indicator in ["macd", "rsi", "close_50_sma"]:
    print(f"\n===== AAPL {indicator} (30-day lookback, as of {DATE}) =====")
    try:
        print(get_stock_stats_indicators_window("AAPL", indicator, DATE, 30))
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
