"""Clean-slate deploy: buy the target on-thesis basket into a freshly reset $100K paper account.

Elisa resets the Alpaca paper account to $100,000 in the dashboard first (which erases all old
positions). This module then buys config.TARGET_PORTFOLIO at target weights. Deterministic, no LLM.

Safety:
- Refuses to run if the account still holds positions (means the reset was not done) -- prevents
  buying on top of the old book.
- Default run PREVIEWS the buy plan and exits; requires execute=True (run.py --deploy --auto) to trade.

CLI: `python run.py --deploy`  (preview)  /  `python run.py --deploy --auto`  (execute)
"""

import config
import alpaca_client
import notion_logger


def _plan(base):
    """Return a list of (symbol, weight, dollars) for the target basket, ranked by weight."""
    rows = []
    for symbol, weight in config.TARGET_PORTFOLIO.items():
        rows.append((symbol, weight, round(weight * base, 2)))
    rows.sort(key=lambda r: -r[1])
    return rows


def deploy(execute=False):
    account = alpaca_client.get_account()
    positions = alpaca_client.get_positions()
    equity = account["portfolio_value"]
    cash = account["cash"]

    # Guard: the reset must have happened (clean, all-cash account).
    if positions:
        held = ", ".join(f"{p['symbol']}" for p in positions)
        print("ABORT: account still holds positions -- reset the Alpaca paper account to $100K first.")
        print(f"  Held: {held}")
        print("  In the Alpaca paper dashboard: Account > Reset, set starting equity to $100,000.")
        return None

    base = equity
    plan = _plan(base)
    invested = sum(d for _, _, d in plan)
    cash_after = base - invested

    print(f"=== Deploy Plan (base equity ${base:,.2f}, cash ${cash:,.2f}) ===")
    print(f"{'Symbol':8} {'Weight':>7}  {'Amount':>12}")
    for symbol, weight, dollars in plan:
        print(f"{symbol:8} {weight*100:6.1f}%  ${dollars:>10,.2f}")
    print(f"{'-'*32}")
    print(f"Invested:   ${invested:,.2f} ({invested/base*100:.0f}%)")
    print(f"Cash after: ${cash_after:,.2f} ({cash_after/base*100:.0f}%)  [min reserve {config.MIN_CASH_RESERVE_PCT*100:.0f}%]")

    if cash_after < base * config.MIN_CASH_RESERVE_PCT:
        print("WARNING: plan would breach the minimum cash reserve. Reduce target weights before deploying.")

    if not execute:
        print("\nPREVIEW ONLY -- no orders placed. Re-run with --auto to execute.")
        return plan

    # Market-hours note (Alpaca notional orders execute at/after open).
    try:
        clock = alpaca_client.get_clock()
        if not clock.get("is_open"):
            print(f"\nNote: market is closed. Orders will queue for next open ({clock.get('next_open')}).")
    except Exception as e:
        print(f"  (clock check skipped: {e})")

    print("\nExecuting deploy...")
    filled = []
    for symbol, weight, dollars in plan:
        try:
            order = alpaca_client.place_order(symbol, "buy", dollars)
        except Exception as e:
            print(f"  ERROR {symbol}: {e}")
            continue
        print(f"  BUY ${dollars:,.2f} {symbol} -- order {order['id']}")
        filled.append(symbol)
        notion_logger.log_trade({
            "symbol": symbol,
            "action": "buy",
            "amount": dollars,
            "order_id": order["id"],
            "reasoning": f"Clean-slate deploy: {weight*100:.1f}% target weight, on-thesis basket 2026-07-12",
            "strategy": config.STRATEGY,
            "paper": config.PAPER_TRADING,
        })

    print(f"\nDeployed {len(filled)}/{len(plan)} target names.")

    try:
        import positions_page
        positions_page.refresh_positions_page()
    except Exception as e:
        print(f"  (holdings page refresh skipped: {e})")

    return filled


if __name__ == "__main__":
    deploy(execute=False)
