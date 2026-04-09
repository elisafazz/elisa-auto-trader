import config


def log_trade(trade_data):
    """Log a trade to the Notion Trade Log DB. Stub for Phase 1."""
    print(f"  [Notion stub] Would log trade: {trade_data['action']} {trade_data['symbol']} ${trade_data['amount']:.2f}")


def log_report(report_data):
    """Log a performance report to the Notion Performance Reports DB. Stub for Phase 1."""
    print(f"  [Notion stub] Would log report: {report_data.get('title', 'Weekly Report')}")
