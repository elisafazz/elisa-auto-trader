"""Go-live readiness diagnostic for the Alpaca stock engine.

Runs after a clean paper-trading window (the engine's brain was fixed 2026-07-05,
so the prior record is contaminated and the clock restarts there). Pulls the paper
equity curve since CLEAN_START, computes return vs SPY, annualized Sharpe, and max
drawdown, applies OBJECTIVE pass criteria, and writes a GO / NO-GO verdict to the
Notion Workflow Notifications DB (Action Needed=true -> phone push).

This is a RECOMMENDATION, not an auto-action. Elisa decides whether to fund real
weekly money. Deliberately conservative: paper has no slippage or emotion.

Run: python golive_diagnostic.py            (writes verdict + notifies)
     python golive_diagnostic.py --dry-run   (prints only)
"""
import os
import sys
import json
import math
import urllib.request
from datetime import datetime, date, timezone

import config
import alpaca_client

CLEAN_START = "2026-07-05"          # brain-fix date; paper record before this is invalid
WF_DB = "358f3cdd-67a4-8061-8b0c-f49ef7e1f9e7"
PAPER_BASE = "https://paper-api.alpaca.markets"

# Pass criteria (ALL must hold for GO)
MAX_DRAWDOWN_LIMIT = 0.15   # 15%
MIN_SHARPE = 0.5
# plus: window return > SPY window return, and window return > 0


def fetch_equity_curve():
    """Paper portfolio history: list of (date_iso, equity) since CLEAN_START."""
    url = f"{PAPER_BASE}/v2/account/portfolio/history?period=3M&timeframe=1D"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    })
    data = json.load(urllib.request.urlopen(req, timeout=30))
    ts, eq = data.get("timestamp", []), data.get("equity", [])
    curve = []
    for t, e in zip(ts, eq):
        d = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
        if e and d >= CLEAN_START:
            curve.append((d, float(e)))
    return curve


def metrics(curve):
    if len(curve) < 2:
        return None
    equities = [e for _, e in curve]
    start, end = equities[0], equities[-1]
    window_return = (end - start) / start

    daily = [(equities[i] - equities[i - 1]) / equities[i - 1] for i in range(1, len(equities))]
    if len(daily) >= 2:
        mean = sum(daily) / len(daily)
        var = sum((x - mean) ** 2 for x in daily) / (len(daily) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
    else:
        sharpe = 0.0

    peak, max_dd = equities[0], 0.0
    for e in equities:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak)

    return {"window_return": window_return, "sharpe": sharpe, "max_drawdown": max_dd,
            "days": len(curve), "start_equity": start, "end_equity": end}


def spy_return(days):
    try:
        bars = alpaca_client.get_bars(["SPY"], days=max(days + 2, 10)).get("SPY", [])
        if len(bars) >= 2:
            return (bars[-1]["close"] - bars[0]["close"]) / bars[0]["close"]
    except Exception:
        pass
    return None


def verdict(m, spy):
    reasons = []
    beat_spy = spy is not None and m["window_return"] > spy
    positive = m["window_return"] > 0
    dd_ok = m["max_drawdown"] <= MAX_DRAWDOWN_LIMIT
    sharpe_ok = m["sharpe"] >= MIN_SHARPE

    if not positive: reasons.append(f"return {m['window_return']:+.1%} not positive")
    if spy is None: reasons.append("SPY benchmark unavailable (cannot confirm outperformance)")
    elif not beat_spy: reasons.append(f"return {m['window_return']:+.1%} did not beat SPY {spy:+.1%}")
    if not dd_ok: reasons.append(f"max drawdown {m['max_drawdown']:.1%} exceeds {MAX_DRAWDOWN_LIMIT:.0%}")
    if not sharpe_ok: reasons.append(f"Sharpe {m['sharpe']:.2f} below {MIN_SHARPE}")

    go = positive and beat_spy and dd_ok and sharpe_ok and m["days"] >= 20
    if m["days"] < 20:
        reasons.append(f"only {m['days']} days of clean data (<20; too short)")
        go = False
    return go, reasons


def post_wf(title, summary, next_action):
    token = os.getenv("NOTION_TOKEN", getattr(config, "NOTION_TOKEN", ""))
    if not token:
        print("[notion] no token -- verdict NOT persisted (FAIL LOUD)")
        return
    body = {"parent": {"database_id": WF_DB}, "properties": {
        "Name": {"title": [{"text": {"content": title}}]},
        "Severity": {"select": {"name": "High"}},
        "Source": {"select": {"name": "Script"}},
        "Workflow": {"select": {"name": "Auto-Trader"}},
        "Action Needed": {"checkbox": True},
        "Summary": {"rich_text": [{"text": {"content": summary[:1900]}}]},
        "Next Action": {"rich_text": [{"text": {"content": next_action[:1900]}}]},
        "Attention Date": {"date": {"start": date.today().isoformat()}}}}
    req = urllib.request.Request("https://api.notion.com/v1/pages", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "Notion-Version": "2022-06-28"})
    try:
        urllib.request.urlopen(req, timeout=20); print("[notion] verdict posted")
    except Exception as e:
        print(f"[notion] post FAILED: {e}")


def main():
    dry = "--dry-run" in sys.argv
    try:
        curve = fetch_equity_curve()
    except Exception as e:
        msg = f"Go-live diagnostic FAILED to fetch equity curve: {e}"
        print(msg)
        if not dry: post_wf("Go-live diagnostic ERROR", msg, "Check ALPACA keys + paper account")
        return

    m = metrics(curve)
    if not m:
        msg = f"Not enough clean data since {CLEAN_START} ({len(curve)} points)."
        print(msg)
        if not dry: post_wf("Go-live diagnostic: insufficient data", msg,
                            "Let the fixed engine run longer, re-run diagnostic")
        return

    spy = spy_return(m["days"])
    go, reasons = verdict(m, spy)
    tag = "GO" if go else "NO-GO"

    summary = (f"[{tag}] Since {CLEAN_START} ({m['days']}d): return {m['window_return']:+.1%} vs "
               f"SPY {spy:+.1%} | Sharpe {m['sharpe']:.2f} | max DD {m['max_drawdown']:.1%}. "
               + ("All criteria met." if go else "Fails: " + "; ".join(reasons))) if spy is not None else \
              (f"[{tag}] Since {CLEAN_START} ({m['days']}d): return {m['window_return']:+.1%} | "
               f"Sharpe {m['sharpe']:.2f} | max DD {m['max_drawdown']:.1%}. "
               + ("All criteria met." if go else "Fails: " + "; ".join(reasons)))
    next_action = ("Elisa: engine cleared paper criteria. Consider funding a SMALL fixed weekly amount "
                   "(start tiny). Paper has no slippage/emotion -- size conservatively.") if go else \
                  "Keep engine on PAPER. Do not fund real money yet. Re-run diagnostic after another clean window."

    print(f"=== Go-Live Diagnostic ({date.today()}) ===")
    print(summary)
    print("Verdict:", tag)
    print("Next:", next_action)
    if not dry:
        post_wf(f"Auto-Trader go-live: {tag}", summary, next_action)


if __name__ == "__main__":
    main()
