"""Non-interactive single-stock analysis via DeepSeek, Chinese output.

Usage (from repo root, with proxy exported if needed):
    python scripts/run_stock.py <TICKER> [YYYY-MM-DD] [analyst1,analyst2,...]

Examples:
    python scripts/run_stock.py 600036.SS 2026-08-04 market,fundamentals
    python scripts/run_stock.py AAPL 2026-08-03 market
"""
import json
import os
import sys

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

ticker = sys.argv[1] if len(sys.argv) > 1 else "600036.SS"
date = sys.argv[2] if len(sys.argv) > 2 else "2026-08-04"
analysts = (
    tuple(a.strip() for a in sys.argv[3].split(","))
    if len(sys.argv) > 3 and sys.argv[3].strip()
    else ("market", "fundamentals")
)

RUN_DIR = os.path.join(os.getcwd(), ".ta_run")
for d in ("results", "cache", "memory"):
    os.makedirs(os.path.join(RUN_DIR, d), exist_ok=True)

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-v4-flash"
config["quick_think_llm"] = "deepseek-v4-flash"
config["output_language"] = "Chinese"
config["checkpoint_enabled"] = False
config["results_dir"] = os.path.join(RUN_DIR, "results")
config["data_cache_dir"] = os.path.join(RUN_DIR, "cache")
config["memory_log_path"] = os.path.join(RUN_DIR, "memory", "trading_memory.md")

ta = TradingAgentsGraph(selected_analysts=analysts, debug=True, config=config)
state, decision = ta.propagate(ticker, date)

print("\n\n========== FINAL DECISION ==========")
print(decision)

out = {k: state.get(k) for k in ("market_report", "fundamentals_report", "final_trade_decision")}
out_path = os.path.join(RUN_DIR, "results", f"{ticker.replace('.', '_')}_{date}_result.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\nsaved -> {out_path}")
