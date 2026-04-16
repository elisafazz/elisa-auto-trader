"""Curated watchlist of AI and biotech tickers for the auto-trader analyst.

Populated by the `company-scout` agent after adversarial Claude + Gemini review.
Tiers reflect pre-run expectations; actual tier assignment happens during scout runs.

Update process:
1. Run `/scout-companies ai` or `/scout-companies biotech`
2. Review the scorecard output
3. Add Tier 1 (Strong Buy) picks to WATCHLIST_AI / WATCHLIST_BIOTECH below
4. Move demoted picks to SKIP for documentation
5. Commit + push so the daily analyst sees the update
"""

# Tier 1 -- daily analyst should actively consider these
WATCHLIST_AI = [
    "GOOGL",  # Google -- Gemini + TPU + cheap multiple (top AI pick, score 26)
    "MSFT",   # Microsoft -- platform AI, lowest binary (24)
    "TSM",    # Taiwan Semi -- fab monopoly (23)
    # AVGO removed 2026-04-16: CFO retirement <90d + EU antitrust filing triggered
    # auto-fail per checklist. Re-evaluate after new CFO seated (est Q4 2026).
]

WATCHLIST_BIOTECH = [
    "LLY",    # Eli Lilly -- GLP-1 monopoly
    "VRTX",   # Vertex -- CF + pain + gene therapy, cash-rich
    "REGN",   # Regeneron -- Dupixent + EYLEA, reasonable multiple
    "IBB",    # iShares biotech ETF -- diversifies single-name binary risk
]

# Manual-only -- never auto-trade (binary catalysts, strategy mismatch)
WATCHLIST_MANUAL_ONLY = [
    "VKTX",   # Viking Tx -- Phase 3 catalyst in 2026
    "SMMT",   # Summit Tx -- ivonescimab trials 2026-2027
    "CRSP",   # CRISPR Tx -- small-cap gene therapy
    "SDGR",   # Schrodinger -- small-cap AI-drug discovery
    "PLTR",   # Palantir -- extreme valuation overlay
]


def all_watched():
    """Return combined list for get_bars() and get_news() calls."""
    return WATCHLIST_AI + WATCHLIST_BIOTECH


def sector_bias_prompt():
    """Return a short paragraph to append to the analyst SYSTEM_PROMPT."""
    ai_list = ", ".join(WATCHLIST_AI)
    biotech_list = ", ".join(WATCHLIST_BIOTECH)
    return (
        f"\nSECTOR FOCUS:\n"
        f"Elisa has expressed interest in AI and biotech as long-term allocation themes. "
        f"When conviction is comparable, prefer these watchlist names:\n"
        f"- AI: {ai_list}\n"
        f"- Biotech: {biotech_list}\n"
        f"Do not force trades into these names, but treat them as preferred candidates "
        f"for new positions. Avoid the following (binary catalysts, strategy mismatch): "
        f"{', '.join(WATCHLIST_MANUAL_ONLY)}."
    )
