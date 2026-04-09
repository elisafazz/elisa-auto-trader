from datetime import datetime, timezone
from notion_client import Client
import config

TRADE_LOG_DB = config.TRADE_LOG_DB
PERFORMANCE_REPORTS_DB = config.PERFORMANCE_REPORTS_DB


def _get_client():
    return Client(auth=config.NOTION_TOKEN)


def log_trade(trade_data):
    """Log a trade to the Notion Trade Log DB."""
    if not config.NOTION_TOKEN:
        print(f"  [Notion] No token -- skipping log for {trade_data['action']} {trade_data['symbol']}")
        return

    try:
        client = _get_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        title = f"{trade_data['action'].upper()} {trade_data['symbol']} ${trade_data['amount']:.2f}"

        client.pages.create(
            parent={"database_id": TRADE_LOG_DB},
            properties={
                "Trade": {"title": [{"text": {"content": title}}]},
                "Date": {"date": {"start": today}},
                "Symbol": {"rich_text": [{"text": {"content": trade_data["symbol"]}}]},
                "Action": {"select": {"name": trade_data["action"].capitalize()}},
                "Total": {"number": trade_data["amount"]},
                "Strategy": {"select": {"name": trade_data.get("strategy", "swing").capitalize()}},
                "Reasoning": {"rich_text": [{"text": {"content": trade_data.get("reasoning", "")[:2000]}}]},
                "Paper Trade": {"checkbox": trade_data.get("paper", True)},
            },
        )
        print(f"  [Notion] Logged: {title}")
    except Exception as e:
        print(f"  [Notion] Failed to log trade: {e}")


def log_report(report_data):
    """Log a performance report to the Notion Performance Reports DB."""
    if not config.NOTION_TOKEN:
        print(f"  [Notion] No token -- skipping report log")
        return

    try:
        client = _get_client()
        title = report_data.get("title", "Weekly Report")

        properties = {
            "Report": {"title": [{"text": {"content": title}}]},
            "Week Ending": {"date": {"start": report_data["week_ending"]}},
            "Portfolio Value": {"number": report_data["portfolio_value"]},
            "Weekly Return": {"rich_text": [{"text": {"content": f"{report_data['weekly_return_pct']:+.2f}%"}}]},
            "Total Return": {"rich_text": [{"text": {"content": f"{report_data['total_return_pct']:+.2f}%"}}]},
            "Trades Executed": {"number": report_data["trades_executed"]},
            "Status": {"select": {"name": "Pending Approval"}},
        }

        if report_data.get("best_trade"):
            properties["Best Trade"] = {"rich_text": [{"text": {"content": report_data["best_trade"]}}]}
        if report_data.get("worst_trade"):
            properties["Worst Trade"] = {"rich_text": [{"text": {"content": report_data["worst_trade"]}}]}
        if report_data.get("strategy_notes"):
            properties["Strategy Notes"] = {"rich_text": [{"text": {"content": report_data["strategy_notes"][:2000]}}]}
        if report_data.get("benchmark_spy") is not None:
            properties["Benchmark (SPY)"] = {"rich_text": [{"text": {"content": f"{report_data['benchmark_spy']:+.2f}%"}}]}

        client.pages.create(
            parent={"database_id": PERFORMANCE_REPORTS_DB},
            properties=properties,
        )
        print(f"  [Notion] Logged report: {title}")
    except Exception as e:
        print(f"  [Notion] Failed to log report: {e}")
