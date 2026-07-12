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
MAX_POSITION_PCT = 0.13       # Never put more than 13% in one stock (allows NVDA/AVGO ballast, forces breadth)
MAX_TRADES_PER_SESSION = 6    # Max trades Claude can recommend per analysis (wider basket maintenance)
MIN_CASH_RESERVE_PCT = 0.10   # Always keep 10% cash
STRATEGY = "swing"            # Hold days to weeks, not day trading

# Target portfolio for the clean-slate deploy (deploy_portfolio.py). Weights = % of equity.
# AI infrastructure ex-mega-cap (~58%) + emerging biotech, half-size, approval-risk tilt (~28%).
# ~12% cash reserve. Reshaped 2026-07-12 from grounded scout + Biotech registry research.
TARGET_PORTFOLIO = {
    # AI infrastructure (ballast + diversified sleeve)
    "NVDA": 0.12,   # accelerators, ballast
    "AVGO": 0.10,   # accelerators + custom ASIC + networking, ballast
    "TSM": 0.07,    # foundry
    "ANET": 0.07,   # networking / switching
    "VST": 0.07,    # power / energy (cheapest quality)
    "VRT": 0.06,    # cooling / thermal (half-size, rich)
    "MU": 0.05,     # memory / HBM (half-size, cyclical peak)
    "ALAB": 0.04,   # interconnect (half-size, very rich)
    # Emerging biotech (all half-size; approval-risk tilt; catalysts spread Sep 2026 -> Feb 2027)
    "COGT": 0.045,  # GIST + mastocytosis PDUFAs Nov/Dec 2026
    "PTGX": 0.045,  # rusfertide PDUFA Q3 2026 (polycythemia vera)
    "BBIO": 0.045,  # BBP-418 PDUFA Nov 2026 (LGMD), revenue-backed
    "SRRK": 0.04,   # apitegromab PDUFA Sep 2026 (SMA)
    "RARE": 0.04,   # UX111 PDUFA Sep 2026 (Sanfilippo gene therapy)
    "PCVX": 0.035,  # VAX-31 topline Q4 2026 (immunobridging endpoint)
    "CGEM": 0.03,   # zipalertinib PDUFA Feb 2027 (EGFR ex20 NSCLC)
}

# Claude API
ANALYSIS_MODEL = "claude-sonnet-5"  # Sonnet 5 for daily analysis (cost-efficient); prior ID claude-sonnet-4-20250514 retired ~May 2026 and silently 404'd the engine for 2 months
DEEP_ANALYSIS_MODEL = "claude-opus-4-8"  # Opus 4.8 for deep analysis when needed

# Notion DB IDs (page IDs for pages.create, data source IDs for querying)
TRADE_LOG_DB = "abfc7ab1-17ad-44d2-a510-8bf39269d3fa"
TRADE_LOG_DS = "23aec1ab-34bc-468e-a809-79c6ddb05aab"
PERFORMANCE_REPORTS_DB = "005d0307-f9b1-4dca-9213-8a48745ee659"
# Current Holdings page (refreshed by positions_page.py on every trade + trading day)
POSITIONS_PAGE_ID = "39bf3cdd-67a4-816a-b0c2-ecb3236b02c0"
