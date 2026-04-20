#!/usr/bin/env python3
import argparse
import sys
import traceback
import alerts
import trader


def notify_failure(mode, error):
    """Persist a critical alert and fire a macOS notification."""
    alerts.log_alert(
        "critical",
        "cron_failure",
        f"{mode} failed: {str(error)[:200]}",
        details={"mode": mode, "error_type": type(error).__name__},
    )


def main():
    parser = argparse.ArgumentParser(description="Auto-Trader: Claude-powered stock trading engine")
    parser.add_argument("--status", action="store_true", help="Show portfolio status")
    parser.add_argument("--analyze", action="store_true", help="Get Claude's trade recommendations")
    parser.add_argument("--execute", action="store_true", help="Execute trade recommendations")
    parser.add_argument("--auto", action="store_true", help="Skip confirmation prompt (for cron/autonomous use)")
    parser.add_argument("--report", action="store_true", help="Generate weekly performance report")
    parser.add_argument("--audit", action="store_true", help="Audit Notion Trade Log against Alpaca orders")
    parser.add_argument("--fix", action="store_true", help="With --audit: backfill missing and enrich incomplete entries")
    args = parser.parse_args()

    if args.fix and not args.audit:
        print("--fix requires --audit")
        sys.exit(1)

    if not any([args.status, args.analyze, args.execute, args.report, args.audit]):
        parser.print_help()
        sys.exit(1)

    if args.status:
        trader.status()

    if args.analyze and args.execute and args.auto:
        try:
            trader.auto_run()
        except Exception as e:
            traceback.print_exc()
            notify_failure("Daily trading", e)
            sys.exit(1)
    elif args.analyze:
        result = trader.analyze()
        if args.execute and result.get("recommendations"):
            confirm = input("\nExecute these trades? (yes/no): ")
            if confirm.strip().lower() == "yes":
                trader.execute(result["recommendations"])
            else:
                print("Trades not executed.")

    if args.report:
        try:
            trader.report()
        except Exception as e:
            traceback.print_exc()
            notify_failure("Weekly report", e)
            sys.exit(1)

    if args.audit:
        import auditor
        auditor.run_audit(fix=args.fix)


if __name__ == "__main__":
    main()
