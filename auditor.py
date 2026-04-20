import time
import alpaca_client
import notion_logger
import config


def fetch_all_notion_trades():
    """Query all entries from the Notion Trade Log via data_sources.query."""
    client = notion_logger._get_client()
    trades = []
    start_cursor = None

    while True:
        kwargs = {"data_source_id": config.TRADE_LOG_DS}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = client.data_sources.query(**kwargs)

        for page in response["results"]:
            props = page["properties"]
            trades.append({
                "page_id": page["id"],
                "title": _get_title(props.get("Trade")),
                "date": _get_date(props.get("Date")),
                "symbol": _get_rich_text(props.get("Symbol")),
                "action": _get_select(props.get("Action")),
                "total": _get_number(props.get("Total")),
                "quantity": _get_number(props.get("Quantity")),
                "price": _get_number(props.get("Price")),
            })

        if not response.get("has_more"):
            break
        start_cursor = response.get("next_cursor")
        time.sleep(0.35)

    return trades


def _get_title(prop):
    if not prop or not prop.get("title"):
        return ""
    parts = prop["title"]
    return parts[0]["text"]["content"] if parts else ""


def _get_rich_text(prop):
    if not prop or not prop.get("rich_text"):
        return ""
    parts = prop["rich_text"]
    return parts[0]["text"]["content"] if parts else ""


def _get_select(prop):
    if not prop or not prop.get("select"):
        return ""
    return prop["select"]["name"]


def _get_number(prop):
    if not prop:
        return None
    return prop.get("number")


def _get_date(prop):
    if not prop or not prop.get("date"):
        return ""
    return prop["date"]["start"]


def _normalize_side(alpaca_side):
    """'OrderSide.BUY' -> 'buy'"""
    return alpaca_side.split(".")[-1].lower()


def _normalize_status(alpaca_status):
    """'OrderStatus.FILLED' -> 'filled'"""
    return alpaca_status.split(".")[-1].lower()


def _extract_date(submitted_at):
    """'2026-04-09 13:30:00+00:00' -> '2026-04-09'"""
    return submitted_at[:10]


def _order_amount(order):
    """Get dollar amount from an Alpaca order, preferring notional."""
    if order["notional"]:
        return float(order["notional"])
    if order["filled_avg_price"] and order["filled_qty"]:
        return float(order["filled_avg_price"]) * float(order["filled_qty"])
    return 0.0


def reconcile(alpaca_orders, notion_trades):
    """Match Alpaca orders to Notion entries. Returns audit report dict."""
    available = list(notion_trades)  # copy so we can remove matched
    matched = []
    missing_from_notion = []
    amount_mismatches = []
    enrichable = []

    for order in alpaca_orders:
        status = _normalize_status(order["status"])
        side = _normalize_side(order["side"])
        date = _extract_date(order["submitted_at"])
        amount = _order_amount(order)

        # Only reconcile filled orders -- cancelled/expired shouldn't be in Notion
        if status not in ("filled", "partially_filled"):
            continue

        # Find Notion candidates
        candidates = [
            n for n in available
            if n["symbol"].upper() == order["symbol"].upper()
            and n["date"] == date
            and n["action"].lower() == side
        ]

        if not candidates:
            missing_from_notion.append({
                "order": order,
                "side": side,
                "date": date,
                "amount": amount,
            })
            continue

        # Pick best match by closest amount
        match = min(candidates, key=lambda n: abs((n["total"] or 0) - amount))
        available.remove(match)

        # Check amount mismatch
        if amount > 0 and abs((match["total"] or 0) - amount) / amount > 0.05:
            amount_mismatches.append({
                "order": order,
                "notion": match,
                "alpaca_amount": amount,
                "notion_amount": match["total"],
            })

        # Check if enrichable (missing quantity or price)
        if match["quantity"] is None or match["price"] is None:
            enrichable.append({
                "notion_page_id": match["page_id"],
                "notion_title": match["title"],
                "notion_quantity": match["quantity"],
                "notion_price": match["price"],
                "alpaca_qty": order["filled_qty"],
                "alpaca_price": order["filled_avg_price"],
            })

        matched.append({"order": order, "notion": match})

    return {
        "matched": matched,
        "missing_from_notion": missing_from_notion,
        "notion_only": available,  # leftover unmatched Notion entries
        "amount_mismatches": amount_mismatches,
        "enrichable": enrichable,
    }


