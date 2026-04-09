import json
import anthropic
import config

SYSTEM_PROMPT = """You are a swing trading analyst managing a small paper trading portfolio.

STRATEGY RULES:
- Swing trading only: hold positions for days to weeks, not intraday
- Maximum {max_position_pct}% of portfolio in any single position
- Keep at least {min_cash_pct}% of portfolio in cash at all times
- Maximum {max_trades} trade recommendations per session
- Focus on high-conviction ideas with clear catalysts
- Consider tax implications: avoid rapid round-trips that create wash sales

ANALYSIS APPROACH:
1. Review current portfolio and open positions
2. Consider macro environment and sector trends
3. Look for asymmetric risk/reward setups
4. Provide specific, actionable recommendations with clear reasoning

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
  "market_summary": "2-3 sentence market overview",
  "recommendations": [
    {{
      "symbol": "TICKER",
      "action": "buy" or "sell",
      "amount_usd": 1000.00,
      "reasoning": "2-3 sentences explaining why",
      "confidence": "high" or "medium" or "low",
      "hold_period": "1-2 weeks",
      "risk": "brief risk note"
    }}
  ]
}}

If no trades are warranted, return an empty recommendations array with an explanation in market_summary.
""".format(
    max_position_pct=int(config.MAX_POSITION_PCT * 100),
    min_cash_pct=int(config.MIN_CASH_RESERVE_PCT * 100),
    max_trades=config.MAX_TRADES_PER_SESSION,
)


def analyze(account, positions, recent_orders, price_data=None, news=None):
    """Call Claude to analyze the portfolio and generate trade recommendations."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    portfolio_context = f"""CURRENT PORTFOLIO:
- Cash: ${account['cash']:,.2f}
- Portfolio Value: ${account['portfolio_value']:,.2f}
- Buying Power: ${account['buying_power']:,.2f}

OPEN POSITIONS:
"""
    if positions:
        for p in positions:
            portfolio_context += (
                f"- {p['symbol']}: {p['qty']} shares @ ${p['avg_entry_price']:.2f} "
                f"(now ${p['current_price']:.2f}, P&L: ${p['unrealized_pl']:.2f} / "
                f"{p['unrealized_plpc']:.1%})\n"
            )
    else:
        portfolio_context += "- No open positions\n"

    portfolio_context += "\nRECENT ORDERS:\n"
    if recent_orders:
        for o in recent_orders[:5]:
            portfolio_context += f"- {o['side']} {o['symbol']} | status: {o['status']}\n"
    else:
        portfolio_context += "- No recent orders\n"

    if price_data:
        portfolio_context += "\nRECENT PRICE DATA (last 10 trading days):\n"
        for symbol, bars in price_data.items():
            if bars:
                latest = bars[-1]
                earliest = bars[0]
                change_pct = ((latest['close'] - earliest['close']) / earliest['close']) * 100
                portfolio_context += (
                    f"- {symbol}: ${latest['close']:.2f} (10d change: {change_pct:+.1f}%, "
                    f"range: ${min(b['low'] for b in bars):.2f}-${max(b['high'] for b in bars):.2f}, "
                    f"avg vol: {sum(b['volume'] for b in bars) // len(bars):,})\n"
                )

    if news:
        portfolio_context += "\nMARKET NEWS (last 48 hours):\n"
        for n in news[:10]:
            syms = ", ".join(n["symbols"][:3]) if n["symbols"] else "general"
            portfolio_context += f"- [{syms}] {n['headline']}"
            if n["summary"]:
                portfolio_context += f" -- {n['summary'][:150]}"
            portfolio_context += "\n"

    portfolio_context += (
        "\nAnalyze the current market conditions and my portfolio. "
        "What trades, if any, should I make today?"
    )

    response = client.messages.create(
        model=config.ANALYSIS_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": portfolio_context}],
    )

    raw = response.content[0].text

    # Parse JSON from response, stripping markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    return json.loads(text)
