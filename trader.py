import subprocess
import alpaca_client
import analyst
import notion_logger
import config


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

    print("Analyzing portfolio with Claude...\n")
    result = analyst.analyze(account, positions, recent_orders, price_data)

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
