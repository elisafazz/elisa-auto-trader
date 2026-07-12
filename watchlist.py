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

# Tier 1 -- daily analyst should actively consider these.
# Full basket reshape 2026-07-12 (grounded AI-infra scout, filings/earnings-verified, auto-fails
# checked). Diversified across the AI-infra stack, not 2 chip names.
WATCHLIST_AI = [
    # Ballast (NVDA-class large infra)
    "NVDA",   # Nvidia -- accelerators, CUDA moat, Blackwell ramp (Strong Buy 26/30, GREEN)
    "AVGO",   # Broadcom -- custom ASIC + networking (Strong Buy 28/30, GREEN)
    # Diversified sleeve, one per sub-sector
    "TSM",    # Taiwan Semi -- foundry (23, GREEN)
    "ANET",   # Arista -- networking / switching (Strong Buy 26/30, GREEN)
    "VST",    # Vistra -- power / energy, cheapest quality ~18x (24/30, GREEN)
    "VRT",    # Vertiv -- cooling / thermal, $15B backlog (Strong Buy 26/30, GREEN); half-size
    "MU",     # Micron -- memory / HBM, sold out (22/30, YELLOW); half-size, cyclical peak
    "ALAB",   # Astera Labs -- interconnect (25/30, GREEN); half-size, very rich
    # SMCI auto-fail (active DOJ export-control matter). MRVL auto-fail (CFO departure <90d) --
    # re-eligible ~2026-09-13. GOOGL/MSFT excluded (mega-cap hyperscalers, off-thesis).
]

# Emerging biotech -- near-term, likely-positive clinical/FDA catalysts (grounded research
# 2026-07-12). All HALF-SIZE (binary catalyst risk); tilted to APPROVAL-risk (positive pivotal
# already in hand, awaiting PDUFA) over pending-data readouts. Catalysts spread Sep 2026 -> Feb 2027.
WATCHLIST_BIOTECH = [
    "COGT",   # Cogent -- GIST PDUFA Nov 30 + mastocytosis Dec 30 2026 (two approvals)
    "PTGX",   # Protagonist -- rusfertide PDUFA Q3 2026 (polycythemia vera)
    "BBIO",   # BridgeBio -- BBP-418 PDUFA Nov 27 2026 (LGMD), revenue-backed
    "SRRK",   # Scholar Rock -- apitegromab PDUFA Sep 30 2026 (SMA)
    "RARE",   # Ultragenyx -- UX111 PDUFA Sep 19 2026 (Sanfilippo gene therapy)
    "PCVX",   # Vaxcyte -- VAX-31 topline Q4 2026 (immunobridging endpoint)
    "CGEM",   # Cullinan -- zipalertinib PDUFA Feb 27 2027 (EGFR ex20 NSCLC)
    # Excluded on auto-fail / pure binary data-readout (see MANUAL_ONLY): CLDX, SMMT, SVRA, CAPR, LRMR.
    # Big pharma dropped as off-thesis: LLY, VRTX, REGN, IBB.
]

# Manual-only -- never auto-trade (pure binary data-readouts, auto-fail flags, strategy mismatch)
WATCHLIST_MANUAL_ONLY = [
    "CLDX",   # Celldex -- barzolvolimab Phase 3 CSU readout Q4 2026 (data-risk, high variance)
    "SMMT",   # Summit -- ivonescimab; mixed OS/squamous data + funding overhang
    "SVRA",   # Savara -- single-product aPAP PDUFA (high single-name variance)
    "CAPR",   # Capricor -- deramiocel post-CRL resubmission (auto-fail: prior CRL)
    "LRMR",   # Larimar -- nomlabofusp; anaphylaxis safety signal + plaintiff probe (auto-fail flags)
    "VKTX",   # Viking Tx -- make-or-break obesity Phase 3 not until 2027 (out of window)
    "CRSP",   # CRISPR Tx -- small-cap gene therapy, binary
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
        f"\nSECTOR FOCUS (thesis set 2026-07-06, basket built 2026-07-12):\n"
        f"Elisa's allocation thesis is AI INFRASTRUCTURE, ex-mega-cap -- the picks-and-shovels "
        f"layer (chips/accelerators, memory, networking, power, cooling, data-center), NOT the "
        f"hyperscalers. Do NOT open new positions in the mega-cap platform names GOOGL, MSFT, "
        f"AMZN, or META. The second sleeve is EMERGING biotech with near-term, likely-positive "
        f"clinical/FDA catalysts, NOT big pharma.\n"
        f"PORTFOLIO CONSTRUCTION:\n"
        f"- Maintain a DIVERSIFIED basket of roughly 12-15 on-thesis names across sub-sectors; do "
        f"NOT concentrate into a few names.\n"
        f"- Size each EMERGING BIOTECH position at HALF a normal position -- they carry binary "
        f"catalyst risk (a single FDA/trial readout can gap 40-70%).\n"
        f"- If any OFF-THESIS legacy name is held (mega-cap, big pharma, broad ETF), prefer trimming "
        f"or exiting it in favor of on-thesis names.\n"
        f"When conviction is comparable, prefer these watchlist names:\n"
        f"- AI infrastructure: {ai_list}\n"
        f"- Emerging biotech (half-size): {biotech_list}\n"
        f"Do not force trades, but treat these as the preferred universe. NEVER auto-trade the "
        f"following (binary data-readouts, auto-fail flags, strategy mismatch): "
        f"{', '.join(WATCHLIST_MANUAL_ONLY)}."
    )
