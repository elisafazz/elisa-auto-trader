import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Trading mode
PAPER_TRADING = True

# Strategy parameters
MAX_POSITION_PCT = 0.20       # Never put more than 20% in one stock
MAX_TRADES_PER_SESSION = 3    # Max trades Claude can recommend per analysis
MIN_CASH_RESERVE_PCT = 0.10   # Always keep 10% cash
STRATEGY = "swing"            # Hold days to weeks, not day trading

# Claude API
ANALYSIS_MODEL = "claude-sonnet-4-20250514"  # Sonnet for daily analysis (cost-efficient)
DEEP_ANALYSIS_MODEL = "claude-sonnet-4-20250514"  # Upgrade to Opus when needed

# Notion DB IDs
TRADE_LOG_DB = "23aec1ab-34bc-468e-a809-79c6ddb05aab"
PERFORMANCE_REPORTS_DB = "e4216810-2905-4027-baf5-112716f3697d"
