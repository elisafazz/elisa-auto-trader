"""Unified weekly report across BOTH trading engines:
  - Alpaca stock engine (this repo)
  - Kalshi arbitrage engine (~/Dropbox/claude_work/elisa-kalshi-engine)

Writes ONE row per week to the Notion "Trading Weekly Report" DB. Replaces the
Alpaca-only Performance Reports as the single digest Elisa reads. The Kalshi side
degrades gracefully to "not yet live" until that engine is funded + keyed, so this
works today and needs no rework when Kalshi goes live.

Run: python combined_report.py            (writes the row + notifies)
     python combined_report.py --dry-run   (prints, no Notion write)
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta

from notion_client import Client
import config
import alpaca_client

COMBINED_DB = "ed971c50-b108-46b1-8adc-4818f8f6fbad"
STARTING_VALUE = getattr(config, "STARTING_VALUE", 100000.0)
KALSHI_DIR = os.path.expanduser("~/Dropbox/claude_work/elisa-kalshi-engine")


def get_stocks():
    """Alpaca side. Returns a dict; never raises (fail-soft, but records the error)."""
    try:
        account = alpaca_client.get_account()
        positions = alpaca_client.get_positions()
        orders = alpaca_client.get_all_orders(limit=500)

        pv = account["portfolio_value"]
        total_ret = ((pv - STARTING_VALUE) / STARTING_VALUE) * 100

        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_trades = [
            o for o in orders
            if o.get("submitted_at") and o["submitted_at"][:10] >= week_ago
            and o.get("status") in ("filled", "partially_filled")
        ]

        spy_ret = None
        try:
            bars = alpaca_client.get_bars(["SPY"], days=7).get("SPY", [])
            if len(bars) >= 2:
                spy_ret = ((bars[-1]["close"] - bars[0]["close"]) / bars[0]["close"]) * 100
        except Exception:
            pass

        best = worst = ""
        if positions:
            sp = sorted(positions, key=lambda p: p["unrealized_pl"])
            worst = f"{sp[0]['symbol']} ${sp[0]['unrealized_pl']:+.2f}"
            best = f"{sp[-1]['symbol']} ${sp[-1]['unrealized_pl']:+.2f}"

        return {
            "ok": True, "portfolio_value": pv, "total_return_pct": total_ret,
            "spy_return_pct": spy_ret, "trades": len(week_trades),
            "positions": len(positions), "best": best, "worst": worst,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


def get_kalshi():
    """Kalshi side via subprocess (avoids config.py namespace clash between repos).
    Returns active=False with a reason until the engine is funded + keyed."""
    try:
        proc = subprocess.run(
            [os.path.join(KALSHI_DIR, ".venv/bin/python"), "run.py", "--status"],
            cwd=KALSHI_DIR, capture_output=True, text=True, timeout=60,
        )
        out = proc.stdout + proc.stderr
        if proc.returncode != 0 or "KALSHI_KEY_ID not set" in out:
            return {"active": False, "reason": "not yet live (no key / not funded)"}
        balance, positions = None, 0
        for line in out.splitlines():
            if line.strip().startswith("Balance:"):
                balance = float(line.split("$")[1].strip())
            if line.strip().startswith("Open positions:"):
                positions = int(line.split(":")[1].strip())
        if balance is None:
            return {"active": False, "reason": "status unreadable"}
        return {"active": True, "balance": balance, "positions": positions}
    except Exception as e:
        return {"active": False, "reason": str(e)[:120]}


def build_row(stocks, kalshi):
    week_ending = datetime.now().strftime("%Y-%m-%d")
    stocks_val = stocks["portfolio_value"] if stocks["ok"] else 0.0
    kalshi_bal = kalshi["balance"] if kalshi["active"] else 0.0
    total_val = stocks_val + kalshi_bal

    notes = []
    if not stocks["ok"]:
        notes.append(f"STOCKS ERROR: {stocks['reason']}")
    if not kalshi["active"]:
        notes.append(f"Kalshi: {kalshi['reason']}")
    notes.append("Stocks: Claude Sonnet 5 swing (paper). Kalshi: deterministic arbitrage.")

    props = {
        "Report": {"title": [{"text": {"content": f"Week ending {week_ending}"}}]},
        "Week Ending": {"date": {"start": week_ending}},
        "Total Value": {"number": round(total_val, 2)},
        "Stocks Value": {"number": round(stocks_val, 2)},
        "Kalshi Balance": {"number": round(kalshi_bal, 2)},
        "Stock Trades": {"number": stocks["trades"] if stocks["ok"] else 0},
        "Kalshi Bets": {"number": kalshi["positions"] if kalshi["active"] else 0},
        "Status": {"select": {"name": "Pending Approval"}},
        "Notes": {"rich_text": [{"text": {"content": " | ".join(notes)[:1900]}}]},
    }
    if stocks["ok"]:
        props["Stocks Return"] = {"rich_text": [{"text": {"content": f"{stocks['total_return_pct']:+.2f}%"}}]}
        props["Total Return"] = {"rich_text": [{"text": {"content": f"{stocks['total_return_pct']:+.2f}% (stocks)"}}]}
        if stocks["best"]:
            props["Best Trade"] = {"rich_text": [{"text": {"content": stocks["best"]}}]}
        if stocks["worst"]:
            props["Worst Trade"] = {"rich_text": [{"text": {"content": stocks["worst"]}}]}
        if stocks["spy_return_pct"] is not None:
            props["Benchmark SPY"] = {"rich_text": [{"text": {"content": f"{stocks['spy_return_pct']:+.2f}%"}}]}
    return props, week_ending, total_val, notes


def main():
    dry = "--dry-run" in sys.argv
    stocks = get_stocks()
    kalshi = get_kalshi()
    props, week_ending, total_val, notes = build_row(stocks, kalshi)

    print(f"=== Trading Weekly ({week_ending}) ===")
    print(f"Stocks (Alpaca): {'$%.2f' % stocks['portfolio_value'] if stocks['ok'] else 'ERROR ' + stocks['reason']}"
          + (f"  {stocks['total_return_pct']:+.2f}% | SPY {stocks['spy_return_pct']:+.2f}% | {stocks['trades']} trades"
             if stocks['ok'] and stocks['spy_return_pct'] is not None else ""))
    print(f"Kalshi: {'$%.2f, %d positions' % (kalshi['balance'], kalshi['positions']) if kalshi['active'] else kalshi['reason']}")
    print(f"TOTAL: ${total_val:,.2f}")
    print("Notes: " + " | ".join(notes))

    if dry:
        print("[dry-run] not writing to Notion")
        return

    token = os.getenv("NOTION_TOKEN", config.NOTION_TOKEN if hasattr(config, "NOTION_TOKEN") else "")
    if not token:
        print("[notion] no NOTION_TOKEN -- skipping write (FAIL LOUD: report not persisted)")
        return
    try:
        Client(auth=token).pages.create(parent={"database_id": COMBINED_DB}, properties=props)
        print("[notion] combined report row written")
    except Exception as e:
        print(f"[notion] write FAILED: {e}")


if __name__ == "__main__":
    main()
