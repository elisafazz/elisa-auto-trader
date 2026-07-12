"""Holdings snapshot layer: refresh a Notion page with the positions we currently hold.

Pulls live Alpaca positions, classifies each by Elisa's allocation thesis
(AI infrastructure ex-mega-cap / emerging biotech / off-thesis), and rewrites the
body of a single "Current Holdings" page under the Auto Trader Dashboard so it always
reflects the latest snapshot.

Thesis source of truth is watchlist.py (WATCHLIST_AI / WATCHLIST_BIOTECH); the static
off-thesis sets below only exist to LABEL why a held name is off-thesis.

CLI: `python run.py --positions`
Also called at the end of auto_run() so the page refreshes on every trading day.
"""

from datetime import datetime, timezone

from notion_client import Client

import config
import alpaca_client
import watchlist

DASHBOARD_PAGE_ID = "33df3cdd-67a4-8177-a2b9-dbadd2fc1dde"

# Off-thesis labels only (why a held name does not fit the thesis).
MEGA_CAP = {"GOOGL", "GOOG", "MSFT", "AMZN", "META", "AAPL"}
BIG_PHARMA = {"LLY", "VRTX", "REGN", "ABBV", "PFE", "MRK", "BMY", "AMGN", "GILD", "NVS", "AZN"}
ETFS = {"XLK", "IBB", "SPY", "QQQ", "XLU", "XLE", "GLD", "XLV"}

# Display order for buckets.
BUCKET_ORDER = [
    "AI Infrastructure",
    "Emerging Biotech",
    "Mega-cap (off thesis)",
    "Big pharma (off thesis)",
    "ETF (off thesis)",
    "Other (off thesis)",
]


def classify(symbol):
    """Return (bucket_label, on_thesis) for a held ticker."""
    s = symbol.upper()
    if s in watchlist.WATCHLIST_AI:
        return "AI Infrastructure", True
    if s in watchlist.WATCHLIST_BIOTECH:
        return "Emerging Biotech", True
    if s in MEGA_CAP:
        return "Mega-cap (off thesis)", False
    if s in BIG_PHARMA:
        return "Big pharma (off thesis)", False
    if s in ETFS:
        return "ETF (off thesis)", False
    return "Other (off thesis)", False


def _rt(text):
    return [{"type": "text", "text": {"content": str(text)}}]


def _row(cells):
    return {
        "type": "table_row",
        "table_row": {"cells": [_rt(c) for c in cells]},
    }


def _clear_page(client, page_id):
    """Archive every existing child block so the body can be rewritten fresh.

    Safe because this page holds only text/table blocks (no child pages/databases).
    """
    cursor = None
    while True:
        resp = client.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100)
        for block in resp.get("results", []):
            try:
                client.blocks.delete(block_id=block["id"])
            except Exception as e:
                print(f"  [Positions] Could not delete block {block['id']}: {e}")
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")


def _get_or_create_page(client):
    """Return the holdings page id. Creates it under the dashboard on first run."""
    page_id = getattr(config, "POSITIONS_PAGE_ID", "")
    if page_id:
        return page_id
    page = client.pages.create(
        parent={"page_id": DASHBOARD_PAGE_ID},
        properties={"title": {"title": _rt("Current Holdings")}},
    )
    new_id = page["id"]
    print(f"  [Positions] Created Current Holdings page: {new_id}")
    print(f"  [Positions] ACTION: add POSITIONS_PAGE_ID = \"{new_id}\" to config.py")
    return new_id


def _build_blocks(account, positions):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    on_val = sum(p["market_value"] for p in positions if classify(p["symbol"])[1])
    off_val = sum(p["market_value"] for p in positions if not classify(p["symbol"])[1])
    total_pos = on_val + off_val
    on_pct = (on_val / total_pos * 100) if total_pos else 0.0

    blocks = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": _rt(
                    f"Last updated {now}. Paper portfolio ${account['portfolio_value']:,.2f}, "
                    f"cash ${account['cash']:,.2f}. On-thesis holdings ${on_val:,.2f} "
                    f"({on_pct:.0f}% of invested), off-thesis ${off_val:,.2f}."
                )
            },
        },
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": _rt(
                    "Thesis: AI infrastructure ex-mega-cap (chips, memory, networking, power, "
                    "cooling) plus emerging biotech. Off-thesis names are legacy positions left "
                    "to rotate out as the watchlist biases new buys on-thesis."
                ),
                "icon": {"type": "emoji", "emoji": "\U0001F4C8"},
            },
        },
    ]

    header = ["Ticker", "Category", "Thesis", "Value", "P&L %"]
    rows = [_row(header)]
    ordered = sorted(
        positions,
        key=lambda p: (
            BUCKET_ORDER.index(classify(p["symbol"])[0]),
            -p["market_value"],
        ),
    )
    for p in ordered:
        bucket, on_thesis = classify(p["symbol"])
        rows.append(
            _row([
                p["symbol"],
                bucket,
                "ON" if on_thesis else "off",
                f"${p['market_value']:,.2f}",
                f"{p['unrealized_plpc'] * 100:+.1f}%",
            ])
        )

    blocks.append({
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(header),
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    })
    return blocks


def refresh_positions_page():
    """Rewrite the Current Holdings page with the latest Alpaca snapshot."""
    if not config.NOTION_TOKEN:
        print("  [Positions] No NOTION_TOKEN -- skipping holdings page refresh")
        return None

    try:
        account = alpaca_client.get_account()
        positions = alpaca_client.get_positions()
        client = Client(auth=config.NOTION_TOKEN)
        page_id = _get_or_create_page(client)
        _clear_page(client, page_id)
        blocks = _build_blocks(account, positions)
        client.blocks.children.append(block_id=page_id, children=blocks)
        print(f"  [Positions] Refreshed holdings page ({len(positions)} positions)")
        return page_id
    except Exception as e:
        print(f"  [Positions] Failed to refresh holdings page: {e}")
        return None


if __name__ == "__main__":
    refresh_positions_page()