def print_report(result, alpaca_count, notion_count):
    """Print human-readable audit report."""
    print(f"=== Trade Audit Report ===\n")
    print(f"Alpaca orders (filled): {alpaca_count}")
    print(f"Notion entries:         {notion_count}")
    print(f"Matched:                {len(result['matched'])}")
    print(f"Missing from Notion:    {len(result['missing_from_notion'])}")
    print(f"Notion-only (no match): {len(result['notion_only'])}")
    print(f"Amount mismatches:      {len(result['amount_mismatches'])}")
    print(f"Enrichable:             {len(result['enrichable'])}")

    if result["missing_from_notion"]:
        print(f"\n--- Missing from Notion ---")
        for entry in result["missing_from_notion"]:
            o = entry["order"]
            print(f"  {entry['date']}  {entry['side'].upper():4s}  {o['symbol']:6s}  ${entry['amount']:>10,.2f}  (order {o['id'][:8]}...)")

    if result["amount_mismatches"]:
        print(f"\n--- Amount Mismatches ---")
        for entry in result["amount_mismatches"]:
            print(
                f"  {entry['order']['symbol']:6s}  "
                f"Alpaca: ${entry['alpaca_amount']:,.2f}  "
                f"Notion: ${entry['notion_amount']:,.2f}  "
                f"diff: ${abs(entry['alpaca_amount'] - (entry['notion_amount'] or 0)):,.2f}"
            )

    if result["enrichable"]:
        print(f"\n--- Enrichable (missing Quantity/Price) ---")
        for entry in result["enrichable"]:
            qty_str = f"qty={entry['alpaca_qty']}" if entry["alpaca_qty"] else "qty=?"
            price_str = f"price=${float(entry['alpaca_price']):.2f}" if entry["alpaca_price"] else "price=?"
            print(f"  {entry['notion_title']}  ->  {qty_str}, {price_str}")

    if result["notion_only"]:
        print(f"\n--- Notion-only (no Alpaca match) ---")
        for entry in result["notion_only"]:
            print(f"  {entry['date']}  {entry['action']:4s}  {entry['symbol']:6s}  ${entry['total'] or 0:>10,.2f}  [{entry['title']}]")

    if not any([result["missing_from_notion"], result["amount_mismatches"],
                result["enrichable"], result["notion_only"]]):
        print("\nAll clear -- Notion matches Alpaca.")


def backfill_missing(missing_entries):
    """Create Notion entries for Alpaca orders that were never logged."""
    if not missing_entries:
        return 0

    count = 0
    for entry in missing_entries:
        order = entry["order"]
        trade_data = {
            "symbol": order["symbol"],
            "action": entry["side"],
            "amount": entry["amount"],
            "date": entry["date"],
            "strategy": "swing",
            "reasoning": "Backfilled from Alpaca order history",
            "paper": True,
        }
        if order["filled_qty"]:
            trade_data["quantity"] = float(order["filled_qty"])
        if order["filled_avg_price"]:
            trade_data["price"] = float(order["filled_avg_price"])

        notion_logger.log_trade(trade_data)
        count += 1
        time.sleep(0.35)

    print(f"\n  Backfilled {count} missing entries.")
    return count


def enrich_existing(enrichable_entries):
    """Update Notion entries with missing Quantity/Price from Alpaca data."""
    if not enrichable_entries:
        return 0

    client = notion_logger._get_client()
    count = 0
    for entry in enrichable_entries:
        props = {}
        if entry["alpaca_qty"] and entry["notion_quantity"] is None:
            props["Quantity"] = {"number": float(entry["alpaca_qty"])}
        if entry["alpaca_price"] and entry["notion_price"] is None:
            props["Price"] = {"number": float(entry["alpaca_price"])}

        if props:
            client.pages.update(page_id=entry["notion_page_id"], properties=props)
            count += 1
            time.sleep(0.35)

    print(f"  Enriched {count} entries with Quantity/Price.")
    return count


def run_audit(fix=False):
    """Main entry point: fetch, reconcile, report, optionally fix."""
    print("Fetching Alpaca orders...")
    all_orders = alpaca_client.get_all_orders()

    print("Fetching Notion Trade Log entries...")
    notion_trades = fetch_all_notion_trades()

    # Count filled orders for the report
    filled_count = sum(
        1 for o in all_orders
        if _normalize_status(o["status"]) in ("filled", "partially_filled")
    )

    result = reconcile(all_orders, notion_trades)
    print_report(result, filled_count, len(notion_trades))

    if fix:
        print("\n--- Applying fixes ---")
        backfill_missing(result["missing_from_notion"])
        enrich_existing(result["enrichable"])
        print("\nDone. Run --audit again to verify.")
    else:
        import alerts
        alerts.alert_audit_mismatch(
            result["missing_from_notion"],
            result["amount_mismatches"],
        )
