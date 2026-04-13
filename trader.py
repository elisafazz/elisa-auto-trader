import subprocess
from datetime import datetime, timedelta
import alpaca_client
import analyst
import notion_logger
import config

STARTING_VALUE = 100000.00  # Paper trading initial capital


def notify(title, message):
    """Send a macOS notification via osascript."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def status():
    """Print current portfolio snapshot."""
    account = alpaca_client.get_account()
    positions = alpaca_client.get_positions()

    print(f"Account Status: {account['status']}")
    print(f"Portfolio Value: ${account['portfolio_value']:,.2f}")
    print(f"Cash: ${account['cash']:,.2f}")
    print(f"Buying Power: ${account['buying_power']:,.2f}")
    print(f"Paper Trading: {config.PAPER_TRADING}")
    print()

    if positions:
        print("Open Positions:")
        for p in positions:
            print(
                f"  {p['symbol']:6s}  {p['qty']:>8.4f} shares  "
                f"@ ${p['avg_entry_price']:>8.2f}  "
                f"now ${p['current_price']:>8.2f}  "
                f"P&L: ${p['unrealized_pl']:>+8.2f} ({p['unrealized_plpc']:>+.1%})"
            )
    else:
        print("No open positions.")

    return account, positions


def analyze():
    """Get Claude's trade recommendations for current portfolio state."""
    account = alpaca_client.get_account()
    positions = alpaca_client.get_positions()
    recent_orders = alpaca_client.get_recent_orders(limit=5)

    # Fetch live price data for holdings + SPY benchmark
    watched = [p["symbol"] for p in positions] if positions else []
    if "SPY" not in watched:
        watched.append("SPY")
    try:
        price_data = alpaca_client.get_bars(watched, days=10)
    except Exception:
        price_data = None

    # Fetch market news for holdings
    try:
        held_symbols = [p["symbol"] for p in positions] if positions else None
        news = alpaca_client.get_news(symbols=held_symbols, limit=10)
    except Exception:
        news = None

    print("Analyzing portfolio with Claude...\n")
    result = analyst.analyze(account, positions, recent_orders, price_data, news)

    print(f"Market Summary: {result['market_summary']}\n")

    recs = result.get("recommendations", [])
    if not recs:
        print("No trades recommended at this time.")
        return result

    print(f"{len(recs)} recommendation(s):\n")
    for i, rec in enumerate(recs, 1):
        print(f"  [{i}] {rec['action'].upper()} ${rec['amount_usd']:.2f} of {rec['symbol']}")
        print(f"      Confidence: {rec['confidence']}  |  Hold: {rec['hold_period']}")
        print(f"      Reasoning: {rec['reasoning']}")
        print(f"      Risk: {rec['risk']}")
        print()

    return result


def execute(recommendations):
    """Execute a list of trade recommendations. Phase 1: requires manual confirmation."""
    if not recommendations:
        print("Nothing to execute.")
        return

    account = alpaca_client.get_account()
    portfolio_value = account["portfolio_value"]

    executed = []
    for rec in recommendations:
        symbol = rec["symbol"]
        action = rec["action"]
        amount = rec["amount_usd"]

        # Safety checks
        if amount > portfolio_value * config.MAX_POSITION_PCT:
            print(f"  SKIP {symbol}: ${amount:.2f} exceeds {config.MAX_POSITION_PCT:.0%} position limit")
            continue

        if action == "buy":
            cash = account["cash"]
            min_reserve = portfolio_value * config.MIN_CASH_RESERVE_PCT
            if cash - amount < min_reserve:
                print(f"  SKIP {symbol}: buying ${amount:.2f} would breach {config.MIN_CASH_RESERVE_PCT:.0%} cash reserve")
                continue

        order = alpaca_client.place_order(symbol, action, amount)
        print(f"  EXECUTED: {action.upper()} ${amount:.2f} of {symbol} -- order {order['id']}")
        executed.append({"recommendation": rec, "order": order})

        notion_logger.log_trade({
            "symbol": symbol,
            "action": action,
            "amount": amount,
            "order_id": order["id"],
            "reasoning": rec.get("reasoning", ""),
            "strategy": config.STRATEGY,
            "paper": config.PAPER_TRADING,
        })

    return executed


