import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

# Trading mode
PAPER_TRADING = True

# Strategy parameters
MAX_POSITION_PCT = 0.20       # Never put more than 20% in one stock
MAX_TRADES_PER_SESSION = 3    # Max trades Claude can recommend per analysis
MIN_CASH_RESERVE_PCT = 0.10   # Always keep 10% cash
STRATEGY = "swing"            # Hold days to weeks, not day trading

# Claude API
ANALYSIS_MODEL = "claude-sonnet-5"  # Sonnet 5 for daily analysis (cost-efficient); prior ID claude-sonnet-4-20250514 retired ~May 2026 and silently 404'd the engine for 2 months
DEEP_ANALYSIS_MODEL = "claude-opus-4-8"  # Opus 4.8 for deep analysis when needed

# Notion DB IDs (page IDs for pages.create, data source IDs for querying)
TRADE_LOG_DB = "abfc7ab1-17ad-44d2-a510-8bf39269d3fa"
TRADE_LOG_DS = "23aec1ab-34bc-468e-a809-79c6ddb05aab"
PERFORMANCE_REPORTS_DB = "005d0307-f9b1-4dca-9213-8a48745ee659"
