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

# Thesis (Elisa, set 2026-07-06; watchlist reshaped 2026-07-12 via /portfolio-review):
# AI INFRASTRUCTURE, ex-mega-cap (picks-and-shovels: chips/memory/networking/power/
# cooling), NOT the hyperscalers (GOOGL/MSFT/AMZN/META excluded), plus EMERGING/budding
# biotech (not big pharma). Barbell: NVDA/AVGO ballast + smaller infra & biotech sleeve.

# Tier 1 -- daily analyst should actively consider these
# AI-infra scout 2026-07-12 (grounded, filings/earnings-verified, auto-fails checked):
WATCHLIST_AI = [
    # Ballast (NVDA-class large infra)
    "NVDA",   # Nvidia -- CUDA moat, Blackwell ramp, Strong Buy (26/30, GREEN)
    "AVGO",   # Broadcom -- custom ASIC + networking, Strong Buy (27/30, GREEN); prior
              # 2026-04 CFO/antitrust auto-fail cleared, re-added 2026-07-12
    # Smaller infra sleeve
    "VRT",    # Vertiv -- liquid cooling, $15B backlog (25/30, GREEN)
    "CEG",    # Constellation -- nuclear PPAs for data centers, reasonably valued (25/30, GREEN)
    "MU",     # Micron -- HBM sold out on multi-year deals (24/30, GREEN); size cycle risk
    "ALAB",   # Astera Labs -- connectivity/scale-up switch (24/30, YELLOW); half-size, rich multiple
    "TSM",    # Taiwan Semi -- foundry monopoly, held; borderline-infra ballast (23)
    # SMCI auto-fail (active DOJ export-control matter). MRVL auto-fail (CFO departure
    # <90d) -- re-evaluate ~2026-09-13. GOOGL/MSFT dropped 2026-07-12 (mega-cap, off-thesis).
]

# Emerging/budding biotech -- sourced from the Biotech & Tech-Bio registry by Investment
# Score (2026-07-12), replacing big-pharma names. High-variance: small sleeve, half-size.
WATCHLIST_BIOTECH = [
    "KARD",   # Kardigan -- registry Investment Score 72
    "LRMR",   # Larimar Therapeutics -- score 70, Phase 3
    "ABSI",   # Absci -- score 70, AI drug discovery / tech-bio platform
    "PRAX",   # Praxis Precision Medicine -- score 65, Phase 3
    "DNLI",   # Denali Therapeutics -- score 65
    "GH",     # Guardant Health -- score 62, clinical-AI & diagnostics
    # Dropped 2026-07-12 (off-thesis big pharma / broad ETF): LLY, VRTX, REGN, IBB.
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
        f"\nSECTOR FOCUS (thesis set 2026-07-06):\n"
        f"Elisa's allocation thesis is AI INFRASTRUCTURE, ex-mega-cap -- the picks-and-shovels "
        f"layer (chips/accelerators, memory, networking, power, cooling, data-center), NOT the "
        f"hyperscalers. Do NOT open new positions in the mega-cap platform names GOOGL, MSFT, "
        f"AMZN, or META. The second sleeve is EMERGING/budding biotech (small/mid-cap, clinical, "
        f"AI drug discovery), NOT big pharma. Barbell: keep large infra ballast plus a smaller "
        f"higher-upside sleeve.\n"
        f"When conviction is comparable, prefer these watchlist names:\n"
        f"- AI infrastructure: {ai_list}\n"
        f"- Emerging biotech: {biotech_list}\n"
        f"Do not force trades into these names, but treat them as preferred candidates "
        f"for new positions. Avoid the following (binary catalysts, strategy mismatch): "
        f"{', '.join(WATCHLIST_MANUAL_ONLY)}."
    )