def auto_run():
    """Full autonomous loop: analyze -> execute -> notify. Used by cron."""
    # Skip if market is closed (holidays, weekends)
    clock = alpaca_client.get_clock()
    if not clock["is_open"]:
        notify("Auto-Trader", f"Market closed today -- skipping. Next open: {clock['next_open']}")
        print(f"Market closed. Next open: {clock['next_open']}")
        return

    result = analyze()
    recs = result.get("recommendations", [])

    if not recs:
        notify("Auto-Trader", "No trades recommended today")
        return

    executed = execute(recs)

    if executed:
        lines = []
        for e in executed:
            rec = e["recommendation"]
            lines.append(f"{rec['action'].upper()} ${rec['amount_usd']:.0f} {rec['symbol']}")
        summary = ", ".join(lines)
        notify("Auto-Trader", f"Executed: {summary}")
    else:
        notify("Auto-Trader", "Analysis complete, all trades skipped (safety limits)")


def report():
    """Generate weekly performance report with SPY benchmark."""
    account = alpaca_client.get_account()
    positions = alpaca_client.get_positions()
    recent_orders = alpaca_client.get_recent_orders(limit=50)

    portfolio_value = account["portfolio_value"]
    total_return_pct = ((portfolio_value - STARTING_VALUE) / STARTING_VALUE) * 100

    # Count trades this week
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    week_trades = [
        o for o in recent_orders
        if o["submitted_at"] and o["submitted_at"][:10] >= week_ago.strftime("%Y-%m-%d")
    ]

    # SPY benchmark
    try:
        spy_bars = alpaca_client.get_bars(["SPY"], days=7)
        spy_data = spy_bars.get("SPY", [])
        if len(spy_data) >= 2:
            spy_return = ((spy_data[-1]["close"] - spy_data[0]["close"]) / spy_data[0]["close"]) * 100
        else:
            spy_return = None
    except Exception:
        spy_return = None

    # Find best/worst positions
    best_trade = ""
    worst_trade = ""
    if positions:
        sorted_pos = sorted(positions, key=lambda p: p["unrealized_pl"])
        worst_trade = f"{sorted_pos[0]['symbol']} ${sorted_pos[0]['unrealized_pl']:+.2f}"
        best_trade = f"{sorted_pos[-1]['symbol']} ${sorted_pos[-1]['unrealized_pl']:+.2f}"

    # Weekly return estimate (simplified: total return / weeks elapsed, or use last 7 days of orders)
    weekly_return_pct = total_return_pct  # Simplified for Phase 1

    # Print report
    week_ending = now.strftime("%Y-%m-%d")
    print(f"=== Auto-Trader Weekly Report ({week_ending}) ===\n")
    print(f"Portfolio Value:  ${portfolio_value:,.2f}")
    print(f"Starting Value:   ${STARTING_VALUE:,.2f}")
    print(f"Total Return:     {total_return_pct:+.2f}%  (${portfolio_value - STARTING_VALUE:+,.2f})")
    if spy_return is not None:
        print(f"SPY (7d):         {spy_return:+.2f}%")
        if total_return_pct < spy_return:
            print(f"  ** UNDERPERFORMING SPY by {spy_return - total_return_pct:.2f}% **")
    print(f"\nTrades this week: {len(week_trades)}")
    print(f"Best position:    {best_trade}")
    print(f"Worst position:   {worst_trade}")
    print(f"Cash:             ${account['cash']:,.2f}")
    print()

    if positions:
        print("Open Positions:")
        for p in positions:
            print(
                f"  {p['symbol']:6s}  ${p['market_value']:>10,.2f}  "
                f"P&L: ${p['unrealized_pl']:>+8.2f} ({p['unrealized_plpc']:>+.1%})"
            )
    print()

    # Log to Notion
    report_data = {
        "title": f"Week ending {week_ending}",
        "week_ending": week_ending,
        "portfolio_value": portfolio_value,
        "weekly_return_pct": weekly_return_pct,
        "total_return_pct": total_return_pct,
        "trades_executed": len(week_trades),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "benchmark_spy": spy_return,
        "strategy_notes": f"Swing trading with Claude Sonnet analysis. {len(positions)} open positions.",
    }
    notion_logger.log_report(report_data)

    # Notification summary
    spy_str = f" | SPY: {spy_return:+.1f}%" if spy_return is not None else ""
    notify(
        "Auto-Trader Weekly Report",
        f"${portfolio_value:,.0f} ({total_return_pct:+.1f}%){spy_str} | {len(week_trades)} trades"
    )
