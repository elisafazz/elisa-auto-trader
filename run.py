#!/usr/bin/env python3
import argparse
import subprocess
import sys
import traceback
import trader


def notify_failure(mode, error):
    """Send a macOS notification on unhandled failure (for cron runs)."""
    msg = f"{mode} failed: {str(error)[:100]}"
    script = f'display notification "{msg}" with title "Auto-Trader ERROR"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description="Auto-Trader: Claude-powered stock trading engine")
    parser.add_argument("--status", action="store_true", help="Show portfolio status")
    parser.add_argument("--analyze", action="store_true", help="Get Claude's trade recommendations")
    parser.add_argument("--execute", action="store_true", help="Execute trade recommendations")
    parser.add_argument("--auto", action="store_true", help="Skip confirmation prompt (for cron/autonomous use)")
    parser.add_argument("--report", action="store_true", help="Generate weekly performance report")
    args = parser.parse_args()

    if not any([args.status, args.analyze, args.execute, args.report]):
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


if __name__ == "__main__":
    main()
